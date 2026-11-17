"""
editor.py — Etapa 4 do fluxo (docs/01 §7.2): criação original pelo Chef IA (receita e dica).

Base: docs/03-PROMPT-SISTEMA.md §2 (camadas), §4-§6 (regras e módulo de receita),
§10 (entrada), §12 (validação e reparo) e §13 (robustez).

O que este módulo faz:
- monta o prompt em camadas (services/carregador_prompts.py);
- chama o modelo da tarefa "criacao" (e "reparo" nas correções);
- valida a saída com Pydantic: SCH-01 (JSON), SCH-02 (esquema), SCH-03 (limites)
  e SCH-04 (o modelo não pode preencher campos do sistema: extra="forbid");
- até 2 reparos (03 §12.2), sempre revalidando a resposta inteira;
- NÃO há bypass de ficha: sem ficha aprovada, não cria.

O que NÃO faz (PENDENTE: validators/, docs/08): SCH-05 a SCH-07, NUM, CUL, ALG,
SEG, HON, SIM, IMG e SEO. Entram pela interface `Validador`. Sem validador, o
resultado é "pendente_validacao", nunca "aprovado".

O CÓDIGO, não o modelo, define dificuldade, tempos de consenso, rendimento,
dieta, ocasiões, armazenamento, slug, autor, aviso e status (03 §6.2): isso é
feito no adaptador (Etapa 4) e nos validadores.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from services import carregador_prompts as cp
from services.llm_cliente import GerarFn, extrair_json, gerar_padrao

MAX_REPAROS = 2  # 03 §12.2
FAMILIAS_ESTRITAS = ("SEG", "ALG", "HON")  # 03 §12.2: o reparo só corrige o trecho apontado


# --------------------------------------------------------------------------
# Esquema de saída da receita (docs/03 §6.2). Nomes e limites da tabela.
# --------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")  # SCH-04


class ItemIngrediente(_Base):
    nome: str = Field(min_length=1, max_length=180)
    quantidade: str = Field(min_length=1, max_length=80)
    unidade: str = Field(min_length=1, max_length=40)  # vocabulário: NUM-07 (validators)
    observacao: str | None = Field(default=None, max_length=180)

    @field_validator("quantidade", mode="before")
    @classmethod
    def _numero_vira_texto(cls, v):
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v

    @field_validator("observacao", mode="before")
    @classmethod
    def _vazio_vira_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class SecaoIngredientes(_Base):
    nome: str = Field(min_length=1, max_length=100)  # SITE: ingredientSectionSchema (shared/recipes.ts:24)
    itens: list[ItemIngrediente] = Field(min_length=1, max_length=80)


class Passo(_Base):
    instrucao: str = Field(min_length=1, max_length=1200)
    titulo: str | None = Field(default=None, max_length=120)

    @field_validator("titulo", mode="before")
    @classmethod
    def _vazio_vira_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class PerguntaFrequente(_Base):
    # 03 §6.2 não nomeia as chaves; limites de 06 §6.2 (faq). PENDENTE: confirmar nomes.
    pergunta: str = Field(min_length=1, max_length=240)
    resposta: str = Field(min_length=1, max_length=1200)


class RespostaReceita(_Base):
    titulo: str = Field(min_length=5, max_length=180)
    descricao_curta: str = Field(min_length=20, max_length=160)
    introducao: str | None = None
    subcategoria: str = Field(min_length=1)
    tempo_preparo_min: int = Field(ge=1, le=1440)
    tempo_cozimento_min: int | None = Field(default=None, ge=0, le=1440)
    tempo_descanso_min: int | None = Field(default=None, ge=0, le=10080)
    rendimento_porcoes: int = Field(ge=1, le=500)
    rendimento_texto: str | None = Field(default=None, max_length=80)
    ingredientes: list[SecaoIngredientes] = Field(min_length=1, max_length=20)
    modo_preparo: list[Passo] = Field(min_length=4, max_length=20)
    dica_extra: str | None = Field(default=None, max_length=1000)
    perguntas_frequentes: list[PerguntaFrequente] = Field(default_factory=list, max_length=5)
    tags: list[str] = Field(default_factory=list, max_length=12)
    termos_busca_imagem: list[str] = Field(min_length=3, max_length=5)
    prompt_imagem: str = Field(min_length=1, max_length=2000)
    texto_alt_imagem: str = Field(min_length=20, max_length=140)
    temas_relacionados: list[str] = Field(min_length=2, max_length=6)
    alertas_internos: list[str]

    @field_validator("introducao", "dica_extra", "rendimento_texto", mode="before")
    @classmethod
    def _vazio_vira_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        for t in v:
            if not (1 <= len(t) <= 40):
                raise ValueError("cada tag deve ter de 1 a 40 caracteres")
        return v


# Compatibilidade de nome para o módulo de SEO; o modelo canônico é RespostaReceita.
ReceitaSaida = RespostaReceita


# --------------------------------------------------------------------------
# Esquema de saída da dica (docs/03 §7 e docs/04 §10)
# --------------------------------------------------------------------------

PALAVRAS_DICA = (150, 400)  # docs/03 §7 item 6 e docs/04 §10 ("tamanho inicial", a calibrar)


class RespostaDica(_Base):
    titulo: str = Field(min_length=5, max_length=180)
    descricao_curta: str = Field(min_length=20, max_length=160)
    assunto: str = Field(min_length=1, max_length=60)  # vem da pauta (SCH-04 confere)
    # 03 §7 pede "1 ou 2 frases"; o limite de caracteres não é definido (600 é parâmetro nosso).
    resposta_direta: str = Field(min_length=1, max_length=600)
    corpo: str = Field(min_length=1)  # markdown; resposta direta, motivo, passos e como evitar
    tags: list[str] = Field(default_factory=list, max_length=12)
    temas_relacionados: list[str] = Field(min_length=2, max_length=4)  # 03 §7 item 8
    subcategoria: str | None = None  # opcional em dica (04 §6.7)
    termos_busca_imagem: list[str] = Field(min_length=3, max_length=5)
    prompt_imagem: str = Field(min_length=1, max_length=2000)
    alertas_internos: list[str]

    @field_validator("subcategoria", mode="before")
    @classmethod
    def _vazio_vira_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("corpo")
    @classmethod
    def _tamanho(cls, v):
        n = len(v.split())
        if not (PALAVRAS_DICA[0] <= n <= PALAVRAS_DICA[1]):
            raise ValueError(f"tamanho: o corpo tem {n} palavras; o esperado é de {PALAVRAS_DICA[0]} a {PALAVRAS_DICA[1]}")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        for t in v:
            if not (1 <= len(t) <= 40):
                raise ValueError("cada tag deve ter de 1 a 40 caracteres")
        return v


# --------------------------------------------------------------------------
# Falhas e interface dos validadores (PENDENTE: validators/, docs/08)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Falha:
    """PENDENTE: unificar com validators/base.py (Passo 7a). IDs como em docs/08 §4."""

    id: str
    detalhe: str
    gravidade: str = "bloqueante"  # "bloqueante" | "aviso"
    campo: str | None = None


class Validador(Protocol):
    def validar(self, conteudo: dict, contexto: dict) -> list[Falha]: ...


_TIPOS_LIMITE = {
    "string_too_short", "string_too_long", "too_short", "too_long",
    "greater_than_equal", "less_than_equal", "greater_than", "less_than",
}


def _falhas_pydantic(exc: ValidationError) -> list[Falha]:
    falhas = []
    for e in exc.errors():
        campo = ".".join(str(p) for p in e["loc"])
        if e["type"] == "extra_forbidden":
            id_, det = "SCH-04", "campo que o sistema preenche ou que não existe no contrato"
        elif e["type"] in _TIPOS_LIMITE or "tamanho:" in e["msg"]:
            id_, det = "SCH-03", e["msg"]
        else:
            id_, det = "SCH-02", e["msg"]
        falhas.append(Falha(id_, det, campo=campo))
    # Quando há erro estrutural e erro de limite na mesma resposta, o contrato
    # deve reportar primeiro a violação estrutural (SCH-02). Isso evita que o
    # código de rejeição oscile conforme a ordem interna do Pydantic.
    return sorted(falhas, key=lambda f: {"SCH-02": 0, "SCH-03": 1, "SCH-04": 2}.get(f.id, 3))


def validar_saida(texto: str, pauta: dict) -> tuple[RespostaReceita | None, list[Falha]]:
    """SCH-01 a SCH-04 e a regra 'subcategoria vem da pauta' (03 §6.2 e §10)."""
    dados, erro = extrair_json(texto)
    if erro:
        return None, [Falha("SCH-01", erro)]
    if not isinstance(dados, dict):
        return None, [Falha("SCH-01", "a resposta deve ser um objeto JSON")]
    try:
        resp = RespostaReceita.model_validate(dados)
    except ValidationError as exc:
        return None, _falhas_pydantic(exc)
    falhas = []
    if resp.subcategoria != pauta.get("subcategoria"):
        falhas.append(Falha("SCH-04", "a subcategoria vem da pauta e não pode ser alterada", campo="subcategoria"))
    return resp, falhas


# --------------------------------------------------------------------------
# Resultado e laço de criação/reparo
# --------------------------------------------------------------------------


@dataclass
class ResultadoCriacao:
    status: str  # "aprovado" | "pendente_validacao" | "rejeitado"
    conteudo: dict | None = None
    tentativas: int = 0  # chamadas ao modelo (1 + reparos)
    modelo: dict = field(default_factory=dict)  # provedor, modelo e família do gerador
    prompt_versoes: dict = field(default_factory=dict)
    prompt_version: str = ""
    alertas_internos: list[str] = field(default_factory=list)
    falhas: list[Falha] = field(default_factory=list)
    historico: list[dict] = field(default_factory=list)
    rejection_code: str | None = None


def _linha_erro(f: Falha) -> str:
    return f"- {f.id}" + (f" ({f.campo})" if f.campo else "") + f": {f.detalhe}"


def _escopo_do_reparo(anterior: dict | None, novo: dict, falhas_anteriores: list[Falha]) -> list[Falha]:
    """
    03 §12.2: reprovação por SEG, ALG ou HON só admite correção do trecho
    apontado. Se o reparo mexer em outro campo de nível superior, reprova.
    Sem 'campo' informado pelo validador, não há como impor (PENDENTE: validators).
    """
    bloq = [f for f in falhas_anteriores if f.gravidade == "bloqueante"]
    if anterior is None or not bloq or not all(f.id.startswith(FAMILIAS_ESTRITAS) for f in bloq):
        return []
    permitidos = {f.campo.split(".")[0] for f in bloq if f.campo}
    if not permitidos:
        return []
    mudou = sorted(k for k in novo if novo.get(k) != anterior.get(k) and k not in permitidos)
    if not mudou:
        return []
    return [Falha("REPARO-ESCOPO", f"o reparo alterou campos fora do trecho apontado: {', '.join(mudou)}", campo=mudou[0])]


def _laco_criacao(
    prompt: str,
    versoes: dict,
    validar_texto: Callable[[str], tuple[BaseModel | None, list[Falha]]],
    contexto: dict,
    gerar: GerarFn,
    validador: Validador | None,
    max_reparos: int,
) -> ResultadoCriacao:
    res = ResultadoCriacao(status="rejeitado", prompt_versoes=dict(versoes))
    resposta = gerar("criacao", prompt)
    anterior: dict | None = None
    falhas_ant: list[Falha] = []
    max_reparos = max(0, min(max_reparos, MAX_REPAROS))

    for tentativa in range(1, max_reparos + 2):
        res.tentativas = tentativa
        res.modelo = resposta.info()
        resp, falhas = validar_texto(resposta.texto)
        conteudo = resp.model_dump() if resp is not None else None
        if conteudo is not None:
            res.alertas_internos = list(conteudo.get("alertas_internos", []))
            falhas = falhas + _escopo_do_reparo(anterior, conteudo, falhas_ant)
            if not any(f.gravidade == "bloqueante" for f in falhas) and validador is not None:
                falhas = falhas + list(validador.validar(conteudo, contexto))
        bloqueantes = [f for f in falhas if f.gravidade == "bloqueante"]
        res.historico.append({"tentativa": tentativa, "falhas": [f.id for f in bloqueantes]})
        res.falhas = falhas

        if not bloqueantes:
            res.conteudo = conteudo
            res.status = "aprovado" if validador is not None else "pendente_validacao"
            break
        # Campos reservados ao sistema não são reparáveis pelo modelo.
        if any(f.id == "SCH-04" for f in bloqueantes):
            res.rejection_code = "SCH-04"
            break
        if tentativa > max_reparos:
            res.rejection_code = bloqueantes[0].id  # 07 §4.3: código da verificação
            break

        rep = cp.carregar("reparo")
        res.prompt_versoes["reparo"] = rep.versao
        texto_rep = cp.renderizar(
            rep,
            ERROS="\n".join(_linha_erro(f) for f in bloqueantes),
            RESPOSTA_ANTERIOR=resposta.texto[:20000].replace("<", "\\u003c"),
        )
        anterior, falhas_ant = conteudo, falhas
        resposta = gerar("reparo", f"{prompt}\n\n{texto_rep}")

    res.prompt_version = cp.versao_composta(res.prompt_versoes)
    return res


def criar_receita(
    ficha: dict,
    pauta: dict,
    *,
    gerar: GerarFn | None = None,
    validador: Validador | None = None,
    categorias_validas: list[str] | None = None,
    contexto_validacao: dict | None = None,
    max_reparos: int = MAX_REPAROS,
) -> ResultadoCriacao:
    """
    Cria uma receita a partir da ficha consolidada APROVADA (agents/analista.py).
    Não consulta a internet. Erros do provedor de LLM (ex.: ModeloNaoAprovado)
    sobem para o pipeline, que aborta a execução (docs/07 §5).
    """
    if ficha.get("status") != "aprovada_para_criacao":
        raise ValueError("ficha não aprovada: a criação exige status 'aprovada_para_criacao' (PESQUISA-RECEITAS §12)")
    if ficha.get("pauta", {}).get("subcategoria") not in (None, pauta.get("subcategoria")):
        raise ValueError("a pauta vale para categoria e subcategoria (03 §10), mas ficha e pauta divergem")
    contexto = dict(contexto_validacao or {}, pauta=pauta, ficha=ficha)
    prompt, versoes = cp.montar_criacao("receita", "receita", pauta, ficha, RespostaReceita, categorias_validas)
    return _laco_criacao(prompt, versoes, lambda t: validar_saida(t, pauta), contexto, gerar or gerar_padrao, validador, max_reparos)


def validar_saida_dica(texto: str, pauta: dict) -> tuple[RespostaDica | None, list[Falha]]:
    """SCH-01 a SCH-04 da dica; assunto e subcategoria vêm da pauta (03 §7, 04 §6.7)."""
    dados, erro = extrair_json(texto)
    if erro:
        return None, [Falha("SCH-01", erro)]
    if not isinstance(dados, dict):
        return None, [Falha("SCH-01", "a resposta deve ser um objeto JSON")]
    try:
        resp = RespostaDica.model_validate(dados)
    except ValidationError as exc:
        return None, _falhas_pydantic(exc)
    falhas = []
    if resp.assunto != pauta.get("assunto"):
        falhas.append(Falha("SCH-04", "o assunto vem da pauta e não pode ser alterado", campo="assunto"))
    if resp.subcategoria != (pauta.get("subcategoria") or None):
        falhas.append(Falha("SCH-04", "a subcategoria vem da pauta (ou fica vazia) e não pode ser alterada", campo="subcategoria"))
    return resp, falhas


def criar_dica(
    ficha: dict,
    pauta: dict,
    *,
    gerar: GerarFn | None = None,
    validador: Validador | None = None,
    categorias_validas: list[str] | None = None,
    contexto_validacao: dict | None = None,
    max_reparos: int = MAX_REPAROS,
) -> ResultadoCriacao:
    """
    Cria uma dica (docs/03 §7) a partir da ficha de pesquisa APROVADA. O assunto
    (um dos seis de docs/04 §6.7) vem da pauta. Mesmo laço de reparo das receitas.
    """
    if ficha.get("status") != "aprovada_para_criacao":
        raise ValueError("ficha não aprovada: a criação exige status 'aprovada_para_criacao'")
    if not pauta.get("assunto"):
        raise ValueError("a pauta de dica precisa do assunto (tip_topic)")
    contexto = dict(contexto_validacao or {}, pauta=pauta, ficha=ficha)
    prompt, versoes = cp.montar_criacao("dica", "dica", pauta, ficha, RespostaDica, categorias_validas)
    return _laco_criacao(prompt, versoes, lambda t: validar_saida_dica(t, pauta), contexto, gerar or gerar_padrao, validador, max_reparos)
