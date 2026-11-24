"""
services/image_providers/wikimedia.py — Adaptador para o Wikimedia Commons.

Mudança de licença: antes, licença ausente virava "CC-BY-SA" por padrão e só "NC"
era recusada. Agora a licença vem como o Commons informa (ou vazia) e a decisão é
de services/image_providers/licencas.py (recusa NC, ND, SA e desconhecida).
"""

import logging
import os
import re
from typing import List

import httpx

from agente_receitas.services.image_providers.base import ImageProvider, StandardImageResult, user_agent

log = logging.getLogger(__name__)


class WikimediaProvider(ImageProvider):
    """Provedor de imagens Wikimedia Commons."""

    ENDPOINT = "https://commons.wikimedia.org/w/api.php"
    IMAGE_HOSTS = ("upload.wikimedia.org",)  # NÃO VERIFICADO (ver base.py)

    def __init__(self):
        enabled_env = os.getenv("WIKIMEDIA_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="wikimedia", enabled=enabled_env)
        self.timeout = 15

    def is_available(self) -> bool:
        return self.enabled

    @staticmethod
    def _limpar_html(raw_html: str) -> str:
        if not raw_html:
            return ""
        return " ".join(re.sub(r"<[^>]+>", "", raw_html).split())

    def search(self, query: str, limit: int = 10, min_width: int = 1280, lang: str = "pt", **kwargs) -> List[StandardImageResult]:
        if not self.is_available():
            return []
        query_limpa = query.strip()
        if not query_limpa:
            return []

        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query_limpa} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": min(max(limit, 5), 25),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        }
        try:
            resp = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                log.warning("Wikimedia: HTTP %s", resp.status_code)
                return []
            paginas = resp.json().get("query", {}).get("pages", {})

            results: List[StandardImageResult] = []
            for page_id, page in paginas.items():
                titulo = page.get("title", "").replace("File:", "")
                infos = page.get("imageinfo", [])
                if not infos:
                    continue
                ii = infos[0]
                img_url = ii.get("url")
                if not img_url:
                    continue
                w, h = ii.get("width", 0) or 0, ii.get("height", 0) or 0
                if min_width > 0 and 0 < w < min_width:
                    continue
                ext = ii.get("extmetadata", {})
                autor = self._limpar_html(ext.get("Artist", {}).get("value", ""))
                lic = ext.get("LicenseShortName", {}).get("value", "")
                desc = self._limpar_html(ext.get("ImageDescription", {}).get("value", "")) or titulo
                results.append(StandardImageResult(
                    provider="wikimedia",
                    provider_image_id=str(page_id),
                    title=desc[:160],
                    original_image_url=img_url,
                    original_page_url=ii.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{page.get('title')}",
                    photographer=autor[:100],
                    photographer_url=None,
                    license=lic,
                    license_url=ext.get("LicenseUrl", {}).get("value"),
                    attribution_text=f"Foto: {autor[:60]} via Wikimedia Commons ({lic})" if autor and lic else "",
                    width=w,
                    height=h,
                    search_query=query_limpa,
                    raw_data=page,
                ))
            return results
        except Exception as exc:
            log.warning("Wikimedia: falha na busca (%s)", type(exc).__name__)
            return []
