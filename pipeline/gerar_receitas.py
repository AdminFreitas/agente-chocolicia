"""Orquestração segura da execução de receitas."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from validators import ResultadoValidacao, validar_conteudo


@dataclass(frozen=True)
class ResultadoExecucao:
    tipo: str
    estado: str
    dry_run: bool
    target: str
    fase: int
    mensagem: str
    payload: dict[str, Any] | None = None


def validar_por_ponto_unico(conteudo: dict, contexto: dict | None = None) -> ResultadoValidacao:
    return validar_conteudo(conteudo, contexto)


def executar_modo_teste(
    tipo: str, *, dry_run: bool = True, target: str = "preview", fase: int = 0,
    validador: Callable[[dict, dict | None], ResultadoValidacao] = validar_por_ponto_unico,
) -> ResultadoExecucao:
    if tipo not in {"receita", "dica"}:
        raise ValueError("tipo deve ser receita ou dica")
    if target not in {"preview", "producao"}:
        raise ValueError("target deve ser preview ou producao")
    if fase not in range(4):
        raise ValueError("fase deve estar entre 0 e 3")
    validador({}, {"modo_teste": True})
    return ResultadoExecucao(
        tipo, "simulado", True, target, fase,
        "fontes simuladas; geração real depende de provedor de pesquisa e LLM",
    )
