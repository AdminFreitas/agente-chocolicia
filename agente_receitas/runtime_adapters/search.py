from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
import httpx
from agente_receitas.services.busca_service import ResultadoBusca, Buscador, dominio_permitido

@dataclass
class BraveSearch:
    api_key: str
    timeout: float = 20.0
    nome: str = "brave"

    def buscar(self, consulta: str, dominios: Sequence[str], max_resultados: int) -> list[ResultadoBusca]:
        if not self.api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY não configurada")
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": consulta, "count": min(max_resultados, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("web", {}).get("results", [])
        output = []
        for item in results:
            url = item.get("url", "")
            result = ResultadoBusca(url=url, titulo=item.get("title", ""))
            if url and (not dominios or dominio_permitido(result.dominio, dominios)):
                output.append(result)
        return output[:max_resultados]
