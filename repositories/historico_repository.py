"""Histórico, fila e custo do agente; sem conexão automática com produção."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


_STATUSES = {"planned", "generated", "rejected", "sent", "published", "unpublished", "error"}


@dataclass
class HistoricoRepository:
    """Implementação em memória para dry-run e testes.

    A persistência SQL fica descrita em ``db/schema_agente.sql``; uma conexão
    só deverá ser ligada em uma etapa operacional posterior, com banco de teste.
    """

    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    generations: list[dict[str, Any]] = field(default_factory=list)
    queue: list[dict[str, Any]] = field(default_factory=list)
    costs: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def reservar_pauta(self, *, content_type: str, topic: str, topic_slug: str, run_id: str,
                       subcategory_slug: str | None = None) -> bool:
        if any(g["content_type"] == content_type and g["topic_slug"] == topic_slug for g in self.generations):
            return False
        agora = _agora()
        self.generations.append({
            "run_id": run_id, "content_type": content_type, "topic": topic,
            "topic_slug": topic_slug, "subcategory_slug": subcategory_slug,
            "status": "planned", "attempts": 0, "created_at": agora, "updated_at": agora,
        })
        return True

    def atualizar_status(self, topic_slug: str, status: str, **dados: Any) -> None:
        if status not in _STATUSES:
            raise ValueError(f"status inválido: {status!r}")
        item = self._generation(topic_slug)
        item.update(dados, status=status, updated_at=_agora())

    def registrar_custo(self, component: str, amount_usd: float, units: int, *, day: str | None = None) -> None:
        if component not in {"llm", "search", "image"}:
            raise ValueError(f"componente inválido: {component!r}")
        chave = (day or date.today().isoformat(), component)
        atual = self.costs.setdefault(chave, {"day": chave[0], "component": component, "amount_usd": 0.0, "units": 0})
        atual["amount_usd"] += float(amount_usd)
        atual["units"] += int(units)

    def proxima_pauta(self) -> dict[str, Any] | None:
        disponiveis = [x for x in self.queue if x.get("status") == "queued"]
        if not disponiveis:
            return None
        item = sorted(disponiveis, key=lambda x: (-int(x.get("priority", 0)), x.get("earliest_date") or ""))[0]
        item["status"] = "taken"
        return dict(item)

    def resumo_cobertura(self) -> dict[str, int]:
        resumo: dict[str, int] = {}
        for item in self.generations:
            chave = item.get("subcategory_slug") or ""
            resumo[chave] = resumo.get(chave, 0) + 1
        return resumo

    def _generation(self, topic_slug: str) -> dict[str, Any]:
        for item in self.generations:
            if item["topic_slug"] == topic_slug:
                return item
        raise KeyError(f"pauta não encontrada: {topic_slug!r}")


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()
