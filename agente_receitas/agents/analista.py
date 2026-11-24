"""
analista.py — Etapa 3 do fluxo (docs/01 §7.2): análise e cruzamento.

Base: docs/02-PESQUISA.md §4.3 e §7.2; docs/PESQUISA-RECEITAS.md §3 (etapas 3 a
9), §5 (normalização), §6 (proporções), §7 (técnica e tempos), §8 (etiquetas de
dieta), §9 (rendimento), §11 (ficha consolidada) e §12 (gate de aprovação).

Entrada: pauta + fichas de fonte (02 §7.1, só fatos). Saída: ficha consolidada
(PESQUISA-RECEITAS §11) com status "aprovada_para_criacao" ou "rejeitada" e o
detalhe do gate em ficha["gate"].

Recursos que dependem de outras partes do projeto entram por INTERFACE. Os
padrões "Sem*" não aprovam nada (na dúvida, rejeita, PESQUISA-RECEITAS §12):
- CatalogoIngredientes  -> PENDENTE: GET /api/catalog/ingredients (Bloco 1 do site)
- RazoesSanidade        -> PENDENTE: config/razoes.json curado por pessoa (08 §4.4 CUL-04)
- DetectorRiscos        -> PENDENTE: validators SEG-01 (08 §4.6); a doc não define as regras
- BaseSeguranca         -> PENDENTE: config/seguranca.json curado por pessoa

O analista NÃO inventa valores: quantidade absoluta = proporção decidida x
quantidade-base da fonte de referência (ver "Lacunas" da Etapa 1).
"""

from __future__ import annotations

import difflib
import json
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FONTES = BASE_DIR / "config" / "fontes.json"
CONFIG_CONVERSOES = BASE_DIR / "config" / "conversoes.json"

SIMILARIDADE_NOME = 0.92  # mesmo limite de docs/04 §7.2 para busca aproximada
_RANK_PESO = {"alto": 0, "medio": 1, "baixo_medio": 2}


# --------------------------------------------------------------------------
# Interfaces das dependências (PENDENTES) e implementações de teste
# --------------------------------------------------------------------------


class CatalogoIngredientes(Protocol):
    disponivel: bool

    def resolver(self, nome: str) -> dict | None:
        """{slug, vegetarian_ok, vegan_ok, needs_label_check} ou None (docs/04 §7.1)."""
        ...


class RazoesSanidade(Protocol):
    def avaliar(self, subcategoria: str, ingredientes: list[dict]) -> list[str] | None:
        """None = família sem razões curadas; lista = violações (vazia = ok)."""
        ...


class DetectorRiscos(Protocol):
    def sinais(self, ingredientes: list[dict], tecnicas: list[str], tempos: dict) -> list[str] | None:
        """Sinais de risco (08 §4.6 SEG-01) ou None se o detector não existe."""
        ...


class BaseSeguranca(Protocol):
    def entrada(self, subcategoria: str, sinal: str) -> dict | None: ...


class SemCatalogo:
    disponivel = False

    def resolver(self, nome):  # PENDENTE: Bloco 1 do site
        return None


class SemRazoes:
    def avaliar(self, subcategoria, ingredientes):  # PENDENTE: curadoria
        return None


class SemDetector:
    def sinais(self, ingredientes, tecnicas, tempos):  # PENDENTE: validators SEG-01
        return None


class SemBaseSeguranca:
    def entrada(self, subcategoria, sinal):  # PENDENTE: curadoria
        return None


class CatalogoMemoria:
    """Catálogo de teste. `itens`: nome -> {slug, vegetarian_ok, vegan_ok, needs_label_check}."""

    disponivel = True

    def __init__(self, itens: dict[str, dict]):
        self._por_chave = {chave_ingrediente(n): v for n, v in itens.items()}

    def resolver(self, nome):
        return self._por_chave.get(chave_ingrediente(nome))


# --------------------------------------------------------------------------
# Texto, nomes e quantidades
# --------------------------------------------------------------------------


def normalizar_texto(texto: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_STOP = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "com", "para", "ao", "na", "no"}
_ESTADOS = {
    "picado", "picada", "ralado", "ralada", "derretido", "derretida", "peneirado",
    "peneirada", "amolecido", "amolecida", "gelado", "gelada", "frio", "fria",
    "morno", "morna", "fatiado", "fatiada", "triturado", "triturada",
    "temperatura", "ambiente",
}


def _tokens_ingrediente(nome: str) -> list[str]:
    base = re.sub(r"\(.*?\)", "", str(nome).split(",")[0])
    toks = [t for t in normalizar_texto(base).split() if t not in _STOP and t not in _ESTADOS]
    return [t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks]


def chave_ingrediente(nome: str) -> str:
    """Chave de comparação entre fontes: sem acento, plural, estado e ordem."""
    return " ".join(sorted(_tokens_ingrediente(nome)))


# Categorias críticas de docs/PESQUISA-RECEITAS §6.2, por palavra.
# PENDENTE: substituir pelo `kind` do catálogo de ingredientes (Bloco 1 do site).
_TOKENS_CRITICOS = {
    "farinha", "acucar", "leite", "agua", "oleo", "manteiga", "margarina", "gordura",
    "ovo", "gema", "clara", "fermento", "chocolate", "cacau", "creme", "nata",
}


def eh_critico(chave: str) -> bool:
    return any(t in _TOKENS_CRITICOS for t in chave.split())


_FRACAO = re.compile(r"^(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)$")
_DECIMAL = re.compile(r"^\d+(?:[.,]\d+)?$")
_SEPARADOR_FAIXA = re.compile(r"\s+(?:a|ate|até|ou)\s+|\s*[-–]\s*")


def _numero(s: str) -> float | None:
    s = s.strip()
    m = _FRACAO.match(s)
    if m:
        den = int(m.group(3))
        if den == 0:
            return None
        return int(m.group(1) or 0) + int(m.group(2)) / den
    if _DECIMAL.match(s):
        return float(s.replace(",", "."))
    return None


def parse_quantidade(q: Any) -> tuple[float | None, bool]:
    """(valor, aproximado). Faixas ('2 a 3') viram a média e aproximado=True."""
    if q is None or isinstance(q, bool):
        return None, False
    if isinstance(q, (int, float)):
        return (float(q), False) if q > 0 else (None, False)
    s = str(q).strip().lower()
    if not s:
        return None, False
    partes = _SEPARADOR_FAIXA.split(s)
    if len(partes) == 2:
        a, b = _numero(partes[0]), _numero(partes[1])
        if a is not None and b is not None and a > 0 and b > 0:
            return (a + b) / 2, True
    v = _numero(s)
    return (v, False) if v is not None and v > 0 else (None, False)


_UNIDADES = {
    "g": "g", "gr": "g", "grama": "g", "gramas": "g",
    "kg": "kg", "quilo": "kg", "quilos": "kg", "quilograma": "kg", "quilogramas": "kg",
    "ml": "ml", "mililitro": "ml", "mililitros": "ml",
    "l": "l", "litro": "l", "litros": "l",
    "xicara": "xicara_cha", "xicaras": "xicara_cha", "xic": "xicara_cha",
    "xicara de cha": "xicara_cha", "xicaras de cha": "xicara_cha",
    "colher de sopa": "colher_sopa", "colheres de sopa": "colher_sopa", "cs": "colher_sopa",
    "colher de cha": "colher_cha", "colheres de cha": "colher_cha", "cc": "colher_cha",
    "unidade": "unidade", "unidades": "unidade", "un": "unidade", "und": "unidade",
    "pitada": "pitada", "pitadas": "pitada",
    "dente": "dente", "dentes": "dente",
    "fatia": "fatia", "fatias": "fatia",
    "lata": "lata", "latas": "lata",
    "caixinha": "caixinha", "caixinhas": "caixinha",
    "maco": "maco", "macos": "maco",
    "ramo": "ramo", "ramos": "ramo",
}


def normalizar_unidade(unidade: Any) -> str | None:
    if unidade is None:
        return None
    return _UNIDADES.get(normalizar_texto(unidade))


@dataclass
class Medida:
    valor: float | None = None
    dimensao: str | None = None  # "massa" (g), "volume" (ml) ou "unidade"
    aproximado: bool = False
    falha: str | None = None


def carregar_conversoes(caminho: Path | str = CONFIG_CONVERSOES) -> dict:
    with Path(caminho).open("r", encoding="utf-8") as f:
        return json.load(f)


def _achar_conversao(tokens: set[str], unidade: str, conv: dict) -> dict | None:
    melhor, melhor_n = None, 0
    for item in conv.get("por_ingrediente", []) + conv.get("unidades_de_referencia", []):
        if item["unidade"] != unidade:
            continue
        chave = set(_tokens_ingrediente(item["ingrediente"]))
        if chave and chave <= tokens and len(chave) > melhor_n:
            melhor, melhor_n = item, len(chave)
    return melhor


def normalizar_medida(nome: str, quantidade: Any, unidade: Any, conv: dict) -> Medida:
    """
    PESQUISA-RECEITAS §5: tudo em g ou ml para comparar. Sem conversão
    documentada, NÃO se estima densidade: a medida fica na sua dimensão
    (volume, unidade) ou falha.
    """
    valor, aprox = parse_quantidade(quantidade)
    if valor is None:
        return Medida(falha="sem_quantidade_numerica")
    canon = normalizar_unidade(unidade) if unidade not in (None, "") else "unidade"
    if canon is None:
        return Medida(falha="unidade_desconhecida")
    tokens = set(_tokens_ingrediente(nome))

    if canon == "g":
        return Medida(valor, "massa", aprox)
    if canon == "kg":
        return Medida(valor * 1000, "massa", aprox)
    if canon == "ml":
        return Medida(valor, "volume", aprox)
    if canon == "l":
        return Medida(valor * 1000, "volume", aprox)

    esp = _achar_conversao(tokens, canon, conv)
    if esp is not None:
        return Medida(valor * esp["g"], "massa", aprox or bool(esp.get("aproximado")))
    if canon in conv.get("generico", {}):
        return Medida(valor * conv["generico"][canon]["ml"], "volume", aprox)
    if canon in {"lata", "caixinha"}:
        return Medida(falha="sem_conversao")
    return Medida(valor, "unidade", aprox, falha="sem_conversao")


# --------------------------------------------------------------------------
# Resultado do gate
# --------------------------------------------------------------------------


def _item(id_: str, descricao: str, ok: bool | None, detalhe: str = "") -> dict:
    """ok=None significa PENDENTE (recurso inexistente); conta como reprovado."""
    return {"id": id_, "descricao": descricao, "ok": ok, "detalhe": detalhe or ("ok" if ok else "")}


# --------------------------------------------------------------------------
# Analista
# --------------------------------------------------------------------------


@dataclass
class _Linha:
    ficha: int
    nome: str
    medida: Medida
    quantidade_bruta: Any
    unidade_bruta: Any


def _mediana(valores: list[float]) -> float:
    return float(statistics.median(valores))


def _fora(valor: float, ref: float, margem: float) -> bool:
    return ref == 0 or abs(valor - ref) / abs(ref) > margem


def _arredondar(v: float) -> float:
    return round(v) if v >= 10 else round(v, 1)


def _parecidos(a: str, b: str) -> bool:
    ta, tb = set(normalizar_texto(a).split()), set(normalizar_texto(b).split())
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= 0.5 or difflib.SequenceMatcher(None, normalizar_texto(a), normalizar_texto(b)).ratio() >= 0.8


class Analista:
    def __init__(
        self,
        catalogo: CatalogoIngredientes | None = None,
        razoes: RazoesSanidade | None = None,
        detector: DetectorRiscos | None = None,
        seguranca: BaseSeguranca | None = None,
        conversoes: dict | None = None,
        cfg: dict | None = None,
        fase: int = 1,
    ):
        self.catalogo = catalogo or SemCatalogo()
        self.razoes = razoes or SemRazoes()
        self.detector = detector or SemDetector()
        self.seguranca = seguranca or SemBaseSeguranca()
        self.conv = conversoes if conversoes is not None else carregar_conversoes()
        if cfg is None:
            with CONFIG_FONTES.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        self.cfg = cfg
        self.margem = cfg["analise"]["margem_outlier"]
        self.minimo = cfg["minimo_fontes"]["receita"]
        self.fase = fase

    # ---- agrupamento -----------------------------------------------------

    def _agrupar(self, fichas: list[dict]):
        """chave canônica -> {ficha_idx: _Linha}; também devolve falhas por chave."""
        canon: list[str] = []
        grupos: dict[str, dict[int, _Linha]] = {}
        falhas: dict[str, list[dict]] = {}

        def canonica(chave: str) -> str:
            if chave in grupos:
                return chave
            for c in canon:
                if difflib.SequenceMatcher(None, chave, c).ratio() >= SIMILARIDADE_NOME:
                    return c
            canon.append(chave)
            return chave

        for idx, f in enumerate(fichas):
            for ing in f["fatos"]["ingredientes"]:
                chave = canonica(chave_ingrediente(ing["nome"]))
                if not chave:
                    continue
                m = normalizar_medida(ing["nome"], ing.get("quantidade"), ing.get("unidade"), self.conv)
                if m.falha:
                    falhas.setdefault(chave, []).append(
                        {"ficha": idx, "nome": ing["nome"], "falha": m.falha}
                    )
                linha = _Linha(idx, ing["nome"], m, ing.get("quantidade"), ing.get("unidade"))
                atual = grupos.setdefault(chave, {}).get(idx)
                if atual is None:
                    grupos[chave][idx] = linha
                elif (
                    atual.medida.valor and m.valor and atual.medida.dimensao == m.dimensao
                ):  # mesmo ingrediente em duas seções: soma
                    atual.medida.valor += m.valor
        return grupos, falhas

    # ---- base e proporções ----------------------------------------------

    def _escolher_bases(self, grupos, necessario: int):
        bases: dict[str, tuple[str, dict[int, float]]] = {}
        for dim in ("massa", "volume"):
            melhor = None
            for chave, por_ficha in grupos.items():
                valores = {
                    i: l.medida.valor for i, l in por_ficha.items()
                    if l.medida.dimensao == dim and l.medida.valor
                }
                if len(valores) < necessario:
                    continue
                ordem = (len(valores), eh_critico(chave), _mediana(list(valores.values())))
                if melhor is None or ordem > melhor[0]:
                    melhor = (ordem, chave, valores)
            if melhor:
                bases[dim] = (melhor[1], melhor[2])
        return bases

    def _decidir(self, valores: list[tuple[int, str, float]], critico: bool):
        """
        valores: (ficha, peso, proporção). Devolve (decisao|None, motivo, divergente).
        PESQUISA-RECEITAS §6.1 passos 4-5 e §6.2: ingrediente crítico divergente
        NÃO se resolve por média; decide fonte de peso alto, senão rejeita.
        """
        props = [v[2] for v in valores]
        med = _mediana(props)
        divergente = any(_fora(p, med, self.margem) for p in props)
        if not divergente:
            return med, "consenso entre as fontes", False
        if not critico:
            return med, "mediana das fontes (ingrediente não crítico)", True
        altos = [v[2] for v in valores if v[1] == "alto"]
        if not altos:
            return None, "sem fonte de peso alto para decidir", True
        med_alto = _mediana(altos)
        if any(_fora(p, med_alto, self.margem) for p in altos):
            return None, "fontes de peso alto também divergem", True
        return med_alto, "faixa de consenso entre fontes de peso alto", True

    # ---- consolidação ----------------------------------------------------

    def consolidar(self, pauta: dict, fichas: list[dict]) -> dict:
        fichas = sorted(
            (f for f in fichas if f.get("fatos", {}).get("ingredientes")),
            key=lambda f: _RANK_PESO.get(f.get("peso"), 9),
        )
        n = len(fichas)
        necessario = n // 2 + 1 if n else 1
        subcat = pauta.get("subcategoria", "")

        dominios = {f["dominio"] for f in fichas}
        n_altos = len({f["dominio"] for f in fichas if f.get("peso") == "alto"})

        grupos, falhas = self._agrupar(fichas)
        consenso_chaves = [c for c, por in grupos.items() if len(por) >= necessario]
        bases = self._escolher_bases({c: grupos[c] for c in consenso_chaves}, necessario) if n else {}

        # ---- ingredientes e proporções
        ingredientes, divergencias, nao_comparaveis, sem_decisao = [], [], [], []
        ref = 0  # fichas já vêm ordenadas por peso; a primeira é a de referência
        for chave in consenso_chaves:
            por_ficha = grupos[chave]
            critico = eh_critico(chave)
            dims = [l.medida.dimensao for l in por_ficha.values() if l.medida.valor]
            dim = max(set(dims), key=lambda d: (dims.count(d), d == "massa", d == "volume")) if dims else None
            nome = por_ficha[min(por_ficha)].nome
            entrada: dict[str, Any] = {"nome": nome, "critico": critico}
            if dim is None or dim == "unidade" or dim not in bases:
                nao_comparaveis.append(nome)
                if critico:
                    sem_decisao.append(f"{nome}: sem medida comparável")
                entrada["proporcao"] = None
                ingredientes.append(entrada)
                continue
            base_chave, base_valores = bases[dim]
            valores = []
            for i, l in por_ficha.items():
                if l.medida.dimensao == dim and l.medida.valor and i in base_valores:
                    valores.append((i, fichas[i].get("peso", ""), l.medida.valor / base_valores[i]))
            if chave == base_chave:
                decisao, motivo, div = 1.0, "ingrediente-base", False
            elif len(valores) < 2:
                if critico:
                    decisao, motivo, div = None, "menos de 2 fontes comparáveis", True
                else:
                    decisao, motivo, div = (valores[0][2] if valores else None), "fonte única comparável", False
            else:
                decisao, motivo, div = self._decidir(valores, critico)
            if div:
                divergencias.append(
                    {
                        "ponto": f"quantidade de {nome}",
                        "valores_proporcao": [round(v[2], 4) for v in valores],
                        "decisao": None if decisao is None else round(decisao, 4),
                        "motivo": motivo,
                    }
                )
            if decisao is None:
                if critico:
                    sem_decisao.append(f"{nome}: {motivo}")
                entrada["proporcao"] = None
                ingredientes.append(entrada)
                continue
            base_ref = base_valores.get(ref, _mediana(list(base_valores.values())))
            qtd = _arredondar(decisao * base_ref)
            entrada["proporcao"] = round(decisao, 4)
            entrada["quantidade_g" if dim == "massa" else "quantidade_ml"] = qtd
            entrada["aproximado"] = any(l.medida.aproximado for l in por_ficha.values())
            ingredientes.append(entrada)

        base_nome = None
        if bases:
            dim_p = "massa" if "massa" in bases else "volume"
            base_nome = grupos[bases[dim_p][0]][min(grupos[bases[dim_p][0]])].nome

        # ---- GATE-02: críticos sem normalização
        criticos_falha = [
            f"{x['nome']} ({x['falha']})"
            for chave, lista in falhas.items() if eh_critico(chave)
            for x in lista if x["falha"] != "sem_quantidade_numerica"
        ]

        # ---- tempos, temperaturas
        tempos, faixas = {}, {}
        for campo in ("preparo_min", "cozimento_min"):
            vals = [f["fatos"]["tempos"].get(campo) for f in fichas if f["fatos"]["tempos"].get(campo) is not None]
            if vals:
                med = _mediana([float(v) for v in vals])
                tempos[campo] = int(round(med))
                faixas[campo] = [min(vals), max(vals)]
                if any(_fora(v, med, self.margem) for v in vals):
                    divergencias.append(
                        {"ponto": campo, "valores": sorted(vals), "decisao": tempos[campo],
                         "motivo": "mediana das fontes"}
                    )
        por_ctx: dict[str, list[float]] = {}
        for f in fichas:
            for t in f["fatos"]["temperaturas"]:
                por_ctx.setdefault(normalizar_texto(t["contexto"]), []).append(t["celsius"])
        temperaturas = [
            {"contexto": ctx, "celsius": _arredondar(_mediana(v)), "fontes": len(v)}
            for ctx, v in por_ctx.items()
        ]

        # ---- técnicas, problemas e diferencial
        tecnica_consenso, pontos_unicos, problemas_consenso = [], [], []
        for campo, tipo in (("tecnicas", "tecnica"), ("problemas_comuns", "problema")):
            vistos: list[tuple[str, set[int]]] = []
            for idx, f in enumerate(fichas):
                for texto in f["fatos"][campo]:
                    for existente in vistos:
                        if _parecidos(texto, existente[0]):
                            existente[1].add(idx)
                            break
                    else:
                        vistos.append((texto, {idx}))
            for texto, quem in vistos:
                if len(quem) >= necessario:
                    (tecnica_consenso if tipo == "tecnica" else problemas_consenso).append(texto)
                else:
                    pontos_unicos.append(
                        {"tipo": tipo, "texto": texto, "fontes": sorted(fichas[i]["fonte"] for i in quem)}
                    )
        for chave, por in grupos.items():
            if len(por) < necessario:
                i = min(por)
                pontos_unicos.append(
                    {"tipo": "ingrediente", "texto": por[i].nome, "fontes": [fichas[i]["fonte"]]}
                )
        diferencial = None
        for tipo in ("tecnica", "problema", "ingrediente"):
            achado = next((p for p in pontos_unicos if p["tipo"] == tipo), None)
            if achado:
                diferencial = f'ponto único ({tipo}): {achado["texto"]}'
                break
        if diferencial is None and problemas_consenso:
            diferencial = f"consenso (problema comum): {problemas_consenso[0]}"

        # ---- rendimento (PESQUISA-RECEITAS §9)
        porcoes = None
        for f in fichas:
            m = re.search(r"\d+", str(f["fatos"].get("rendimento") or ""))
            if m:
                porcoes = int(m.group())
                break
        peso_total = sum(i.get("quantidade_g", 0) for i in ingredientes)
        rendimento = {"porcoes": porcoes, "base": None}
        if porcoes and peso_total > 0:
            rendimento["base"] = f"porção de cerca de {round(peso_total / porcoes)} g"

        # ---- catálogo, dieta
        consenso_para_catalogo = [i for i in ingredientes]
        nao_resolvidos, etiquetas = [], []
        if self.catalogo.disponivel:
            resolvidos = []
            for i in consenso_para_catalogo:
                r = self.catalogo.resolver(i["nome"])
                (resolvidos if r else nao_resolvidos).append(r or i["nome"])
            if not nao_resolvidos and resolvidos and not any(r.get("needs_label_check") for r in resolvidos):
                if all(r.get("vegetarian_ok") for r in resolvidos):
                    etiquetas.append("vegetariana")
                if all(r.get("vegan_ok") for r in resolvidos):
                    etiquetas.append("vegana")

        # ---- razões de sanidade, risco e segurança
        violacoes = self.razoes.avaliar(subcat, ingredientes)
        tecnicas_todas = [t for f in fichas for t in f["fatos"]["tecnicas"]]
        sinais = self.detector.sinais(ingredientes, tecnicas_todas, tempos)
        alertas, armazenamento, sem_entrada = [], None, []
        for s in sinais or []:
            entrada = self.seguranca.entrada(subcat, s)
            if entrada is None:
                sem_entrada.append(s)
                continue
            if entrada.get("alerta"):
                alertas.append(entrada["alerta"])
            if entrada.get("armazenamento") and armazenamento is None:
                armazenamento = entrada.get("chave") or f"{subcat}:{s}"

        flags = sorted({fl for f in fichas for fl in f["fatos"]["tecnica_flags"]})

        # ---- gate (PESQUISA-RECEITAS §12)
        itens = [
            _item(
                "GATE-01",
                "Ao menos 3 fontes de domínios diferentes e 1 de peso alto",
                len(dominios) >= self.minimo["fontes"] and n_altos >= self.minimo["peso_alto"],
                f"{len(dominios)} domínio(s) distinto(s), {n_altos} de peso alto "
                f"(mínimo {self.minimo['fontes']} e {self.minimo['peso_alto']})",
            ),
            _item(
                "GATE-02",
                "Medidas de ingredientes críticos normalizadas (conversoes.json)",
                not criticos_falha,
                "ok" if not criticos_falha else "sem conversão: " + "; ".join(criticos_falha[:5]),
            ),
            _item(
                "GATE-03",
                "Nenhum ingrediente crítico divergente sem decisão registrada",
                not sem_decisao and bool(ingredientes),
                "ok" if not sem_decisao and ingredientes else "; ".join(sem_decisao[:5]) or "sem ingredientes de consenso",
            ),
            _item(
                "GATE-04",
                "Nenhuma razão de sanidade violada",
                None if violacoes is None else not violacoes,
                "PENDENTE: razões não curadas para a família (config/razoes.json)"
                if violacoes is None else ("ok" if not violacoes else "; ".join(violacoes)),
            ),
            _item(
                "GATE-05",
                "Etiquetas de dieta calculadas pelo catálogo",
                True if self.catalogo.disponivel else None,
                "ok" if self.catalogo.disponivel else "PENDENTE: catálogo de ingredientes (Bloco 1 do site)",
            ),
            _item(
                "GATE-06",
                "Ingredientes resolvem no catálogo (Fase 0/1: vocabulário fechado)",
                (None if not self.catalogo.disponivel else (not nao_resolvidos or self.fase >= 2)),
                "PENDENTE: catálogo de ingredientes (Bloco 1 do site)" if not self.catalogo.disponivel
                else ("ok" if not nao_resolvidos else "fora do catálogo: " + ", ".join(map(str, nao_resolvidos[:8]))),
            ),
            _item(
                "GATE-07",
                "Sinais de risco com entrada na base curada (SEG-02)",
                None if sinais is None else not sem_entrada,
                "PENDENTE: detector de sinais de risco (validators SEG-01)" if sinais is None
                else ("ok" if not sem_entrada else "sinal sem entrada em config/seguranca.json: " + ", ".join(sem_entrada)),
            ),
            _item(
                "GATE-08",
                "Rendimento coerente com as quantidades",
                bool(porcoes and 1 <= porcoes <= 500 and peso_total > 0),
                "ok (faixa por subcategoria: PENDENTE, validators NUM-04)"
                if porcoes and 1 <= porcoes <= 500 and peso_total > 0
                else f"porções={porcoes}, peso total={peso_total} g",
            ),
            _item(
                "GATE-09",
                "Ficha traz diferencial e referências",
                bool(diferencial and fichas),
                "ok" if diferencial and fichas else "sem ponto único nem consenso para sugerir diferencial",
            ),
        ]
        aprovada = all(i["ok"] is True for i in itens)

        return {
            "pauta": {k: pauta.get(k) for k in ("tema", "categoria", "subcategoria")},
            "fontes_consultadas": n,
            "ingrediente_base": base_nome,
            "ingredientes_consenso": ingredientes,
            "divergencias": divergencias,
            "tecnica_consenso": tecnica_consenso,
            "tempos": tempos,
            "faixas_consenso": faixas,
            "temperaturas": temperaturas,
            "rendimento_estimado": rendimento,
            "etiquetas_dieta": etiquetas,
            "alertas_seguranca": alertas,
            "diferencial_sugerido": diferencial,
            "perguntas_comuns": [],  # PENDENTE: a doc não define a origem (02 §7.2)
            "armazenamento_base": armazenamento,
            "tecnica_flags": flags,
            "sinais_de_risco": sinais or [],
            "pontos_unicos": pontos_unicos,
            "nao_comparaveis": nao_comparaveis,
            "referencias_registro": [
                {"dominio": f["dominio"], "url": f["url"], "acessado_em": str(f["acessado_em"])[:10]}
                for f in fichas
            ],
            "status": "aprovada_para_criacao" if aprovada else "rejeitada",
            "gate": {"itens": itens, "conversoes_conferidas": bool(self.conv.get("conferido_contra_tabelas_publicadas"))},
        }
