"""
imagem_service.py — Serviço unificado de busca, processamento e proveniência de imagens
para o agente do Chocolícia.

Integra 4 bancos de imagens reais com controle independente:
    1. Pixabay (fonte prioritária com chave)
    2. Pexels (fonte complementar de alta resolução com chave)
    3. Openverse (fonte complementar de licença aberta Creative Commons)
    4. Wikimedia Commons (fonte complementar enciclopédica, técnicas e receitas)

Preserva integralmente:
- A compatibilidade com buscar_imagem_capa(titulo, tema, categoria)
- A compatibilidade com buscar_imagem_noticia(...)
- O fluxo de retorno de dicionários com imagem_url, imagem_fonte, imagem_autor, etc.
- O novo contrato estruturado de receitas e artigos (mode, provider, sourceImageUrl, stored_image_url)
"""

import os
import re
from typing import Optional, Dict, Any, List

from services.image_providers import (
    ImageSelector,
    buscar_e_armazenar_imagem as _buscar_e_armazenar,
    PixabayProvider,
    PexelsProvider,
    OpenverseProvider,
    WikimediaProvider,
)

_selector = ImageSelector()


def buscar_imagem_receita(
    titulo: str,
    categoria: str = "",
    subcategoria: str = "",
    tags: Optional[List[str]] = None,
    baixar_localmente: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Busca de imagem para receitas no Chocolícia.
    Consulta os 4 bancos de imagens (Pixabay, Pexels, Openverse, Wikimedia)
    respeitando configurações de ativação, validação de licença comercial,
    proporção horizontal e resolução de capa.
    """
    return _selector.buscar_e_armazenar_imagem(
        titulo=titulo,
        categoria=categoria,
        subcategoria=subcategoria,
        ingredientes=tags,
        min_width=1280,
        baixar=baixar_localmente,
    )


def buscar_imagem_capa(
    titulo: str = "",
    tema: str | None = None,
    categoria: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Função de compatibilidade consumida por pipeline/gerar_artigos.py e agents/seo.py.
    Preserva a assinatura e o formato de dicionário esperado pelo código existente.
    """
    res = buscar_imagem_receita(
        titulo=titulo,
        categoria=categoria or "",
        subcategoria=tema or "",
        baixar_localmente=True,
    )

    if res:
        url_imagem = res.get("stored_image_url") or res.get("sourceImageUrl")
        return {
            "imagem_url": url_imagem,
            "imagem_fonte": f"{res.get('provider', '').capitalize()} (banco de imagens)",
            "imagem_query": res.get("search_query", titulo),
            "imagem_alt": res.get("coverImageAlt", f"{titulo} servido"),
            "imagem_autor": res.get("author", "Fotógrafo"),
            "imagem_link": res.get("sourcePageUrl", ""),
            "cover": res,
        }
    return None


def buscar_imagem_noticia(
    titulo: str = "",
    tema: str | None = None,
    categoria: str | None = None,
    url_fonte: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Função de compatibilidade para notícias, tentando primeiro og:image e depois os bancos.
    """
    if url_fonte:
        try:
            import httpx
            resp = httpx.get(url_fonte, timeout=8, follow_redirects=True)
            if resp.status_code == 200:
                match = re.search(r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']", resp.text, re.IGNORECASE)
                if match:
                    img_url = match.group(1)
                    return {
                        "imagem_url": img_url,
                        "imagem_fonte": "RSS (og:image)",
                        "imagem_query": url_fonte,
                        "imagem_alt": "Imagem da notícia original",
                        "imagem_autor": "Fonte original",
                        "imagem_link": url_fonte,
                    }
        except Exception:
            pass

    return buscar_imagem_capa(titulo=titulo, tema=tema, categoria=categoria)
