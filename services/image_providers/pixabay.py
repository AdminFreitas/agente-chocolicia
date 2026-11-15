"""
services/image_providers/pixabay.py — Adaptador para o banco de imagens Pixabay.
"""

import logging
import os
import time
from typing import Any, Dict, List

import httpx

from services.image_providers.base import ImageProvider, StandardImageResult, user_agent

log = logging.getLogger(__name__)


class PixabayProvider(ImageProvider):
    """Provedor de imagens Pixabay (fonte prioritária)."""

    ENDPOINT = "https://pixabay.com/api/"
    CACHE_TTL_SECS = 24 * 3600  # 24 horas, conforme a política do Pixabay
    IMAGE_HOSTS = ("pixabay.com", "cdn.pixabay.com")  # NÃO VERIFICADO (ver base.py)

    def __init__(self):
        enabled_env = os.getenv("PIXABAY_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="pixabay", enabled=enabled_env)
        self.api_key = os.getenv("PIXABAY_API_KEY", "").strip()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.timeout = 12

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def search(self, query: str, limit: int = 10, min_width: int = 1280, lang: str = "pt", **kwargs) -> List[StandardImageResult]:
        if not self.is_available():
            return []
        query_limpa = query.strip()[:100]
        if not query_limpa:
            return []

        cache_key = f"{query_limpa.lower()}|{lang}|{min_width}"
        agora = time.time()
        entrada = self._cache.get(cache_key)
        if entrada and agora - entrada["time"] < self.CACHE_TTL_SECS:
            return entrada["results"]

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
        headers = {"User-Agent": user_agent(), "Accept": "application/json"}

        try:
            resp = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code == 429:
                log.warning("Pixabay: limite de requisições excedido (429)")
                return []
            if resp.status_code != 200:
                log.warning("Pixabay: HTTP %s", resp.status_code)
                return []
            hits = resp.json().get("hits", [])
            if not hits and lang == "pt":
                params["lang"] = "en"
                resp_en = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout)
                if resp_en.status_code == 200:
                    hits = resp_en.json().get("hits", [])

            results: List[StandardImageResult] = []
            for hit in hits:
                img_url = (
                    hit.get("largeImageURL") or hit.get("fullHDURL")
                    or hit.get("imageURL") or hit.get("webformatURL")
                )
                if not img_url:
                    continue
                user = hit.get("user") or ""
                user_id = hit.get("user_id")
                user_url = f"https://pixabay.com/users/{user}-{user_id}/" if (user and user_id) else hit.get("pageURL")
                results.append(StandardImageResult(
                    provider="pixabay",
                    provider_image_id=str(hit.get("id")),
                    title=hit.get("tags", query_limpa),
                    original_image_url=img_url,
                    original_page_url=hit.get("pageURL", ""),
                    photographer=user,
                    photographer_url=user_url,
                    license="Pixabay Content License",
                    license_url="https://pixabay.com/service/terms/",
                    attribution_text=f"Foto: {user} via Pixabay" if user else "",
                    width=hit.get("imageWidth", 0) or 0,
                    height=hit.get("imageHeight", 0) or 0,
                    tags=[t.strip() for t in hit.get("tags", "").split(",") if t.strip()],
                    search_query=query_limpa,
                    raw_data=hit,
                ))
            self._cache[cache_key] = {"time": agora, "results": results}
            return results
        except Exception as exc:  # não registrar a mensagem: pode conter a URL com a chave
            log.warning("Pixabay: falha na busca (%s)", type(exc).__name__)
            return []
