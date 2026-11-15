"""
revisor.py — Etapa 5 (revisão por IA, escopo reduzido). docs/03 §12.3 e docs/08 §5.

- NÃO reescreve o conteúdo: só devolve problemas (o conteúdo nunca volta daqui).
- NÃO confere contas, quantidades, tempos nem a lista de ingredientes (é código).
- Usa modelo de FAMÍLIA DIFERENTE da do gerador. Falha fechada: se não for
  possível garantir isso, levanta FamiliaNaoGarantida (services/llm_cliente.py).
- Gravidade "alta" reprova. Resposta inválida também reprova (na dúvida, reprova).
- Nunca aprova o que o código rejeitou: use decisao_final().

PENDENTE: temperatura 0,1 a 0,2 (03 §13) depende de o llm_service aceitar
parâmetro de temperatura (ver "Lacunas" da Etapa 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services import carregador_prompts as cp
from services.llm_cliente import FamiliaNaoGarantida, GerarFn, extrair_json, gerar_padrao


class ProblemaRevisao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campo: str = Field(min_length=1, max_length=200)
    descricao: str = Field(min_length=1, max_length=500)
    gravidade: Literal["alta", "media", "baixa"]


class RespostaRevisor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aprovado: bool
    problemas: list[ProblemaRevisao] = Field(default_factory=list, max_length=50)


@dataclass
class ResultadoRevisao:
    aprovado: bool
    problemas: list[dict] = field(default_factory=list)
    modelo: dict = field(default_factory=dict)
    erro: str | None = None
    prompt_versao: str = ""


def revisar_conteudo(
    conteudo: dict,
    ficha: dict,
    familia_gerador: str,
    *,
    gerar: GerarFn | None = None,
) -> ResultadoRevisao:
    if not familia_gerador:
        raise FamiliaNaoGarantida("família do gerador desconhecida: não há como exigir família diferente")
    gerar = gerar or gerar_padrao

    prompt = cp.carregar("revisor")
    texto = cp.renderizar(
        prompt,
        CONTEUDO=cp.json_seguro(conteudo),
        DADOS_PESQUISA=cp.json_seguro({k: v for k, v in ficha.items() if k != "gate"}),
    )
    resposta = gerar("revisao", texto, familia_excluida=familia_gerador)
    # defesa em código, mesmo que o provedor ignore a exclusão
    if not resposta.familia or resposta.familia == familia_gerador:
        raise FamiliaNaoGarantida(
            f"revisor sem família diferente da do gerador (gerador={familia_gerador!r}, revisor={resposta.familia!r})"
        )

    base = dict(modelo=resposta.info(), prompt_versao=prompt.versao)
    dados, erro = extrair_json(resposta.texto)
    if erro or not isinstance(dados, dict):
        return ResultadoRevisao(False, erro=erro or "a resposta deve ser um objeto JSON", **base)
    try:
        r = RespostaRevisor.model_validate(dados)
    except ValidationError as exc:
        return ResultadoRevisao(False, erro=f"resposta fora do contrato: {exc.error_count()} erro(s)", **base)

    problemas = [p.model_dump() for p in r.problemas]
    aprovado = r.aprovado and not any(p["gravidade"] == "alta" for p in problemas)
    return ResultadoRevisao(aprovado, problemas, **base)


# Compatibilidade com a Etapa 2: o prompt do revisor vale para receita e dica.
revisar_receita = revisar_conteudo


def decisao_final(codigo_aprovou: bool, revisao: ResultadoRevisao) -> bool:
    """O revisor nunca aprova o que o código rejeitou (docs/03 §12.3)."""
    return bool(codigo_aprovou and revisao.aprovado)
