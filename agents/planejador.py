"""
planejador.py — Etapa 1 do fluxo (docs/01 §7.2): agendamento e pauta.

Base: docs/02-PESQUISA.md §4.1 (critérios e pesos da pauta, topic_slug),
docs/07-PUBLICACAO.md §4.1 (condições da próxima pauta) e §4.2 passo 2 (reserva),
docs/PESQUISA-RECEITAS.md §2 (formato da pauta) e docs/01 §7.4 (fases).

Escolhe pautas de RECEITA e de DICA (Etapa 5: assunto de docs/04 §6.7).
Este módulo só ESCOLHE e RESERVA pautas que já estão na fila. A doc não define
quem cria os temas das origens "calendar" e "coverage": a população da fila é
PENDENTE (Passos 3 e 9). Também PENDENTES, por interface:
- Taxonomia real: GET /api/taxonomy (Bloco 1 do site)
- Cobertura real: GET /api/coverage (Bloco 1 do site)
- Conteúdo existente: GET /api/content/lookup (Bloco 1 do site)
- Histórico real (agent_generations): Passo 3
- Pautas bloqueadas: config/pautas_bloqueadas.json e TAX-03 (validators)
- Teto de custo e limite diário (docs/07 §4.1 item 5): Passo 9
- Origem "search_console": gancho aceito, sem implementação (PENDENTE)
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_CALENDARIO = BASE_DIR / "config" / "calendario.json"

CONTENT_TYPES = {"receita": "recipe", "tecnica": "technique", "dica": "tip", "materia": "feature"}
ORIGENS = {"calendar", "coverage", "search_console", "manual"}  # docs/07 §4.1

# docs/taxonomy.seed.json (phase_allows_risk) e docs/01 §7.4. Fase 0 publica nada, mas só gera 'low'.
FASES_RISCO = {0: ("low",), 1: ("low",), 2: ("low", "medium"), 3: ("low", "medium", "high")}

# docs/02 §4.1: pesos iniciais (sugestão a calibrar).
PESOS_PAUTA = {"cobertura": 0.40, "sazonalidade": 0.25, "tendencia": 0.20, "eixo": 0.15}

# Interpretação (a doc diz só "eixo chocolate e confeitaria"): categorias de confeitaria
# da árvore de docs/04 §5.2 ou tema que cita chocolate.
CATEGORIAS_CONFEITARIA = {"bolos-e-tortas", "doces-e-sobremesas"}

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def gerar_topic_slug(tema: str) -> str:
    """Slug estável do TEMA normalizado, não do título gerado (docs/02 §4.1)."""
    t = unicodedata.normalize("NFKD", tema).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if not _SLUG_RE.match(slug):
        raise ValueError(f"tema inválido para topic_slug: {tema!r}")
    return slug[:180]


# --------------------------------------------------------------------------
# Interfaces e implementações em memória (mock)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Subcategoria:
    slug: str
    categoria: str
    risk_level: str
    agent_enabled: bool = False
    active: bool = True


@dataclass(frozen=True)
class AssuntoDica:
    """Assunto de dica (docs/04 §6.7): tabela tip_topics do site."""

    slug: str
    risk_level: str
    agent_enabled: bool = False
    active: bool = True


@dataclass(frozen=True)
class CoberturaItem:
    publicados: int = 0
    rascunhos: int = 0

    @property
    def total(self) -> int:
        return self.publicados + self.rascunhos


@dataclass(frozen=True)
class ItemFila:
    tema: str
    subcategoria: str | None = None  # opcional em dica (docs/04 §6.7)
    origem: str = "manual"
    ocasioes: tuple[str, ...] = ()
    dieta: tuple[str, ...] = ()
    dificuldade_alvo: str | None = None
    observacoes: str = ""
    prioridade: float = 0.0
    tendencia: float = 0.0  # 0..1; PENDENTE: preenchido pelo Search Console no futuro
    data_minima: date | None = None  # earliest_date (docs/04 §8.9)
    assunto: str | None = None  # só em dica: slug de tip_topics (docs/04 §6.7)


class Taxonomia(Protocol):
    def subcategorias(self) -> list[Subcategoria]: ...


class AssuntosDica(Protocol):
    """PENDENTE: os assuntos virão do site (tip_topics, Bloco 1)."""

    def assuntos(self) -> list[AssuntoDica]: ...


class Cobertura(Protocol):
    def por_subcategoria(self) -> dict[str, CoberturaItem]: ...


class Historico(Protocol):
    def ja_existe(self, content_type: str, topic_slug: str) -> bool: ...
    def reservar_pauta(self, content_type: str, topic_slug: str, tema: str, subcategoria: str) -> bool: ...


class ConteudoExistente(Protocol):
    def existe(self, topic_slug: str, tema: str) -> bool: ...


class Bloqueios(Protocol):
    def motivo(self, tema: str, subcategoria: str) -> str | None: ...


class FilaPautas(Protocol):
    def itens(self) -> list[ItemFila]: ...


class TaxonomiaMemoria:
    def __init__(self, itens: list[Subcategoria]):
        self._itens = list(itens)

    def subcategorias(self):
        return list(self._itens)


class AssuntosDicaMemoria:
    def __init__(self, itens: list[AssuntoDica]):
        self._itens = list(itens)

    def assuntos(self):
        return list(self._itens)


class CoberturaMock:
    """Implementação mock; a real (GET /api/coverage) entra depois do Bloco 1."""

    def __init__(self, dados: dict[str, CoberturaItem] | None = None):
        self._dados = dados or {}

    def por_subcategoria(self):
        return dict(self._dados)


class HistoricoMemoria:
    """Substituto de agent_generations (UNIQUE content_type + topic_slug)."""

    def __init__(self):
        self._reservas: set[tuple[str, str]] = set()

    def ja_existe(self, content_type, topic_slug):
        return (content_type, topic_slug) in self._reservas

    def reservar_pauta(self, content_type, topic_slug, tema, subcategoria):
        chave = (content_type, topic_slug)
        if chave in self._reservas:
            return False
        self._reservas.add(chave)
        return True


class ConteudoExistenteMemoria:
    def __init__(self, topic_slugs: set[str] | None = None):
        self._slugs = set(topic_slugs or ())

    def existe(self, topic_slug, tema):
        return topic_slug in self._slugs


class BloqueiosMemoria:
    def __init__(self, palavras_por_motivo: dict[str, list[str]] | None = None):
        self._m = palavras_por_motivo or {}

    def motivo(self, tema, subcategoria):
        t = tema.lower()
        for motivo, palavras in self._m.items():
            if any(p in t for p in palavras):
                return motivo
        return None


class FilaMemoria:
    def __init__(self, itens: list[ItemFila]):
        self._itens = list(itens)

    def itens(self):
        return list(self._itens)


# --------------------------------------------------------------------------
# Calendário e pontuação
# --------------------------------------------------------------------------


def carregar_calendario(caminho: Path | str = CONFIG_CALENDARIO) -> dict:
    with Path(caminho).open("r", encoding="utf-8") as f:
        return json.load(f)


def _data_do_evento(valor: str, hoje: date) -> date | None:
    """'AAAA-MM-DD' | 'MM-DD' (próxima ocorrência) | 'a definir' -> None."""
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
            return datetime.strptime(valor, "%Y-%m-%d").date()
        if re.fullmatch(r"\d{2}-\d{2}", valor):
            d = datetime.strptime(f"{hoje.year}-{valor}", "%Y-%m-%d").date()
            return d if d >= hoje else datetime.strptime(f"{hoje.year + 1}-{valor}", "%Y-%m-%d").date()
    except ValueError:
        return None
    return None


def pontuar_sazonalidade(item: ItemFila, calendario: dict | None, hoje: date) -> float:
    """
    0..1. Só pontua com datas e antecedência numéricas; enquanto o calendário
    estiver 'a definir' (docs/02 §3.3 não traz datas), devolve 0 (PENDENTE).
    """
    if not calendario:
        return 0.0
    semanas = calendario.get("antecedencia_semanas")
    if not isinstance(semanas, (int, float)) or semanas <= 0:
        return 0.0
    janela = timedelta(weeks=semanas)
    melhor = 0.0
    for ev in calendario.get("datas", []):
        if ev.get("ocasiao_slug") not in item.ocasioes:
            continue
        alvo = _data_do_evento(str(ev.get("data", "")), hoje)
        if alvo is None:
            continue
        faltam = alvo - hoje
        if timedelta(0) <= faltam <= janela:
            melhor = max(melhor, 1 - faltam / janela)
    return melhor


@dataclass
class Pauta:
    """Formato de docs/PESQUISA-RECEITAS.md §2, mais topic_slug e origem."""

    tipo_conteudo: str
    tema: str
    categoria: str | None
    subcategoria: str | None
    topic_slug: str
    origem: str
    assunto: str | None = None
    ocasiao: list[str] = field(default_factory=list)
    dieta: list[str] = field(default_factory=list)
    dificuldade_alvo: str | None = None
    observacoes: str = ""
    score: float = 0.0
    avisos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        extra = {"assunto": self.assunto} if self.assunto else {}
        return {
            **extra,
            "tipo_conteudo": self.tipo_conteudo,
            "tema": self.tema,
            "categoria": self.categoria,
            "subcategoria": self.subcategoria,
            "ocasiao": self.ocasiao,
            "dieta": self.dieta,
            "dificuldade_alvo": self.dificuldade_alvo,
            "observacoes": self.observacoes,
            "topic_slug": self.topic_slug,
            "origem": self.origem,
            "score": round(self.score, 4),
            "avisos": self.avisos,
        }


@dataclass
class ResultadoPlanejamento:
    pauta: Pauta | None
    descartadas: list[dict] = field(default_factory=list)


def escolher_pauta(
    fila: FilaPautas,
    taxonomia: Taxonomia,
    cobertura: Cobertura,
    historico: Historico,
    *,
    fase: int = 1,
    hoje: date | None = None,
    conteudo_existente: ConteudoExistente | None = None,
    bloqueios: Bloqueios | None = None,
    calendario: dict | None = None,
    tipo_conteudo: str = "receita",
    assuntos: AssuntosDica | None = None,
) -> ResultadoPlanejamento:
    """
    Aplica as condições de docs/07 §4.1 (1 a 4), pontua por docs/02 §4.1 e
    reserva a melhor pauta (docs/07 §4.2 passo 2). Devolve também o motivo de
    cada descarte, com os mesmos códigos dos validadores (TAX-01 a TAX-03).
    """
    if tipo_conteudo not in ("receita", "dica"):
        raise NotImplementedError("PENDENTE: pautas de técnica e matéria")
    if tipo_conteudo == "dica" and assuntos is None:
        raise ValueError("pauta de dica exige a interface de assuntos (tip_topics, docs/04 §6.7)")
    idx_assuntos = {a.slug: a for a in assuntos.assuntos()} if assuntos is not None else {}
    hoje = hoje or date.today()
    content_type = CONTENT_TYPES[tipo_conteudo]
    riscos_ok = FASES_RISCO.get(fase)
    if riscos_ok is None:
        raise ValueError(f"fase inválida: {fase}")

    subs = {s.slug: s for s in taxonomia.subcategorias()}
    cob = cobertura.por_subcategoria()
    habilitadas = [s for s in subs.values() if s.active and s.agent_enabled and s.risk_level in riscos_ok]
    max_total = max((cob.get(s.slug, CoberturaItem()).total for s in habilitadas), default=0)

    avisos = []
    if bloqueios is None:
        avisos.append("PENDENTE: pautas bloqueadas não aplicadas (config/pautas_bloqueadas.json, TAX-03)")
    if conteudo_existente is None:
        avisos.append("PENDENTE: duplicidade com o site não consultada (GET /api/content/lookup)")

    descartadas: list[dict] = []
    elegiveis: list[tuple[float, float, int, ItemFila, Subcategoria, str]] = []
    for ordem, item in enumerate(fila.itens()):
        def recusar(codigo: str, detalhe: str) -> None:
            descartadas.append({"tema": item.tema, "codigo": codigo, "detalhe": detalhe})

        if item.origem not in ORIGENS:
            recusar("ORIGEM", f"origem desconhecida: {item.origem}")
            continue
        if tipo_conteudo == "dica":
            # 04 §6.7: o assunto é limitado pela fase como as subcategorias; a subcategoria é opcional.
            ass = idx_assuntos.get(item.assunto or "")
            if ass is None or not ass.active or not ass.agent_enabled:
                recusar("TAX-01", "assunto inexistente, inativo ou não habilitado")
                continue
            if ass.risk_level not in riscos_ok:
                recusar("TAX-02", f"risco {ass.risk_level} do assunto não permitido na fase {fase}")
                continue
            sub = subs.get(item.subcategoria) if item.subcategoria else None
            if item.subcategoria and (sub is None or not sub.active):
                recusar("TAX-01", "subcategoria inexistente ou inativa")
                continue
        else:
            sub = subs.get(item.subcategoria)
            if sub is None or not sub.active or not sub.agent_enabled:
                recusar("TAX-01", "subcategoria inexistente, inativa ou não habilitada")
                continue
            if sub.risk_level not in riscos_ok:
                recusar("TAX-02", f"risco {sub.risk_level} não permitido na fase {fase}")
                continue
        if item.data_minima and item.data_minima > hoje:
            recusar("DATA", "ainda antes da data mínima (earliest_date)")
            continue
        try:
            slug = gerar_topic_slug(item.tema)
        except ValueError as exc:
            recusar("TEMA", str(exc))
            continue
        if historico.ja_existe(content_type, slug):
            recusar("DUP-HIST", "topic_slug já registrado no histórico")
            continue
        if conteudo_existente is not None and conteudo_existente.existe(slug, item.tema):
            recusar("SIM-04", "conteúdo equivalente já existe no site")
            continue
        if bloqueios is not None:
            motivo = bloqueios.motivo(item.tema, item.subcategoria or item.assunto or "")
            if motivo:
                recusar("TAX-03", f"pauta bloqueada: {motivo}")
                continue

        total = cob.get(sub.slug, CoberturaItem()).total if sub else 0
        # dica: a cobertura por assunto não existe (PENDENTE, docs/06 §9); não pontua
        s_cob = 1.0 if (max_total == 0 or tipo_conteudo == "dica") else 1 - total / max_total
        s_saz = pontuar_sazonalidade(item, calendario, hoje)
        s_tend = max(0.0, min(1.0, item.tendencia))  # PENDENTE: Search Console
        eixo = 1.0 if ((sub and sub.categoria in CATEGORIAS_CONFEITARIA) or "chocolate" in item.tema.lower()) else 0.0
        score = (
            PESOS_PAUTA["cobertura"] * s_cob
            + PESOS_PAUTA["sazonalidade"] * s_saz
            + PESOS_PAUTA["tendencia"] * s_tend
            + PESOS_PAUTA["eixo"] * eixo
        )
        elegiveis.append((score, item.prioridade, -ordem, item, sub, slug))

    elegiveis.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    for score, _, _, item, sub, slug in elegiveis:
        if historico.reservar_pauta(content_type, slug, item.tema, item.subcategoria):
            return ResultadoPlanejamento(
                Pauta(
                    tipo_conteudo=tipo_conteudo,
                    tema=item.tema,
                    categoria=sub.categoria if sub else None,
                    subcategoria=sub.slug if sub else None,
                    topic_slug=slug,
                    origem=item.origem,
                    assunto=item.assunto if tipo_conteudo == "dica" else None,
                    ocasiao=list(item.ocasioes),
                    dieta=list(item.dieta),
                    dificuldade_alvo=item.dificuldade_alvo,
                    observacoes=item.observacoes,
                    score=score,
                    avisos=avisos,
                ),
                descartadas,
            )
        descartadas.append({"tema": item.tema, "codigo": "RESERVA", "detalhe": "reserva não obtida (concorrência)"})
    return ResultadoPlanejamento(None, descartadas)
