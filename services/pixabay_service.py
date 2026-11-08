"""
services/pixabay_service.py — Integração com a API do Pixabay para busca de imagens culinárias.

Implementado conforme a documentação oficial da API do Pixabay:
- Endpoint: https://pixabay.com/api/
- Suporte a busca em português (lang="pt") com fallback para inglês (lang="en")
- Filtro por categoria "food", tipo "photo", orientação "horizontal", safesearch ativo
- Largura mínima de imagem (1280px para alta resolução de capa)
- Cache em memória de 24 horas para conformidade com as diretrizes do Pixabay
- Formatação de proveniência completa para o contrato do Chocolícia (06-INTEGRACAO.md)
"""

import os
import re
import time
import random
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import httpx

# Chave de API do Pixabay
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
PIXABAY_ENDPOINT = "https://pixabay.com/api/"
CACHE_TTL_SECS = 24 * 3600  # 24 horas conforme especificação do Pixabay
TIMEOUT = 12

# Cache simples em memória com expiração
_query_cache: Dict[str, Dict[str, Any]] = {}

# Mapeamento culinário de termos frequentes de confeitaria (PT -> EN) para busca enriquecida
TERMOS_CULINARIOS_PT_EN = {
    "bolo": "cake",
    "bolos": "cakes",
    "bolo de chocolate": "chocolate cake",
    "bolo de cenoura": "carrot cake",
    "torta": "pie tart",
    "tortas": "pies tarts",
    "torta holandesa": "chocolate cream pie",
    "torta de limao": "lemon pie tart",
    "torta de morango": "strawberry tart",
    "brigadeiro": "chocolate truffles fudge",
    "brigadeiros": "chocolate truffles",
    "trufa": "chocolate truffle",
    "trufas": "chocolate truffles",
    "bombom": "chocolate bonbon",
    "brownie": "chocolate brownie",
    "cupcake": "cupcake",
    "cupcakes": "cupcakes",
    "pudim": "caramel flan pudding",
    "mousse": "chocolate mousse",
    "pao de mel": "gingerbread honey cake",
    "cookies": "chocolate chip cookies",
    "biscoito": "cookies biscuits",
    "doce": "sweet dessert",
    "doces": "desserts sweets",
    "sobremesa": "dessert",
    "sobremesas": "desserts",
    "chocolate": "chocolate dessert",
    "calda": "chocolate syrup ganache",
    "ganache": "chocolate ganache",
    "morango": "strawberry",
    "baunilha": "vanilla dessert",
    "confeitaria": "pastry confectionery bakery",
}

# Stopwords em português para limpeza de títulos de receitas
STOPWORDS_CULINARIA = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob",
    "sobre", "e", "ou", "que", "se", "como", "facil", "fácil", "rapido", "rápido",
    "caseiro", "caseira", "delicioso", "deliciosa", "simples", "perfeito", "perfeita",
    "melhor", "tradicional", "receita", "passo", "tudo", "mais", "muito",
}


def _limpar_termo(texto: str) -> str:
    """Remove caracteres especiais e normaliza espaços."""
    if not texto:
        return ""
    limpo = re.sub(r"[^\w\s-]", " ", texto, flags=re.UNICODE)
    return " ".join(limpo.split())


def _extrair_termos_busca(titulo: str, categoria: str = "", subcategoria: str = "") -> List[str]:
    """
    Gera uma lista ordenada de queries candidatas da mais específica para a mais genérica.
    """
    queries = []
    
    # 1. Título limpo sem stopwords
    palavras = _limpar_termo(titulo).lower().split()
    palavras_chave = [p for p in palavras if p not in STOPWORDS_CULINARIA and len(p) > 2]
    if palavras_chave:
        query_titulo = " ".join(palavras_chave[:4])
        queries.append(query_titulo)

    # 2. Subcategoria (ex: "Bolo de Chocolate", "Trufas e Bombons")
    if subcategoria:
        queries.append(_limpar_termo(subcategoria).lower())

    # 3. Categoria principal
    if categoria:
        queries.append(_limpar_termo(categoria).lower())

    # 4. Tradução para inglês se houver correspondência
    titulo_lower = titulo.lower()
    for pt, en in TERMOS_CULINARIOS_PT_EN.items():
        if pt in titulo_lower:
            queries.append(en)
            break

    # 5. Fallback culinário temático do Chocolícia
    queries.append("chocolate dessert")

    # Remove duplicadas mantendo ordem
    vistos = set()
    ordenadas = []
    for q in queries:
        if q and q not in vistos:
            vistos.add(q)
            ordenadas.append(q)
    return ordenadas


def buscar_pixabay(
    query: str,
    lang: str = "pt",
    categoria: str = "food",
    image_type: str = "photo",
    orientation: str = "horizontal",
    min_width: int = 1280,
    per_page: int = 15,
) -> Optional[List[Dict[str, Any]]]:
    """
    Executa busca na API do Pixabay com cache de 24 horas.
    Retorna a lista de 'hits' ou None em caso de erro ou sem resultados.
    """
    if not PIXABAY_API_KEY:
        print("[Pixabay] AVISO: PIXABAY_API_KEY não configurada.")
        return None

    chave_cache = f"{query.strip().lower()}|{lang}|{categoria}|{min_width}"
    agora = time.time()

    # Verifica cache de 24 horas
    if chave_cache in _query_cache:
        entrada = _query_cache[chave_cache]
        if agora - entrada["timestamp"] < CACHE_TTL_SECS:
            return entrada["data"]

    params = {
        "key": PIXABAY_API_KEY,
        "q": query[:100],  # Limite máximo de 100 caracteres exigido pela API
        "lang": lang,
        "image_type": image_type,
        "orientation": orientation,
        "safesearch": "true",
        "order": "popular",
        "per_page": min(max(per_page, 3), 100),
    }

    if categoria:
        params["category"] = categoria
    if min_width > 0:
        params["min_width"] = min_width

    headers = {
        "User-Agent": "ChocoliciaAgent/1.0 (+https://chocolicia.com)",
        "Accept": "application/json",
    }

    try:
        resp = httpx.get(PIXABAY_ENDPOINT, params=params, headers=headers, timeout=TIMEOUT)
        
        # Log dos limites de taxa se disponíveis
        rate_limit = resp.headers.get("X-RateLimit-Limit")
        rate_remaining = resp.headers.get("X-RateLimit-Remaining")
        if rate_remaining and int(rate_remaining) < 10:
            print(f"[Pixabay] Atenção: limite de requisições baixo: {rate_remaining}/{rate_limit}")

        if resp.status_code == 200:
            dados = resp.json()
            hits = dados.get("hits", [])
            _query_cache[chave_cache] = {"timestamp": agora, "data": hits}
            return hits
        elif resp.status_code == 429:
            reset_time = resp.headers.get("X-RateLimit-Reset", "60")
            print(f"[Pixabay] ERRO 429: Limite excedido. Reset em {reset_time}s.")
            return None
        else:
            print(f"[Pixabay] Erro HTTP {resp.status_code}: {resp.text[:200]}")
            return None

    except httpx.TimeoutException:
        print(f"[Pixabay] Timeout ao buscar '{query}'")
        return None
    except Exception as e:
        print(f"[Pixabay] Exceção na busca '{query}': {e}")
        return None


def buscar_imagem_receita(
    titulo: str,
    categoria: str = "",
    subcategoria: str = "",
    tags: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca a melhor imagem para uma receita no Pixabay e monta a estrutura
    exata de proveniência exigida pelo contrato do Chocolícia.

    Retorno no formato do contrato da API Chocolícia (seção 7 e 8.8):
    {
        "mode": "stock",
        "provider": "pixabay",
        "sourceImageUrl": "https://pixabay.com/get/...",
        "sourcePageUrl": "https://pixabay.com/pt/photos/...",
        "author": "Nome do autor",
        "license": "Pixabay Content License",
        "attributionText": "Foto: Autor via Pixabay",
        "coverImageAlt": "Descrição acessível",
        ...
    }
    """
    queries = _extrair_termos_busca(titulo, categoria, subcategoria)

    for query in queries:
        print(f"[Pixabay] Buscando imagem para receita: '{query}' (pt)...")
        # 1. Tenta em português com categoria "food" e min_width=1280
        hits = buscar_pixabay(query, lang="pt", categoria="food", min_width=1280)

        # 2. Se não encontrar, tenta em português sem filtro estrito de categoria
        if not hits:
            hits = buscar_pixabay(query, lang="pt", categoria="", min_width=1280)

        # 3. Se ainda não encontrar, tenta busca em inglês
        if not hits:
            # Traduz termo se possível
            query_en = TERMOS_CULINARIOS_PT_EN.get(query, query)
            print(f"[Pixabay] Tentando fallback em inglês: '{query_en}'...")
            hits = buscar_pixabay(query_en, lang="en", categoria="food", min_width=1280)

        if hits:
            # Seleciona o melhor hit: prefere com boa contagem de curtidas ou downloads
            # e garante que imageWidth >= 1280
            candidatos_validos = [
                h for h in hits
                if h.get("imageWidth", 0) >= 1280 or h.get("webformatWidth", 0) >= 640
            ]
            
            if not candidatos_validos:
                candidatos_validos = hits

            # Ordena por downloads/likes para escolher uma foto atraente e de alta qualidade
            candidatos_validos.sort(key=lambda x: (x.get("downloads", 0) + x.get("likes", 0)), reverse=True)
            foto = candidatos_validos[0]

            # URL da imagem: prefere largeImageURL (1280px), fullHDURL (1920px), ou webformatURL
            imagem_url = (
                foto.get("largeImageURL")
                or foto.get("fullHDURL")
                or foto.get("imageURL")
                or foto.get("webformatURL")
            )
            
            if not imagem_url:
                continue

            autor = foto.get("user", "Colaborador Pixabay")
            page_url = foto.get("pageURL", "https://pixabay.com")
            
            # Texto alternativo acessível (SEO e acessibilidade conforme 08-VALIDACAO.md IMG-08)
            alt_text = f"{titulo} servido, com acabamento refinado"
            if len(alt_text) < 15:
                alt_text = f"Prato de {titulo} pronto para consumo"

            return {
                "mode": "stock",
                "provider": "pixabay",
                "sourceImageUrl": imagem_url,
                "sourcePageUrl": page_url,
                "author": autor,
                "authorUrl": f"https://pixabay.com/users/{foto.get('user')}-{foto.get('user_id')}/" if foto.get("user_id") else page_url,
                "license": "Pixabay Content License",
                "attributionText": f"Foto: {autor} via Pixabay",
                "coverImageAlt": alt_text,
                "width": foto.get("imageWidth"),
                "height": foto.get("imageHeight"),
                "pixabayId": foto.get("id"),
                "tags": foto.get("tags", ""),
                "query": query,
            }

    print(f"[Pixabay] Nenhuma imagem de qualidade encontrada para o título: '{titulo}'")
    return None
