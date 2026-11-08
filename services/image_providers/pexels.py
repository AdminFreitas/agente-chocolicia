"""
services/image_providers/pexels.py — Adaptador para o banco de imagens Pexels.
"""

import os
from typing import List, Optional
import httpx

from services.image_providers.base import ImageProvider, StandardImageResult


class PexelsProvider(ImageProvider):
    """Provedor de imagens Pexels (fonte complementar de alta qualidade fotográfica)."""

    ENDPOINT = "https://api.pexels.com/v1/search"

    def __init__(self):
        enabled_env = os.getenv("PEXELS_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="pexels", enabled=enabled_env)
        self.api_key = os.getenv("PEXELS_API_KEY", "").strip()
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

        query_limpa = query.strip()
        if not query_limpa:
            return []

        headers = {
            "Authorization": self.api_key,
            "User-Agent": "ChocoliciaAgent/1.0 (+https://chocolicia.com)",
        }

        locale = "pt-BR" if lang == "pt" else "en-US"
        params = {
            "query": query_limpa,
            "per_page": min(max(limit, 3), 30),
            "orientation": "landscape",
            "locale": locale,
        }

        try:
            resp = httpx.get(self.ENDPOINT, headers=headers, params=params, timeout=self.timeout)
            
            # Se não houver fotos em pt-BR, tenta busca sem locale / en-US
            if resp.status_code == 200 and not resp.json().get("photos") and locale == "pt-BR":
                params["locale"] = "en-US"
                resp = httpx.get(self.ENDPOINT, headers=headers, params=params, timeout=self.timeout)

            if resp.status_code == 200:
                dados = resp.json()
                photos = dados.get("photos", [])
                results: List[StandardImageResult] = []

                for p in photos:
                    src = p.get("src", {})
                    img_url = src.get("large2x") or src.get("original") or src.get("large")
                    if not img_url:
                        continue

                    w = p.get("width", 0)
                    h = p.get("height", 0)
                    if min_width > 0 and w > 0 and w < min_width:
                        continue

                    photographer = p.get("photographer", "Pexels Photographer")
                    photo_url = p.get("url", "https://www.pexels.com")
                    alt_desc = p.get("alt") or query_limpa

                    item = StandardImageResult(
                        provider="pexels",
                        provider_image_id=str(p.get("id")),
                        title=alt_desc,
                        original_image_url=img_url,
                        original_page_url=photo_url,
                        photographer=photographer,
                        photographer_url=p.get("photographer_url"),
                        license="Pexels License",
                        license_url="https://www.pexels.com/license/",
                        attribution_text=f"Foto por {photographer} no Pexels",
                        width=w,
                        height=h,
                        is_commercial_friendly=True,
                        tags=[],
                        search_query=query_limpa,
                        raw_data=p,
                    )
                    results.append(item)

                return results

            elif resp.status_code == 429:
                print("[Pexels] Erro 429: Rate limit atingido.")
                return []
            else:
                print(f"[Pexels] Erro HTTP {resp.status_code}: {resp.text[:150]}")
                return []

        except Exception as e:
            print(f"[Pexels] Falha ao pesquisar '{query}': {e}")
            return []

