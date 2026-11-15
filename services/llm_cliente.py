"""Adaptador mínimo e seguro sobre ``services.llm_service``.

O módulo não importa o serviço de LLM até a primeira chamada, evitando rede e
leitura de credenciais durante a importação.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class FamiliaNaoGarantida(RuntimeError):
    """Não foi possível provar que o modelo usado pertence a outra família."""


@dataclass(frozen=True)
class RespostaLLM:
    texto: str
    provedor: str
    modelo: str
    familia: str

    def info(self) -> dict[str, str]:
        return {
            "provedor": self.provedor,
            "modelo": self.modelo,
            "familia": self.familia,
        }


class GerarFn(Protocol):
    def __call__(
        self,
        tarefa: str,
        prompt: str,
        *,
        familia_excluida: str | None = None,
    ) -> RespostaLLM: ...


def extrair_json(texto: str) -> tuple[Any | None, str | None]:
    """Extrai um objeto/array JSON, aceitando cercas e texto ao redor."""
    if not isinstance(texto, str) or not texto.strip():
        return None, "resposta vazia; JSON esperado"
    bruto = texto.strip()
    if bruto.startswith("```"):
        linhas = bruto.splitlines()
        if linhas and linhas[0].lstrip().startswith("```"):
            linhas = linhas[1:]
        if linhas and lines[-1].strip() == "```":
            linhas = linhas[:-1]
        bruto = "\n".join(linhas).strip()
    inicio = next((i for i, c in enumerate(bruto) if c in "[{"), None)
    if inicio is None:
        return None, "resposta sem objeto ou array JSON"
    try:
        valor, _ = json.JSONDecoder().raw_decode(bruto[inicio:])
        return valor, None
    except json.JSONDecodeError as exc:
        return None, f"JSON inválido: {exc.msg} (posição {exc.pos})"


def _coletar_familias() -> set[str]:
    caminho = Path(__file__).resolve().parent.parent / "config" / "modelos_aprovados.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"não foi possível ler modelos aprovados: {exc}") from exc
    familias = {
        item.get("familia", "").strip()
        for modelos in dados.values()
        if isinstance(modelos, list)
        for item in modelos
        if isinstance(item, dict) and isinstance(item.get("familia"), str)
    }
    return {familia for familia in familias if familia}


def _validar_familia_excluida(familia_excluida: str) -> None:
    if not isinstance(familia_excluida, str) or not familia_excluida.strip():
        raise ValueError("familia_excluida deve ser uma família não vazia")
    if familia_excluida not in _coletar_familias():
        raise ValueError(f"família não aprovada em modelos_aprovados.json: {familia_excluida!r}")


def gerar_padrao(
    tarefa: str,
    prompt: str,
    *,
    familia_excluida: str | None = None,
) -> RespostaLLM:
    """Gera texto e metadados sem permitir revisão sem família verificável."""
    if familia_excluida is not None:
        _validar_familia_excluida(familia_excluida)

    from services import llm_service

    funcao = llm_service.gerar_texto_com_metadados
    parametros = inspect.signature(funcao).parameters
    if familia_excluida is not None and "familia_excluida" not in parametros:
        raise FamiliaNaoGarantida(
            "llm_service não aceita familia_excluida; não é possível garantir família diferente"
        )

    kwargs = {"familia_excluida": familia_excluida} if familia_excluida is not None else {}
    dados = funcao(tarefa, prompt, **kwargs)
    if not isinstance(dados, dict) or "texto" not in dados:
        raise ValueError("llm_service devolveu metadados incompletos: falta texto")
    resposta = RespostaLLM(
        texto=dados["texto"],
        provedor=dados.get("provedor", ""),
        modelo=dados.get("modelo", ""),
        familia=dados.get("familia", ""),
    )
    if familia_excluida is not None and (
        not resposta.familia or resposta.familia == familia_excluida
    ):
        raise FamiliaNaoGarantida(
            f"revisor devolveu família {resposta.familia!r}; excluída: {familia_excluida!r}"
        )
    return resposta
