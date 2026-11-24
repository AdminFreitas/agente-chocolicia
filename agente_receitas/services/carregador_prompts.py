"""
carregador_prompts.py — prompts em camadas (docs/03-PROMPT-SISTEMA.md §2 e §10).

Camadas: [1] base  [2] módulo do tipo  [3] dados da pesquisa (delimitados, como
DADO)  [4] contrato de saída. Os prompts vivem em prompts/*.md, com a primeira
linha "versao: X.Y.Z" (03 §2 regra 1). Nada de texto de prompt no código.

Substituição de {{MARCADORES}} em UMA passada: o valor inserido nunca é relido,
então texto de terceiros (ficha, resposta anterior) não consegue injetar outro
marcador.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PASTA_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
_VERSAO = re.compile(r"^versao:\s*(\d+\.\d+\.\d+)\s*$", re.IGNORECASE)
_MARCADOR = re.compile(r"\{\{([A-Z_]+)\}\}")


class PromptInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    nome: str
    versao: str
    texto: str


def carregar(nome: str, pasta: Path | str = PASTA_PROMPTS) -> Prompt:
    caminho = Path(pasta) / f"{nome}.md"
    if not caminho.is_file():
        raise PromptInvalido(f"prompt inexistente: {caminho.name}")
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    m = _VERSAO.match(linhas[0]) if linhas else None
    if not m:
        raise PromptInvalido(f"{caminho.name}: a primeira linha deve ser 'versao: X.Y.Z'")
    return Prompt(nome, m.group(1), "\n".join(linhas[1:]).strip("\n"))


def json_seguro(obj: Any) -> str:
    """JSON válido em que '<' vira \\u003c: o dado não consegue fechar um delimitador."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).replace("<", "\\u003c")


def renderizar(prompt: Prompt, **valores: str) -> str:
    esperados = set(_MARCADOR.findall(prompt.texto))
    if esperados != set(valores):
        raise PromptInvalido(
            f"{prompt.nome}: marcadores {sorted(esperados)} != valores {sorted(valores)}"
        )
    return _MARCADOR.sub(lambda m: valores[m.group(1)], prompt.texto)


def contrato_saida(modelo) -> str:
    """Esquema JSON do tipo (03 §2 camada 4), a partir do modelo Pydantic."""
    return json.dumps(modelo.model_json_schema(), ensure_ascii=False, separators=(",", ":"))


def montar_criacao(
    tipo_conteudo: str,
    modulo: str,
    pauta: dict,
    ficha: dict,
    modelo_saida,
    categorias_validas: list[str] | None = None,
) -> tuple[str, dict[str, str]]:
    """
    Monta o prompt de criação: base + módulo + entrada (formato de 03 §10).
    A ficha entra como DADO, sem o detalhe interno do gate. Devolve (prompt, versões).
    """
    base, mod = carregar("base"), carregar(modulo)
    dados = {k: v for k, v in ficha.items() if k != "gate"}
    pauta_min = {
        k: pauta.get(k)
        for k in ("tema", "assunto", "categoria", "subcategoria", "ocasiao", "dieta", "dificuldade_alvo", "observacoes")
        if k in pauta
    }
    if categorias_validas:
        lista = "\n".join(categorias_validas)
    else:  # PENDENTE: config/categorias.json não existe; vale a subcategoria fixa da pauta
        sub = pauta.get("subcategoria")
        lista = f"{sub} (fixa pela pauta; não alterar)" if sub else "nenhuma (esta pauta não tem subcategoria; deixe vazia)"
    entrada = (
        f"TIPO DE CONTEÚDO: {tipo_conteudo}\n\n"
        f"PAUTA\n{json_seguro(pauta_min)}\n\n"
        f"<dados_pesquisa>\n{json_seguro(dados)}\n</dados_pesquisa>\n\n"
        f"LISTA DE CATEGORIAS VÁLIDAS\n{lista}\n\n"
        f"CONTRATO DE SAÍDA\n{contrato_saida(modelo_saida)}\n\n"
        "Responda somente com o objeto JSON."
    )
    prompt = f"{base.texto}\n\n{mod.texto}\n\n{entrada}"
    return prompt, {base.nome: base.versao, mod.nome: mod.versao}


def versao_composta(versoes: dict[str, str]) -> str:
    """Valor para generationMeta.prompt_version (06 §6.2), ex.: 'base@1.0.0+receita@1.1.0'."""
    return "+".join(f"{n}@{v}" for n, v in versoes.items())
