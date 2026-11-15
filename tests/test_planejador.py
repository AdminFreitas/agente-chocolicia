from datetime import date

import pytest

from agents.planejador import (
    BloqueiosMemoria, CoberturaItem, CoberturaMock, ConteudoExistenteMemoria, FilaMemoria, HistoricoMemoria,
    ItemFila, Subcategoria, TaxonomiaMemoria, carregar_calendario, escolher_pauta, gerar_topic_slug,
    pontuar_sazonalidade,
)

SUBS = TaxonomiaMemoria([
    Subcategoria("brigadeiros-e-docinhos", "doces-e-sobremesas", "low", True),
    Subcategoria("bolos-simples", "bolos-e-tortas", "low", True),
    Subcategoria("tortas-salgadas", "bolos-e-tortas", "medium", True),
    Subcategoria("trufas-e-bombons", "doces-e-sobremesas", "low", False),
    Subcategoria("bovina", "carnes", "high", True),
])
HOJE = date(2026, 11, 11)


def planejar(itens, **kw):
    args = dict(fila=FilaMemoria(itens), taxonomia=SUBS, cobertura=CoberturaMock(), historico=HistoricoMemoria(), hoje=HOJE)
    args.update(kw)
    return escolher_pauta(**args)


def test_topic_slug_do_tema():
    assert gerar_topic_slug("Brigadeiro de colher cremoso") == "brigadeiro-de-colher-cremoso"
    assert gerar_topic_slug("  Pão de Mel!! ") == "pao-de-mel"
    with pytest.raises(ValueError):
        gerar_topic_slug("!!!")


def test_cobertura_menor_vence():
    cob = CoberturaMock({"brigadeiros-e-docinhos": CoberturaItem(publicados=5), "bolos-simples": CoberturaItem(publicados=0, rascunhos=0)})
    r = planejar([ItemFila("Bolo de fubá", "bolos-simples"), ItemFila("Brigadeiro branco", "brigadeiros-e-docinhos")], cobertura=cob)
    assert r.pauta.subcategoria == "bolos-simples"
    assert r.pauta.categoria == "bolos-e-tortas" and r.pauta.topic_slug == "bolo-de-fuba"


def test_fase_filtra_risco_e_habilitacao():
    itens = [ItemFila("Torta de frango", "tortas-salgadas"), ItemFila("Bife", "bovina"),
             ItemFila("Trufa", "trufas-e-bombons"), ItemFila("X", "inexistente")]
    r = planejar(itens, fase=1)
    assert r.pauta is None
    assert {d["codigo"] for d in r.descartadas} == {"TAX-01", "TAX-02"}
    assert planejar(itens, fase=2).pauta.tema == "Torta de frango"


def test_reserva_evita_repetir_tema():
    h = HistoricoMemoria()
    fila = [ItemFila("Brigadeiro branco", "brigadeiros-e-docinhos")]
    assert planejar(fila, historico=h).pauta is not None
    r2 = planejar(fila, historico=h)
    assert r2.pauta is None and r2.descartadas[0]["codigo"] == "DUP-HIST"


def test_reserva_concorrente_passa_para_o_proximo():
    class Disputado(HistoricoMemoria):
        def reservar_pauta(self, ct, slug, tema, sub):
            return False if slug == "a" else super().reservar_pauta(ct, slug, tema, sub)
    r = planejar([ItemFila("A", "bolos-simples", prioridade=9), ItemFila("B", "bolos-simples")], historico=Disputado())
    assert r.pauta.tema == "B" and any(d["codigo"] == "RESERVA" for d in r.descartadas)


def test_bloqueio_existente_e_data_minima():
    itens = [ItemFila("Conserva de palmito", "bolos-simples"), ItemFila("Bolo repetido", "bolos-simples"),
             ItemFila("Bolo futuro", "bolos-simples", data_minima=date(2026, 12, 1)), ItemFila("Bolo ok", "bolos-simples")]
    r = planejar(itens, bloqueios=BloqueiosMemoria({"conserva": ["conserva"]}),
                 conteudo_existente=ConteudoExistenteMemoria({"bolo-repetido"}))
    assert r.pauta.tema == "Bolo ok"
    assert {d["codigo"] for d in r.descartadas} == {"TAX-03", "SIM-04", "DATA"}
    assert r.pauta.avisos == []


def test_avisos_de_pendencia_sem_interfaces():
    r = planejar([ItemFila("Bolo ok", "bolos-simples")])
    assert any("pautas bloqueadas" in a for a in r.pauta.avisos) and any("lookup" in a for a in r.pauta.avisos)


def test_origem_search_console_aceita_e_invalida_recusada():
    r = planejar([ItemFila("Bolo A", "bolos-simples", origem="search_console", tendencia=0.9), ItemFila("Bolo B", "bolos-simples", origem="xpto")])
    assert r.pauta.origem == "search_console"
    assert r.descartadas[0]["codigo"] == "ORIGEM"


def test_pauta_no_formato_da_doc():
    d = planejar([ItemFila("Brigadeiro", "brigadeiros-e-docinhos", ocasioes=("festas",), dificuldade_alvo="Fácil")]).pauta.to_dict()
    for chave in ("tipo_conteudo", "tema", "categoria", "subcategoria", "ocasiao", "dieta", "dificuldade_alvo", "observacoes", "topic_slug"):
        assert chave in d
    assert d["tipo_conteudo"] == "receita"


def test_calendario_da_doc_esta_a_definir_e_nao_pontua():
    cal = carregar_calendario()
    assert len(cal["datas"]) == 8 and all(e["data"] == "a definir" for e in cal["datas"])
    assert cal["antecedencia_semanas"] == "a definir"
    assert pontuar_sazonalidade(ItemFila("x", "y", ocasioes=("natal",)), cal, HOJE) == 0.0


def test_sazonalidade_com_datas_numericas():
    cal = {"antecedencia_semanas": 4, "datas": [{"ocasiao_slug": "natal", "data": "12-25"}, {"ocasiao_slug": "pascoa", "data": "2027-03-28"}]}
    item = ItemFila("x", "y", ocasioes=("natal",))
    assert pontuar_sazonalidade(item, cal, date(2026, 12, 20)) > pontuar_sazonalidade(item, cal, date(2026, 12, 1)) > 0
    assert pontuar_sazonalidade(item, cal, date(2026, 11, 1)) == 0.0
    assert pontuar_sazonalidade(ItemFila("x", "y", ocasioes=("pascoa",)), cal, date(2026, 11, 11)) == 0.0


def test_sazonalidade_decide_empate():
    cal = {"antecedencia_semanas": 4, "datas": [{"ocasiao_slug": "natal", "data": "12-25"}]}
    r = planejar([ItemFila("Bolo comum", "bolos-simples"), ItemFila("Bolo de Natal", "bolos-simples", ocasioes=("natal",))],
                 calendario=cal, hoje=date(2026, 12, 15))
    assert r.pauta.tema == "Bolo de Natal"
