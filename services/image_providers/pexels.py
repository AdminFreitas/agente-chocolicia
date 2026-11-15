"""
services/image_providers/pexels.py — Adaptador para o banco de imagens Pexels.
"""

import logging
import os
from typing import List

import httpx

from services.image_providers.base import ImageProvider, StandardImageResult, user_agent

log = logging.getLogger(__name__)


class PexelsProvider(ImageProvider):
    """Provedor de imagens Pexels (fotografia de alta qualidade)."""

    ENDPOINT = "https://api.pexels.com/v1/search"
    IMAGE_HOSTS = ("images.pexels.com",)  # NÃO VERIFICADO (ver base.py)

    def __init__(self):
        enabled_env = os.getenv("PEXELS_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="pexels", enabled=enabled_env)
        self.api_key = os.getenv("PEXELS_API_KEY", "").strip()
        self.timeout = 12

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def search(self, query: str, limit: int = 10, min_width: int = 1280, lang: str = "pt", **kwargs) -> List[StandardImageResult]:
        if not self.is_available():
            return []
        query_limpa = query.strip()
        if not query_limpa:
            return []

        headers = {"Authorization": self.api_key, "User-Agent": user_agent()}
        locale = "pt-BR" if lang == "pt" else "en-US"
        params = {
            "query": query_limpa,
            "per_page": min(max(limit, 3), 30),
            "orientation": "landscape",
            "locale": locale,
        }
        try:
            resp = httpx.get(self.ENDPOINT, headers=headers, params=params, timeout=self.timeout)
            if resp.status_code == 200 and not resp.json().get("photos") and locale == "pt-BR":
                params["locale"] = "en-US"
                resp = httpx.get(self.ENDPOINT, headers=headers, params=params, timeout=self.timeout)
            if resp.status_code == 429:
                log.warning("Pexels: rate limit atingido (429)")
                return []
            if resp.status_code != 200:
                log.warning("Pexels: HTTP %s", resp.status_code)
                return []

            results: List[StandardImageResult] = []
            for p in resp.json().get("photos", []):
                src = p.get("src", {})
                img_url = src.get("large2x") or src.get("original") or src.get("large")
                if not img_url:
                    continue
                w, h = p.get("width", 0) or 0, p.get("height", 0) or 0
                if min_width > 0 and 0 < w < min_width:
                    continue
                autor = p.get("photographer") or ""
                results.append(StandardImageResult(
                    provider="pexels",
                    provider_image_id=str(p.get("id")),
                    title=p.get("alt") or query_limpa,
                    original_image_url=img_url,
                    original_page_url=p.get("url", ""),
                    photographer=autor,
                    photographer_url=p.get("photographer_url"),
                    license="Pexels License",
                    license_url="https://www.pexels.com/license/",
                    attribution_text=f"Foto por {autor} no Pexels" if autor else "",
                    width=w,
                    height=h,
                    search_query=query_limpa,
                    raw_data=p,
                ))
            return results
        except Exception as exc:
            log.warning("Pexels: falha na busca (%s)", type(exc).__name__)
            return []
