import pytest

from agents.planejador import (
    AssuntoDica, AssuntosDicaMemoria, BloqueiosMemoria, CoberturaMock, FilaMemoria, HistoricoMemoria, ItemFila, Subcategoria,
    TaxonomiaMemoria, escolher_pauta,
)

SUBS = TaxonomiaMemoria([Subcategoria("doces-de-colher", "doces-e-sobremesas", "low", False), Subcategoria("antiga", "x", "low", True, active=False)])
ASSUNTOS = AssuntosDicaMemoria([AssuntoDica("preparo", "low", True), AssuntoDica("negocios", "medium", True),
                                AssuntoDica("ornamentacao", "low", False), AssuntoDica("velho", "low", True, active=False)])


def dica(itens, **kw):
    args = dict(fila=FilaMemoria(itens), taxonomia=SUBS, cobertura=CoberturaMock(), historico=HistoricoMemoria(), tipo_conteudo="dica",
                assuntos=ASSUNTOS, fase=1)
    args.update(kw)
    return escolher_pauta(**args)


def test_pauta_de_dica_com_e_sem_subcategoria():
    r = dica([ItemFila("Ganache talhou?", assunto="preparo", subcategoria="doces-de-colher")])
    d = r.pauta.to_dict()
    assert d["assunto"] == "preparo" and d["subcategoria"] == "doces-de-colher" and d["categoria"] == "doces-e-sobremesas"
    assert d["tipo_conteudo"] == "dica" and d["topic_slug"] == "ganache-talhou"
    r2 = dica([ItemFila("Como organizar a produção", assunto="preparo")])
    assert r2.pauta.subcategoria is None and r2.pauta.categoria is None and r2.pauta.to_dict()["subcategoria"] is None


def test_subcategoria_da_dica_nao_precisa_estar_habilitada_mas_precisa_existir():
    assert dica([ItemFila("a b", assunto="preparo", subcategoria="doces-de-colher")]).pauta is not None  # agent_enabled=False
    for sub in ("inexistente", "antiga"):
        r = dica([ItemFila("a b", assunto="preparo", subcategoria=sub)])
        assert r.pauta is None and r.descartadas[0]["codigo"] == "TAX-01"


def test_assunto_limitado_pela_fase_e_pela_habilitacao():
    itens = [ItemFila("t1", assunto="negocios"), ItemFila("t2", assunto="ornamentacao"), ItemFila("t3", assunto="velho"),
             ItemFila("t4", assunto="nao-existe"), ItemFila("t5")]
    r = dica(itens, fase=1)
    assert r.pauta is None and [d["codigo"] for d in r.descartadas] == ["TAX-02", "TAX-01", "TAX-01", "TAX-01", "TAX-01"]
    assert dica(itens, fase=2).pauta.assunto == "negocios"
    assert dica(itens, fase=0).pauta is None


def test_exige_interface_de_assuntos_e_tecnica_continua_pendente():
    with pytest.raises(ValueError, match="assuntos"):
        dica([ItemFila("x", assunto="preparo")], assuntos=None)
    with pytest.raises(NotImplementedError):
        dica([], tipo_conteudo="tecnica")


def test_historico_separa_dica_de_receita_com_o_mesmo_tema():
    h = HistoricoMemoria()
    assert h.reservar_pauta("recipe", "ganache-talhou", "x", "y")
    assert dica([ItemFila("Ganache talhou?", assunto="preparo")], historico=h).pauta is not None


def test_bloqueios_recebem_assunto_quando_nao_ha_subcategoria():
    b = BloqueiosMemoria({"conserva": ["conserva"]})
    r = dica([ItemFila("Conserva de palmito", assunto="preparo")], bloqueios=b)
    assert r.pauta is None and r.descartadas[0]["codigo"] == "TAX-03"


def test_receita_nao_mudou():
    r = escolher_pauta(FilaMemoria([ItemFila("Brigadeiro", "doces-de-colher")]), TaxonomiaMemoria([Subcategoria("doces-de-colher", "doces-e-sobremesas", "low", True)]),
                       CoberturaMock(), HistoricoMemoria(), fase=1)
    assert "assunto" not in r.pauta.to_dict() and r.pauta.tipo_conteudo == "receita"
