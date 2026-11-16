"""Validações por código, com IDs de docs/08-VALIDACAO.md.

As listas de curadoria são deliberadamente lidas do config e, quando vazias,
produzem bloqueio. O módulo não consulta rede nem LLM.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class FalhaValidacao:
    id: str
    gravidade: str = "bloqueante"
    detalhe: str = ""
    campo: str | None = None


@dataclass
class ResultadoValidacao:
    falhas: list[FalhaValidacao] = field(default_factory=list)
    avisos: list[FalhaValidacao] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.falhas

    def adicionar(self, falha: FalhaValidacao) -> None:
        (self.avisos if falha.gravidade == "aviso" else self.falhas).append(falha)


def _texto(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_texto(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_texto(v) for v in obj)
    return ""


def _config(nome: str) -> dict:
    caminho = ROOT / "config" / nome
    if not caminho.exists():
        return {"fonte": "docs/08-VALIDACAO.md", "itens": []}
    return json.loads(caminho.read_text(encoding="utf-8"))


def validar_conteudo(conteudo: dict, contexto: dict | None = None) -> ResultadoValidacao:
    """Executa as verificações implementadas em ordem de segurança."""
    ctx = contexto or {}
    r = ResultadoValidacao()
    _sch(r, conteudo, ctx)
    _tax(r, conteudo, ctx)
    _num(r, conteudo, ctx)
    _cul(r, conteudo, ctx)
    _alg(r, conteudo, ctx)
    _seg(r, conteudo, ctx)
    _hon(r, conteudo, ctx)
    _sim(r, conteudo, ctx)
    _img(r, conteudo, ctx)
    _seo(r, conteudo, ctx)
    return r


def _add(r, id_: str, detalhe: str, campo: str | None = None, aviso: bool = False):
    r.adicionar(FalhaValidacao(id_, "aviso" if aviso else "bloqueante", detalhe, campo))


def _sch(r, c, x):
    if not isinstance(c, dict): _add(r, "SCH-01", "a saída deve ser um objeto JSON")
    if len(c.get("ingredientes", [])) < 1: _add(r, "SCH-07", "ingredientes ausentes", "ingredientes")
    if len(c.get("modo_preparo", [])) < 4: _add(r, "SCH-07", "menos de 4 passos", "modo_preparo")
    for k, v in c.items():
        if isinstance(v, str) and ("<script" in v.lower() or "http://" in v or "https://" in v):
            _add(r, "SCH-05", "HTML ou URL não permitido", k)


def _tax(r, c, x):
    pauta = x.get("pauta", {})
    if pauta.get("subcategoria") and c.get("subcategoria") != pauta["subcategoria"]:
        _add(r, "TAX-01", "subcategoria diferente da pauta", "subcategoria")
    reservadas = {"sem-gluten", "sem-lactose"}
    if reservadas & set(c.get("tags", []) or []): _add(r, "TAX-05", "etiqueta reservada")


def _num(r, c, x):
    unidades = {"g", "kg", "ml", "l", "unidade", "pitada", "dente", "fatia", "lata", "caixinha", "maço", "ramo", "xícara", "colher de sopa", "colher de chá"}
    for sec in c.get("ingredientes", []) or []:
        for item in sec.get("itens", []) or []:
            if item.get("unidade") not in unidades: _add(r, "NUM-07", "unidade fora do vocabulário", "unidade")
            if str(item.get("quantidade", "")).strip().lower() in {"", "a gosto", "um pouco"}:
                _add(r, "NUM-08", "quantidade não interpretável", "quantidade")


def _cul(r, c, x):
    passos = c.get("modo_preparo", []) or []
    if len({p.get("instrucao", "") for p in passos}) != len(passos): _add(r, "CUL-06", "passos duplicados")
    for p in passos:
        t = p.get("instrucao", "").lower()
        if any(w in t for w in ("forno", "assar", "fritar", "fogo")) and not re.search(r"\d+|ponto|dourad|firm", t):
            _add(r, "CUL-08", "passo de fogo/forno sem tempo ou sinal de ponto")


def _alg(r, c, x):
    catalogo = x.get("catalogo")
    if catalogo is not None and not getattr(catalogo, "disponivel", False): _add(r, "ALG-01", "catálogo indisponível")
    texto = _texto(c).lower()
    if any(t in texto for t in ("sem glúten", "sem lactose", "zero lactose", "para celíacos", "hipoalergênico")): _add(r, "ALG-05", "alegação de dieta não permitida")


def _seg(r, c, x):
    riscos = x.get("riscos", [])
    base = _config("seguranca.json").get("itens", [])
    if riscos and not base: _add(r, "SEG-02", "risco sem curadoria em config/seguranca.json")


def _hon(r, c, x):
    texto = _texto(c).lower()
    proibidas = _config("frases_proibidas.json").get("itens", [])
    termos = [i.get("termo", "") if isinstance(i, dict) else str(i) for i in proibidas]
    termos += ["testamos", "testada", "garantido", "infalível", "emagrece", "cura", "fizemos"]
    for termo in termos:
        if termo and termo.lower() in texto: _add(r, "HON-01", f"frase proibida: {termo}")


def _sim(r, c, x):
    fontes = x.get("fontes_texto", [])
    texto = _texto(c).lower()
    for fonte in fontes:
        palavras = [p for p in re.findall(r"[a-záéíóúàâêôãõç]+", str(fonte).lower()) if len(p) > 2]
        for i in range(max(0, len(palavras) - 9)):
            if " ".join(palavras[i:i + 10]) in texto: _add(r, "SIM-01", "sequência idêntica à fonte")


def _img(r, c, x):
    alt = c.get("texto_alt_imagem", "")
    if not 20 <= len(alt) <= 140: _add(r, "IMG-08", "texto alternativo fora do intervalo", "texto_alt_imagem")


def _seo(r, c, x):
    if not c.get("titulo"): _add(r, "SEO-01", "título ausente", "titulo")
