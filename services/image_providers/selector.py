"""
services/image_providers/selector.py — Orquestrador de busca, filtragem,
seleção e persistência de imagens para o Chocolícia.
"""

import os
import re
from typing import Any, Dict, List, Optional

from services.image_providers.base import StandardImageResult
from services.image_providers.pixabay import PixabayProvider
from services.image_providers.pexels import PexelsProvider
from services.image_providers.openverse import OpenverseProvider
from services.image_providers.wikimedia import WikimediaProvider
from services.image_providers.storage import baixar_e_processar_imagem
from services.image_providers.database import registrar_imagem


# Termos culinários frequentes de confeitaria (PT -> EN) para enriquecimento de busca
DICIONARIO_CULINARIO_EN = {
    "bolo": "cake",
    "bolos": "cakes",
    "cenoura": "carrot",
    "chocolate": "chocolate",
    "morango": "strawberry",
    "limao": "lemon",
    "limão": "lemon",
    "torta": "pie tart",
    "tortas": "tarts pies",
    "brigadeiro": "chocolate truffles fudge",
    "trufa": "chocolate truffle",
    "trufas": "chocolate truffles",
    "bombom": "chocolate bonbon",
    "brownie": "chocolate brownie",
    "cupcake": "cupcake",
    "pudim": "caramel pudding flan",
    "mousse": "chocolate mousse",
    "cookies": "chocolate chip cookies",
    "biscoito": "cookies biscuits",
    "doce": "dessert sweet",
    "doces": "desserts sweets",
    "sobremesa": "dessert",
    "confeitaria": "pastry confectionery bakery",
    "aniversario": "birthday cake",
    "aniversário": "birthday cake",
}

STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob",
    "sobre", "e", "ou", "que", "se", "como", "facil", "fácil", "rapido", "rápido",
    "caseiro", "caseira", "delicioso", "deliciosa", "receita", "passo",
}


class ImageSelector:
    """Gerencia a consulta a múltiplos bancos de imagens e seleciona a melhor candidata."""

    def __init__(self):
        # Inicializa os quatro provedores respeitando a ordem de prioridade
        self.providers = [
            PixabayProvider(),      # Prioritário
            PexelsProvider(),       # Complementar fotográfico
            OpenverseProvider(),    # Complementar Creative Commons
            WikimediaProvider(),    # Complementar enciclopédico/educativo
        ]

    def _gerar_queries(
        self,
        titulo: str,
        categoria: str = "",
        subcategoria: str = "",
        ingredientes: Optional[List[str]] = None,
    ) -> List[tuple[str, str]]:
        """
        Retorna lista de tuplas (query, idioma), ordenadas por especificidade.
        """
        queries: List[tuple[str, str]] = []

        # 1. Título limpo em português
        tokens = re.findall(r"[A-Za-zçÇãÃõÕáéíóúÁÉÍÓÚâêîôûÂÊÎÔÛ0-9]+", titulo)
        tokens_relevantes = [t for t in tokens if t.lower() not in STOPWORDS and len(t) > 2]
        if tokens_relevantes:
            queries.append((" ".join(tokens_relevantes[:4]), "pt"))

        # 2. Subcategoria se informada
        if subcategoria:
            queries.append((subcategoria.strip(), "pt"))

        # 3. Tradução culinária para inglês para máxima cobertura
        termos_en = []
        for t in tokens_relevantes:
            t_lower = t.lower()
            if t_lower in DICIONARIO_CULINARIO_EN:
                termos_en.append(DICIONARIO_CULINARIO_EN[t_lower])
        if termos_en:
            queries.append((" ".join(termos_en[:3]), "en"))

        # 4. Categoria em português
        if categoria:
            queries.append((categoria.strip(), "pt"))

        # 5. Fallback culinário temático
        queries.append(("chocolate dessert", "en"))

        # Deduplicação mantendo a ordem
        vistos = set()
        resultado = []
        for q, lang in queries:
            q_norm = q.lower().strip()
            if q_norm and q_norm not in vistos:
                vistos.add(q_norm)
                resultado.append((q, lang))

        return resultado

    def buscar_e_armazenar_imagem(
        self,
        titulo: str,
        categoria: str = "",
        subcategoria: str = "",
        ingredientes: Optional[List[str]] = None,
        min_width: int = 1280,
        baixar: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Realiza a busca em cascata nos 4 provedores, seleciona a melhor imagem,
        faz o download seguro (com proteção SSRF) e persiste os metadados.
        """
        queries = self._gerar_queries(titulo, categoria, subcategoria, ingredientes)
        
        # Filtra provedores ativos e disponíveis
        provedores_ativos = [p for p in self.providers if p.is_available()]
        if not provedores_ativos:
            print("[ImageSelector] Nenhum provedor de imagem está ativo/configurado.")
            return None

        for query_texto, lang in queries:
            for provider in provedores_ativos:
                try:
                    candidatos = provider.search(
                        query=query_texto,
                        limit=5,
                        min_width=min_width,
                        lang=lang,
                    )

                    if not candidatos:
                        continue

                    # Filtra os candidatos válidos (horizontal e licença comercial)
                    validos = [
                        c for c in candidatos 
                        if c.is_commercial_friendly and c.is_horizontal
                    ]
                    if not validos:
                        validos = candidatos

                    # Seleciona o melhor candidato
                    escolhido: StandardImageResult = validos[0]

                    slug_base = re.sub(r"[^\w-]", "-", titulo.lower())[:30]
                    alt_texto = f"{titulo} pronto para servir"

                    resultado_final = {
                        "mode": "stock",
                        "provider": escolhido.provider,
                        "provider_image_id": escolhido.provider_image_id,
                        "sourceImageUrl": escolhido.original_image_url,
                        "sourcePageUrl": escolhido.original_page_url,
                        "author": escolhido.photographer,
                        "authorUrl": escolhido.photographer_url,
                        "license": escolhido.license,
                        "licenseUrl": escolhido.license_url,
                        "attributionText": escolhido.attribution_text,
                        "coverImageAlt": alt_texto,
                        "width": escolhido.width,
                        "height": escolhido.height,
                        "search_query": query_texto,
                    }

                    # Se solicitado o download real e armazenamento
                    if baixar:
                        download_info = baixar_e_processar_imagem(
                            url=escolhido.original_image_url,
                            slug=slug_base,
                        )
                        resultado_final.update({
                            "stored_path": download_info["stored_path"],
                            "stored_image_url": download_info["stored_url"],
                            "final_width": download_info["width"],
                            "final_height": download_info["height"],
                            "file_size_bytes": download_info["size_bytes"],
                            "format": download_info["format"],
                        })

                        # Grava no banco de dados local com metadados completos
                        reg_id = registrar_imagem(
                            provider=escolhido.provider,
                            provider_image_id=escolhido.provider_image_id,
                            original_image_url=escolhido.original_image_url,
                            original_page_url=escolhido.original_page_url,
                            stored_image_url=download_info["stored_url"],
                            stored_path=download_info["stored_path"],
                            photographer=escolhido.photographer,
                            license=escolhido.license,
                            license_url=escolhido.license_url,
                            attribution_text=escolhido.attribution_text,
                            search_query=query_texto,
                            width=download_info["width"],
                            height=download_info["height"],
                            image_status="stored",
                        )
                        resultado_final["db_record_id"] = reg_id

                    return resultado_final

                except Exception as e:
                    print(f"[ImageSelector] Erro ao consultar {provider.name} com query '{query_texto}': {e}")
                    continue

        return None

