"""Fixtures da pesquisa. Valores ILUSTRATIVOS: não representam dados reais de nenhuma fonte."""
from agents.analista import Analista, CatalogoMemoria

FONTES = {
    "panelinha": ("panelinha.com.br", "alto"),
    "receitasnestle": ("receitasnestle.com.br", "alto"),
    "tudogostoso": ("tudogostoso.com.br", "medio"),
    "receiteria": ("receiteria.com.br", "medio"),
    "receitasglobo": ("receitas.globo.com", "medio"),
    "cybercook": ("cybercook.com.br", "medio"),
}

CATALOGO = {
    "leite condensado": {"slug": "leite-condensado", "vegetarian_ok": True, "vegan_ok": False, "needs_label_check": False},
    "chocolate em pó": {"slug": "chocolate-em-po", "vegetarian_ok": True, "vegan_ok": False, "needs_label_check": False},
    "manteiga": {"slug": "manteiga", "vegetarian_ok": True, "vegan_ok": False, "needs_label_check": False},
}


def ing(nome, qtd, un):
    return {"nome": nome, "quantidade": qtd, "unidade": un}


def ficha(fonte, ingredientes, *, preparo=10, cozimento=15, rendimento="30 brigadeiros",
          tecnicas=("cozinhar mexendo sem parar até soltar do fundo",), problemas=(), flags=()):
    dominio, peso = FONTES[fonte]
    return {
        "fonte": fonte, "dominio": dominio, "url": f"https://{dominio}/receita", "acessado_em": "2026-11-11T08:03:00-03:00",
        "titulo_pagina": "Brigadeiro", "tipo_fonte": "x", "peso": peso,
        "fatos": {
            "ingredientes": ingredientes,
            "tempos": {"preparo_min": preparo, "cozimento_min": cozimento},
            "temperaturas": [], "rendimento": rendimento,
            "tecnicas": list(tecnicas), "problemas_comuns": list(problemas), "tecnica_flags": list(flags),
        },
    }


def fichas_aprovaveis():
    return [
        ficha("panelinha", [ing("leite condensado", "1", "lata"), ing("chocolate em pó", "40", "g"), ing("manteiga", "15", "g")],
              problemas=["queima se o fogo estiver alto"]),
        ficha("receitasnestle", [ing("leite condensado", "395", "g"), ing("chocolate em pó", "45", "g"), ing("manteiga", "1", "colher de sopa")]),
        ficha("tudogostoso", [ing("leite condensado", "2", "latas"), ing("chocolate em pó", "160", "g"), ing("manteiga", "30", "g")], cozimento=20),
        ficha("receiteria", [ing("leite condensado", "395", "g"), ing("chocolate em pó", "40", "g"), ing("manteiga", "15", "g"),
                             ing("granulado de chocolate", "50", "g")],
              tecnicas=("cozinhar mexendo sem parar até soltar do fundo", "enrolar com as mãos untadas")),
    ]


class RazoesOk:
    def avaliar(self, subcategoria, ingredientes):
        return []


class RazoesViolada:
    def avaliar(self, subcategoria, ingredientes):
        return ["chocolate fora da razão"]


class DetectorSemRisco:
    def sinais(self, ingredientes, tecnicas, tempos):
        return []


class DetectorOvoCru:
    def sinais(self, ingredientes, tecnicas, tempos):
        return ["ovo_cru_ou_malcozido"]


class SegurancaVazia:
    def entrada(self, subcategoria, sinal):
        return None


class SegurancaComEntrada:
    def entrada(self, subcategoria, sinal):
        return {"alerta": "alerta da base curada", "armazenamento": True, "chave": "base:x"}


def analista_ok(**kw):
    args = dict(catalogo=CatalogoMemoria(CATALOGO), razoes=RazoesOk(), detector=DetectorSemRisco(), seguranca=SegurancaVazia())
    args.update(kw)
    return Analista(**args)


PAUTA = {"tema": "Brigadeiro de colher cremoso", "categoria": "doces-e-sobremesas", "subcategoria": "brigadeiros-e-docinhos"}
