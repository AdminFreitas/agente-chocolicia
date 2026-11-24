"""
llm_cliente.py — adaptador entre os agentes e services/llm_service.py.

Os agentes recebem uma função `gerar(tarefa, prompt, *, familia_excluida=None)`
que devolve RespostaLLM. Assim os testes usam um dublê e os agentes não
dependem das chaves nem do httpx.

Regra "revisor de família diferente" (docs/03 §12.3, 08 §1 item 6): falha
FECHADA. Se não for possível garantir que o revisor é de família diferente da
do gerador, levanta FamiliaNaoGarantida em vez de seguir. Isso vale quando:
  - o llm_service não aceita o parâmetro `familia_excluida`;
  - o llm_service não informa a família usada;
  - a família devolvida é a excluída ou não consta em modelos_aprovados.json.

`familia_excluida` é validado de forma fechada: só aceita famílias previstas em
config/modelos_aprovados.json. Valor de tipo inválido levanta TypeError; valor
desconhecido levanta ValueError. Nada é tratado em silêncio.

Sem rede, LLM ou leitura de arquivo no import. Prompts, tokens e chaves nunca
são registrados nem incluídos em mensagens de erro.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Protocol

_CAMINHO_MODELOS = Path(__file__).resolve().parent.parent / "config" / "modelos_aprovados.json"


class FamiliaNaoGarantida(RuntimeError):
    """Não é possível garantir que gerador e revisor sejam de famílias diferentes."""


@dataclass(frozen=True)
class RespostaLLM:
    texto: str
    provedor: str = ""
    modelo: str = ""
    familia: str = ""

    def info(self) -> dict:
        return {"provedor": self.provedor, "modelo": self.modelo, "familia": self.familia}


class GerarFn(Protocol):
    def __call__(self, tarefa: str, prompt: str, *, familia_excluida: str | None = None) -> RespostaLLM: ...


# ---------------------------------------------------------------------------
# Famílias aprovadas (config/modelos_aprovados.json)
# ---------------------------------------------------------------------------

def _coletar_familias(dados: object) -> set[str]:
    """
    PONTO ÚNICO que assume o formato de modelos_aprovados.json (ver "Perguntas").
    Reconhece: {"familias": [...] | {...}}, ou lista/dict de entradas com chave
    "familia". Formato não reconhecido => conjunto vazio (e o chamador falha).
    """
    familias: set[str] = set()
    if isinstance(dados, dict):
        bloco = dados.get("familias")
        if isinstance(bloco, list):
            familias.update(x for x in bloco if isinstance(x, str) and x)
        elif isinstance(bloco, dict):
            familias.update(k for k in bloco if isinstance(k, str) and k)
        for valor in dados.values():
            if isinstance(valor, (list, dict)):
                familias |= _familias_de_entradas(valor)
    elif isinstance(dados, list):
        familias |= _familias_de_entradas(dados)
    return familias


def _familias_de_entradas(valor: object) -> set[str]:
    itens = valor.values() if isinstance(valor, dict) else valor
    achadas: set[str] = set()
    for item in itens:
        if isinstance(item, dict):
            fam = item.get("familia")
            if isinstance(fam, str) and fam:
                achadas.add(fam)
            for sub in item.values():
                if isinstance(sub, (list, dict)):
                    achadas |= _familias_de_entradas(sub)
    return achadas


@lru_cache(maxsize=1)
def familias_aprovadas() -> frozenset[str]:
    try:
        dados = json.loads(_CAMINHO_MODELOS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FamiliaNaoGarantida(
            f"não foi possível ler {_CAMINHO_MODELOS.name} para validar famílias: {type(exc).__name__}"
        ) from exc
    familias = _coletar_familias(dados)
    if not familias:
        raise FamiliaNaoGarantida(
            f"{_CAMINHO_MODELOS.name} não contém nenhuma família reconhecível; "
            "não é possível garantir revisor de família diferente"
        )
    return frozenset(familias)


def validar_familia_excluida(familia: object) -> str:
    """Validação fechada: devolve a família se for str aprovada; senão levanta erro claro."""
    if not isinstance(familia, str):
        raise TypeError(f"familia_excluida deve ser str, recebido {type(familia).__name__}")
    if not familia:
        raise ValueError("familia_excluida não pode ser vazia")
    aprovadas = familias_aprovadas()
    if familia not in aprovadas:
        raise ValueError(f"familia_excluida desconhecida: {familia!r}; previstas: {sorted(aprovadas)}")
    return familia


# ---------------------------------------------------------------------------
# Implementação real
# ---------------------------------------------------------------------------

def gerar_padrao(tarefa: str, prompt: str, *, familia_excluida: str | None = None) -> RespostaLLM:
    if familia_excluida is not None:
        validar_familia_excluida(familia_excluida)  # falha antes de qualquer chamada externa

    import agente_receitas.services.llm_service as llm  # sob demanda: exige chaves e httpx

    funcao: Callable = llm.gerar_texto_com_metadados
    if familia_excluida is not None:
        if "familia_excluida" not in inspect.signature(funcao).parameters:
            raise FamiliaNaoGarantida(
                "llm_service não suporta familia_excluida (aplicar a mudança mínima proposta na Etapa 2)"
            )
        dados = funcao(tarefa, prompt, familia_excluida=familia_excluida)
    else:
        dados = funcao(tarefa, prompt)

    if not isinstance(dados, dict) or "texto" not in dados:
        raise RuntimeError("llm_service devolveu resposta sem o campo 'texto'")

    resposta = RespostaLLM(
        texto=dados["texto"],
        provedor=dados.get("provedor", ""),
        modelo=dados.get("modelo", ""),
        familia=dados.get("familia", ""),
    )

    if familia_excluida is not None:
        if not resposta.familia:
            raise FamiliaNaoGarantida("llm_service não informou a família usada pelo revisor")
        if resposta.familia == familia_excluida:
            raise FamiliaNaoGarantida(
                f"revisor usou a família excluída ({familia_excluida!r}); revisão independente não garantida"
            )
        if resposta.familia not in familias_aprovadas():
            raise FamiliaNaoGarantida(f"família devolvida não consta em modelos_aprovados.json: {resposta.familia!r}")
    return resposta


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

_CERCA = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\r?\n(.*?)\r?\n[ \t]*```", flags=re.DOTALL)


def extrair_json(texto: str) -> tuple[object | None, str | None]:
    """
    Devolve (objeto, None) ou (None, erro). Tenta, nesta ordem:
      1. a resposta inteira como JSON;
      2. o conteúdo de uma cerca de código (```json ... ```), em qualquer posição;
      3. o primeiro objeto/array JSON válido embutido em texto ao redor.
    Só objetos ({}) e arrays ([]) contam nos passos 2 e 3. Havendo mais de um
    candidato, vale o primeiro que for JSON válido.
    """
    t = (texto or "").strip()
    if not t:
        return None, "JSON inválido: resposta vazia"

    try:
        return json.loads(t), None
    except json.JSONDecodeError as exc:
        erro_inteiro = f"JSON inválido: {exc.msg} (linha {exc.lineno}, coluna {exc.colno})"

    for m in _CERCA.finditer(t):
        try:
            obj = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, (dict, list)):
            return obj, None

    decoder = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "{[":
            try:
                obj, _ = decoder.raw_decode(t, i)
            except json.JSONDecodeError:
                continue
            return obj, None

    return None, erro_inteiro
