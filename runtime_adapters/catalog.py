from __future__ import annotations
from dataclasses import dataclass
import httpx

@dataclass
class SiteCatalog:
    base_url: str
    token: str
    timeout: float = 20.0

    @property
    def disponivel(self) -> bool:
        return bool(self.base_url and self.token)

    def _get(self, path: str):
        if not self.token:
            raise RuntimeError("Token de leitura do catálogo ausente")
        response = httpx.get(
            self.base_url.rstrip("/") + path,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def ingredients(self):
        data = self._get("/api/catalog/ingredients")
        return data.get("items", data) if isinstance(data, dict) else data

    def taxonomy(self):
        data = self._get("/api/taxonomy")
        return data.get("items", data) if isinstance(data, dict) else data

    def coverage(self):
        return self._get("/api/coverage")

    def lookup_content(self, slug: str):
        from urllib.parse import quote
        return self._get(
            "/api/content/lookup?topic_slug=" + quote(slug, safe="")
        )

    def resolver(self, nome: str) -> dict | None:
        alvo = nome.strip().casefold()
        for item in self.ingredients():
            if not isinstance(item, dict):
                continue
            nomes = [item.get("name"), item.get("nome"), item.get("label")]
            aliases = item.get("aliases", [])
            if isinstance(aliases, list):
                nomes.extend(aliases)
            if any(isinstance(valor, str) and valor.strip().casefold() == alvo for valor in nomes):
                return item
        return None

    def existe(self, topic_slug: str, tema: str) -> bool:
        data = self.lookup_content(topic_slug)
        if isinstance(data, dict):
            return bool(data.get("exists", data.get("items")))
        return bool(data)
