"""
services/image_providers/openverse.py — Adaptador para o banco de imagens abertas Openverse.
"""

import os
from typing import List, Optional
import httpx

from services.image_providers.base import ImageProvider, StandardImageResult


class OpenverseProvider(ImageProvider):
    """Provedor de imagens Openverse (fonte complementar de Creative Commons)."""

    ENDPOINT = "https://api.openverse.org/v1/images/"
    # Licenças comerciais aceitas para o Chocolícia
    LICENCAS_COMERCIAIS_ACEITAS = {"cc0", "pdm", "by", "by-sa"}

    def __init__(self):
        enabled_env = os.getenv("OPENVERSE_ENABLED", "true").lower() in ("true", "1", "yes")
        super().__init__(name="openverse", enabled=enabled_env)
        self.timeout = 20  # API Openverse tem latência maior que outros provedores

    def is_available(self) -> bool:
        return self.enabled

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
            "User-Agent": "ChocoliciaAgent/1.0 (+https://chocolicia.com; contact@chocolicia.com)",
            "Accept": "application/json",
        }

        # Solicita explicitamente licenças comerciais/modificáveis
        params = {
            "q": query_limpa,
            "page_size": min(max(limit, 5), 30),
            "license_type": "commercial,modification",
        }

        try:
            resp = httpx.get(
                self.ENDPOINT,
                params=params,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )

            if resp.status_code == 200:
                dados = resp.json()
                results_raw = dados.get("results", []) if isinstance(dados, dict) else []
                results: List[StandardImageResult] = []

                for r in results_raw:
                    lic = (r.get("license") or "").lower()
                    
                    # Filtro de segurança: rejeita expressamente licenças não-comerciais
                    if "nc" in lic or "nd" in lic:
                        continue
                    if lic not in self.LICENCAS_COMERCIAIS_ACEITAS:
                        continue

                    img_url = r.get("url") or r.get("thumbnail")
                    if not img_url:
                        continue

                    w = r.get("width") or 0
                    h = r.get("height") or 0
                    if min_width > 0 and w > 0 and w < min_width:
                        continue

                    creator = r.get("creator") or "Autor desconhecido"
                    page_url = r.get("foreign_landing_url") or r.get("url") or "https://openverse.org"
                    lic_version = r.get("license_version", "")
                    lic_nome = f"CC {lic.upper()} {lic_version}".strip()
                    lic_url = r.get("license_url") or f"https://creativecommons.org/licenses/{lic}/"

                    item = StandardImageResult(
                        provider="openverse",
                        provider_image_id=str(r.get("id")),
                        title=r.get("title") or query_limpa,
                        original_image_url=img_url,
                        original_page_url=page_url,
                        photographer=creator,
                        photographer_url=r.get("creator_url"),
                        license=lic_nome,
                        license_url=lic_url,
                        attribution_text=f'"{r.get("title") or query_limpa}" por {creator} sob {lic_nome}',
                        width=w,
                        height=h,
                        is_commercial_friendly=True,
                        tags=[t.get("name", "") for t in r.get("tags", []) if isinstance(t, dict)],
                        search_query=query_limpa,
                        raw_data=r,
                    )
                    results.append(item)

                return results
            else:
                print(f"[Openverse] Erro HTTP {resp.status_code}")
                return []

        except Exception as e:
            print(f"[Openverse] Falha ao pesquisar '{query}': {e}")
            return []

