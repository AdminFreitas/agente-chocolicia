"""
services/image_providers/openverse.py — Adaptador para o Openverse (Creative Commons).

O Openverse agrega imagens de vários sites; o host da imagem varia. Por isso este
provedor NÃO contribui com hosts para o filtro IMG-03 (IMAGE_HOSTS vazio): uma
candidata só passa se o host da imagem estiver na lista permitida por outro
motivo (ex.: upload.wikimedia.org). Definir os hosts aceitáveis é PENDENTE
(docs/06 §18).
"""

import logging
import os
from typing import List

import httpx

from services.image_providers.base import ImageProvider, StandardImageResult, user_agent

log = logging.getLogger(__name__)


class OpenverseProvider(ImageProvider):
    """Provedor de imagens Openverse."""

    ENDPOINT = "https://api.openverse.org/v1/images/"
    # IMG-01: CC0, domínio público e CC BY. By-SA, NC e ND são recusadas
    # (antes, "by-sa" constava aqui por engano).
    LICENCAS_ACEITAS = {"cc0", "pdm", "by"}
    IMAGE_HOSTS = ()

    def __init__(self):
        enabled_env = os.getenv("OPENVERSE_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="openverse", enabled=enabled_env)
        self.timeout = 20

    def is_available(self) -> bool:
        return self.enabled

    def search(self, query: str, limit: int = 10, min_width: int = 1280, lang: str = "pt", **kwargs) -> List[StandardImageResult]:
        if not self.is_available():
            return []
        query_limpa = query.strip()
        if not query_limpa:
            return []

        headers = {"User-Agent": user_agent(), "Accept": "application/json"}
        params = {
            "q": query_limpa,
            "page_size": min(max(limit, 5), 30),
            "license_type": "commercial,modification",
        }
        try:
            resp = httpx.get(self.ENDPOINT, params=params, headers=headers, timeout=self.timeout, follow_redirects=True)
            if resp.status_code != 200:
                log.warning("Openverse: HTTP %s", resp.status_code)
                return []
            dados = resp.json()
            brutos = dados.get("results", []) if isinstance(dados, dict) else []

            results: List[StandardImageResult] = []
            for r in brutos:
                lic = (r.get("license") or "").lower()
                if lic not in self.LICENCAS_ACEITAS:
                    continue
                img_url = r.get("url")  # a miniatura não serve: é pequena e vem do próprio Openverse
                if not img_url:
                    continue
                w, h = r.get("width") or 0, r.get("height") or 0
                if min_width > 0 and 0 < w < min_width:
                    continue
                titulo = r.get("title") or query_limpa
                criador = r.get("creator") or ""
                versao = r.get("license_version", "")
                prefixo = "CC " if lic == "by" else ""  # "CC0", "PDM" e "CC BY": sem duplicar o "CC"
                lic_nome = f"{prefixo}{lic.upper()} {versao}".strip()
                results.append(StandardImageResult(
                    provider="openverse",
                    provider_image_id=str(r.get("id")),
                    title=titulo,
                    original_image_url=img_url,
                    original_page_url=r.get("foreign_landing_url") or "",
                    photographer=criador,
                    photographer_url=r.get("creator_url"),
                    license=lic_nome,
                    license_url=r.get("license_url") or f"https://creativecommons.org/licenses/{lic}/",
                    attribution_text=f'"{titulo}" por {criador} sob {lic_nome}' if criador else "",
                    width=w,
                    height=h,
                    tags=[t.get("name", "") for t in r.get("tags", []) if isinstance(t, dict)],
                    search_query=query_limpa,
                    raw_data=r,
                ))
            return results
        except Exception as exc:
            log.warning("Openverse: falha na busca (%s)", type(exc).__name__)
            return []
