from __future__ import annotations
from dataclasses import dataclass
import secrets
import httpx

@dataclass
class SiteCatalog:
    base_url: str
    token: str
    timeout: float = 20.0

    @property
    def disponivel(self) -> bool:
        return bool(self.base_url and self.token)

    def _get(self, path: str, *, auth_required: bool = True):
        if auth_required and not self.token:
            raise RuntimeError("Token de leitura do catálogo ausente")
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = httpx.get(
            self.base_url.rstrip("/") + path,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def ingredients(self):
        data = self._get("/api/catalog/ingredients")
        return data.get("items", data) if isinstance(data, dict) else data

    def taxonomy(self):
        data = self._get("/api/taxonomy", auth_required=False)
        return data.get("items", data) if isinstance(data, dict) else data

    def subcategoria_habilitada(self, slug: str, fase: int) -> bool:
        riscos = {0: {"low"}, 1: {"low"}, 2: {"low", "medium"}, 3: {"low", "medium", "high"}}
        if fase not in riscos:
            raise ValueError(f"fase inválida: {fase}")
        data = self.taxonomy()
        categorias = data.get("categories", data.get("items", [])) if isinstance(data, dict) else data
        if not isinstance(categorias, list):
            raise RuntimeError("resposta de /api/taxonomy fora do formato esperado")
        for categoria in categorias:
            if not isinstance(categoria, dict):
                continue
            for subcategoria in categoria.get("subcategories", []):
                if not isinstance(subcategoria, dict) or subcategoria.get("slug") != slug:
                    continue
                ativa = subcategoria.get("active") is True
                habilitada = subcategoria.get("agentEnabled", subcategoria.get("agent_enabled")) is True
                risco = subcategoria.get("riskLevel", subcategoria.get("risk_level"))
                return ativa and habilitada and risco in riscos[fase]
        return False

    def selecionar_subcategoria(self, fase: int, slug: str | None = None) -> dict:
        riscos = {0: {"low"}, 1: {"low"}, 2: {"low", "medium"}, 3: {"low", "medium", "high"}}
        if fase not in riscos:
            raise ValueError(f"fase inválida: {fase}")
        data = self.taxonomy()
        categorias = data.get("categories", data.get("items", [])) if isinstance(data, dict) else data
        if not isinstance(categorias, list):
            raise RuntimeError("resposta de /api/taxonomy fora do formato esperado")
        doces = [
            item for item in categorias
            if isinstance(item, dict) and item.get("slug") == "doces-e-sobremesas"
        ]
        if not doces:
            raise RuntimeError("a categoria doces-e-sobremesas não está disponível na taxonomia")
        candidatas = []
        for categoria in doces:
            for sub in categoria.get("subcategories", []):
                if not isinstance(sub, dict):
                    continue
                if (
                    sub.get("active") is True
                    and sub.get("agentEnabled", sub.get("agent_enabled")) is True
                    and sub.get("riskLevel", sub.get("risk_level")) in riscos[fase]
                ):
                    candidatas.append({
                        "category_slug": categoria["slug"],
                        "category_name": categoria["name"],
                        "subcategory_slug": sub["slug"],
                    })
        if slug:
            escolhida = next((item for item in candidatas if item["subcategory_slug"] == slug), None)
            if escolhida is None:
                raise ValueError(f"subcategoria '{slug}' não está habilitada para a fase {fase}")
            return escolhida
        if not candidatas:
            raise RuntimeError("nenhuma subcategoria de doces está habilitada para o agente")
        return secrets.choice(candidatas)

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
