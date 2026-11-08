"""
services/image_providers/wikimedia.py — Adaptador para o Wikimedia Commons.
"""

import os
import re
from typing import Any, Dict, List, Optional
import httpx

from services.image_providers.base import ImageProvider, StandardImageResult


class WikimediaProvider(ImageProvider):
    """Provedor de imagens Wikimedia Commons (conteúdos educativos, matérias, técnicas e receitas)."""

    ENDPOINT = "https://commons.wikimedia.org/w/api.php"

    def __init__(self):
        enabled_env = os.getenv("WIKIMEDIA_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="wikimedia", enabled=enabled_env)
        self.timeout = 15

    def is_available(self) -> bool:
        return self.enabled

    def _limpar_html(self, raw_html: str) -> str:
        if not raw_html:
            return ""
        limpo = re.sub(r"<[^>]+>", "", raw_html)
        return " ".join(limpo.split())

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
            "User-Agent": "ChocoliciaBot/1.0 (contact@chocolicia.com)",
            "Accept": "application/json",
        }

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query_limpa} filetype:bitmap",
            "gsrnamespace": 6,  # 6 = Namespace de arquivos de mídia
            "gsrlimit": min(max(limit, 5), 25),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        }

        try:
            resp = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                print(f"[Wikimedia] Erro HTTP {resp.status_code}")
                return []

            dados = resp.json()
            pages = dados.get("query", {}).get("pages", {})
            results: List[StandardImageResult] = []

            for page_id, page_data in pages.items():
                title = page_data.get("title", "").replace("File:", "")
                image_info_list = page_data.get("imageinfo", [])
                if not image_info_list:
                    continue

                ii = image_info_list[0]
                img_url = ii.get("url")
                if not img_url:
                    continue

                w = ii.get("width", 0)
                h = ii.get("height", 0)
                if min_width > 0 and w > 0 and w < min_width:
                    continue

                ext = ii.get("extmetadata", {})
                artist_raw = ext.get("Artist", {}).get("value", "")
                artist = self._limpar_html(artist_raw) or "Autor Wikimedia"
                
                license_short = ext.get("LicenseShortName", {}).get("value", "CC-BY-SA")
                license_url = ext.get("LicenseUrl", {}).get("value", "https://creativecommons.org/")

                # Validação de licença: rejeita licenças NC (não comerciais)
                lic_lower = license_short.lower()
                if "nc" in lic_lower:
                    continue

                page_url = ii.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{page_data.get('title')}"
                desc_raw = ext.get("ImageDescription", {}).get("value", "")
                desc = self._limpar_html(desc_raw) or title

                item = StandardImageResult(
                    provider="wikimedia",
                    provider_image_id=str(page_id),
                    title=desc[:160],
                    original_image_url=img_url,
                    original_page_url=page_url,
                    photographer=artist[:100],
                    photographer_url=None,
                    license=license_short,
                    license_url=license_url,
                    attribution_text=f"Foto: {artist[:60]} via Wikimedia Commons ({license_short})",
                    width=w,
                    height=h,
                    is_commercial_friendly=True,
                    tags=[],
                    search_query=query_limpa,
                    raw_data=page_data,
                )
                results.append(item)

            return results

        except Exception as e:
            print(f"[Wikimedia] Falha ao pesquisar '{query}': {e}")
            return []

