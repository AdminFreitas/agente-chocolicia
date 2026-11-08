"""
services/image_providers/pixabay.py — Adaptador para o banco de imagens Pixabay.
"""

import os
import time
from typing import Any, Dict, List, Optional
import httpx

from services.image_providers.base import ImageProvider, StandardImageResult


class PixabayProvider(ImageProvider):
    """Provedor de imagens Pixabay (fonte prioritária)."""

    ENDPOINT = "https://pixabay.com/api/"
    CACHE_TTL_SECS = 24 * 3600  # 24 horas obrigatório pela política do Pixabay

    def __init__(self):
        enabled_env = os.getenv("PIXABAY_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="pixabay", enabled=enabled_env)
        self.api_key = os.getenv("PIXABAY_API_KEY", "").strip()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.timeout = 12

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def search(
        self,
        query: str,
        limit: int = 10,
        min_width: int = 1280,
        lang: str = "pt",
        **kwargs
    ) -> List[StandardImageResult]:
        if not self.is_available():
            return []

        query_limpa = query.strip()[:100]
        if not query_limpa:
            return []

        cache_key = f"{query_limpa.lower()}|{lang}|{min_width}"
        agora = time.time()

        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if agora - cache_entry["time"] < self.CACHE_TTL_SECS:
                return cache_entry["results"]

        params = {
            "key": self.api_key,
            "q": query_limpa,
            "lang": lang,
            "category": "food",
            "image_type": "photo",
            "orientation": "horizontal",
            "safesearch": "true",
            "order": "popular",
            "per_page": min(max(limit, 3), 50),
        }
        if min_width > 0:
            params["min_width"] = min_width

        headers = {
            "User-Agent": "ChocoliciaAgent/1.0 (+https://chocolicia.com)",
            "Accept": "application/json",
        }

        try:
            resp = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                dados = resp.json()
                hits = dados.get("hits", [])
                
                # Se não houver hits em português e lang era pt, tenta em inglês
                if not hits and lang == "pt":
                    params["lang"] = "en"
                    resp_en = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout)
                    if resp_en.status_code == 200:
                        hits = resp_en.json().get("hits", [])

                results: List[StandardImageResult] = []
                for hit in hits:
                    img_url = (
                        hit.get("largeImageURL")
                        or hit.get("fullHDURL")
                        or hit.get("imageURL")
                        or hit.get("webformatURL")
                    )
                    if not img_url:
                        continue

                    user = hit.get("user", "Pixabay Contributor")
                    user_id = hit.get("user_id")
                    user_url = f"https://pixabay.com/users/{user}-{user_id}/" if user_id else hit.get("pageURL")
                    tags_list = [t.strip() for t in hit.get("tags", "").split(",") if t.strip()]

                    item = StandardImageResult(
                        provider="pixabay",
                        provider_image_id=str(hit.get("id")),
                        title=hit.get("tags", query_limpa),
                        original_image_url=img_url,
                        original_page_url=hit.get("pageURL", "https://pixabay.com"),
                        photographer=user,
                        photographer_url=user_url,
                        license="Pixabay Content License",
                        license_url="https://pixabay.com/service/terms/",
                        attribution_text=f"Foto: {user} via Pixabay",
                        width=hit.get("imageWidth", 0),
                        height=hit.get("imageHeight", 0),
                        is_commercial_friendly=True,
                        tags=tags_list,
                        search_query=query_limpa,
                        raw_data=hit,
                    )
                    results.append(item)

                self._cache[cache_key] = {"time": agora, "results": results}
                return results

            elif resp.status_code == 429:
                print(f"[Pixabay] Erro 429: limite de requisições excedido.")
                return []
            else:
                print(f"[Pixabay] Erro HTTP {resp.status_code}")
                return []

        except Exception as e:
            print(f"[Pixabay] Falha ao pesquisar '{query}': {e}")
            return []

