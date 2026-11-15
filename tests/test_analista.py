import pytest

from agents.analista import (
    Analista, CatalogoMemoria, carregar_conversoes, chave_ingrediente, eh_critico, normalizar_medida, parse_quantidade,
)
from helpers_pesquisa import (
    CATALOGO, DetectorOvoCru, PAUTA, RazoesViolada, SegurancaComEntrada, analista_ok, fichas_aprovaveis, ficha, ing,
)

CONV = carregar_conversoes()


def gate(res):
    return {i["id"]: i for i in res["gate"]["itens"]}


def test_parse_quantidade():
    assert parse_quantidade("1,5") == (1.5, False)
    assert parse_quantidade("1/2") == (0.5, False)
    assert parse_quantidade("1 1/2") == (1.5, False)
    assert parse_quantidade("2 a 3") == (2.5, True)
    assert parse_quantidade("a gosto") == (None, False)
    assert parse_quantidade(None) == (None, False) and parse_quantidade(0) == (None, False)


def test_chave_ingrediente_ignora_acento_plural_ordem_estado():
    assert chave_ingrediente("Chocolate meio-amargo picado") == chave_ingrediente("chocolate meio amargo")
    assert chave_ingrediente("Ovos") == chave_ingrediente("ovo")
    assert eh_critico(chave_ingrediente("farinha de trigo")) and not eh_critico(chave_ingrediente("canela"))


def test_conversoes_da_doc():
    m = lambda n, q, u: normalizar_medida(n, q, u, CONV)
    assert (m("leite condensado", "1", "lata").valor, m("leite condensado", "1", "lata").dimensao) == (395, "massa")
    assert m("creme de leite", "1", "caixinha").valor == 200 and m("creme de leite", "1", "lata").valor == 300
    assert m("farinha de trigo", "2", "xícaras").valor == 240 and m("farinha de trigo", "2", "xícaras").aproximado
    assert m("açúcar refinado", "1", "xícara").valor == 180
    assert m("leite", "1", "xícara de chá").valor == 240 and m("leite", "1", "xícara").dimensao == "volume"
    assert m("manteiga", "1", "colher de sopa").valor == 15 and m("sal", "1", "colher de chá").valor == 5
    assert m("farinha", "1", "kg").valor == 1000 and m("leite", "1", "l").valor == 1000
    assert m("ovos", "2", None).valor == 100


def test_medida_sem_conversao_nao_inventa():
    assert normalizar_medida("chocolate", "1", "lata", CONV).falha == "sem_conversao"
    assert normalizar_medida("leite", "1", "copo", CONV).falha == "unidade_desconhecida"
    assert normalizar_medida("sal", "a gosto", None, CONV).falha == "sem_quantidade_numerica"
    assert normalizar_medida("gemas", "2", "unidade", CONV).falha == "sem_conversao"


def test_ficha_aprovada_com_decisao_por_fonte_de_peso_alto():
    res = analista_ok().consolidar(PAUTA, fichas_aprovaveis())
    assert res["status"] == "aprovada_para_criacao", gate(res)
    assert res["ingrediente_base"] == "leite condensado"
    por_nome = {i["nome"]: i for i in res["ingredientes_consenso"]}
    assert por_nome["leite condensado"]["proporcao"] == 1.0
    assert por_nome["chocolate em pó"]["proporcao"] == pytest.approx(0.1076, abs=1e-3)
    assert por_nome["chocolate em pó"]["quantidade_g"] == pytest.approx(42.5, abs=1)
    div = res["divergencias"][0]
    assert div["ponto"] == "quantidade de chocolate em pó" and div["motivo"] == "faixa de consenso entre fontes de peso alto"
    assert "granulado de chocolate" not in por_nome
    assert res["tempos"] == {"preparo_min": 10, "cozimento_min": 15}
    assert res["tecnica_consenso"] and res["diferencial_sugerido"].startswith("ponto único (tecnica)")
    assert res["rendimento_estimado"]["porcoes"] == 30 and "porção de cerca de" in res["rendimento_estimado"]["base"]
    assert res["etiquetas_dieta"] == ["vegetariana"]
    assert len(res["referencias_registro"]) == 4 and res["referencias_registro"][0]["acessado_em"] == "2026-11-11"
    assert res["perguntas_comuns"] == [] and res["status"] == "aprovada_para_criacao"


def test_critico_divergente_sem_fonte_alto_rejeita():
    fs = [
        ficha("panelinha", [ing("leite condensado", "395", "g"), ing("manteiga", "15", "g")]),
        ficha("receitasnestle", [ing("leite condensado", "395", "g"), ing("manteiga", "15", "g")]),
        ficha("tudogostoso", [ing("leite condensado", "395", "g"), ing("chocolate em pó", "40", "g")]),
        ficha("receiteria", [ing("leite condensado", "395", "g"), ing("chocolate em pó", "100", "g")]),
        ficha("cybercook", [ing("leite condensado", "395", "g"), ing("chocolate em pó", "40", "g")]),
    ]
    res = analista_ok().consolidar(PAUTA, fs)
    assert res["status"] == "rejeitada" and gate(res)["GATE-03"]["ok"] is False
    assert "sem fonte de peso alto" in gate(res)["GATE-03"]["detalhe"]
    assert any(d["decisao"] is None for d in res["divergencias"])


def test_fontes_de_peso_alto_divergentes_rejeitam():
    fs = fichas_aprovaveis()
    fs[1]["fatos"]["ingredientes"][1]["quantidade"] = "120"
    assert gate(analista_ok().consolidar(PAUTA, fs))["GATE-03"]["ok"] is False


def test_fontes_insuficientes_e_sem_peso_alto():
    res = analista_ok().consolidar(PAUTA, fichas_aprovaveis()[:2])
    assert gate(res)["GATE-01"]["ok"] is False
    sem_alto = [f for f in fichas_aprovaveis() if f["peso"] != "alto"]
    assert gate(analista_ok().consolidar(PAUTA, sem_alto))["GATE-01"]["ok"] is False


def test_dominio_repetido_nao_conta_duas_vezes():
    fs = fichas_aprovaveis()[:2] + [fichas_aprovaveis()[0]]
    assert gate(analista_ok().consolidar(PAUTA, fs))["GATE-01"]["ok"] is False


def test_dependencias_pendentes_rejeitam_por_padrao():
    res = Analista().consolidar(PAUTA, fichas_aprovaveis())
    g = gate(res)
    assert res["status"] == "rejeitada"
    for id_ in ("GATE-04", "GATE-05", "GATE-06", "GATE-07"):
        assert g[id_]["ok"] is None and "PENDENTE" in g[id_]["detalhe"]
    for id_ in ("GATE-01", "GATE-02", "GATE-03", "GATE-08", "GATE-09"):
        assert g[id_]["ok"] is True


def test_razao_violada_rejeita():
    res = analista_ok(razoes=RazoesViolada()).consolidar(PAUTA, fichas_aprovaveis())
    assert gate(res)["GATE-04"]["ok"] is False and res["status"] == "rejeitada"


def test_sinal_de_risco_sem_entrada_rejeita_e_com_entrada_aprova():
    res = analista_ok(detector=DetectorOvoCru()).consolidar(PAUTA, fichas_aprovaveis())
    assert gate(res)["GATE-07"]["ok"] is False and res["sinais_de_risco"] == ["ovo_cru_ou_malcozido"]
    res = analista_ok(detector=DetectorOvoCru(), seguranca=SegurancaComEntrada()).consolidar(PAUTA, fichas_aprovaveis())
    assert res["status"] == "aprovada_para_criacao"
    assert res["alertas_seguranca"] == ["alerta da base curada"] and res["armazenamento_base"] == "base:x"


def test_ingrediente_fora_do_catalogo_na_fase_1_e_fase_2():
    cat = CatalogoMemoria({k: v for k, v in CATALOGO.items() if k != "manteiga"})
    assert gate(analista_ok(catalogo=cat, fase=1).consolidar(PAUTA, fichas_aprovaveis()))["GATE-06"]["ok"] is False
    res2 = analista_ok(catalogo=cat, fase=2).consolidar(PAUTA, fichas_aprovaveis())
    assert gate(res2)["GATE-06"]["ok"] is True and res2["etiquetas_dieta"] == []


def test_rotulo_variavel_bloqueia_etiquetas():
    cat = dict(CATALOGO)
    cat["chocolate em pó"] = {**cat["chocolate em pó"], "needs_label_check": True}
    assert analista_ok(catalogo=CatalogoMemoria(cat)).consolidar(PAUTA, fichas_aprovaveis())["etiquetas_dieta"] == []


def test_critico_sem_conversao_reprova_gate_02():
    fs = fichas_aprovaveis()
    fs[2]["fatos"]["ingredientes"][1] = ing("chocolate em pó", "1", "lata")
    res = analista_ok().consolidar(PAUTA, fs)
    assert gate(res)["GATE-02"]["ok"] is False and "chocolate em pó" in gate(res)["GATE-02"]["detalhe"]


def test_a_gosto_em_uma_fonte_nao_reprova_se_as_outras_decidem():
    fs = fichas_aprovaveis()
    fs[3]["fatos"]["ingredientes"][2] = ing("manteiga", "a gosto", None)
    assert analista_ok().consolidar(PAUTA, fs)["status"] == "aprovada_para_criacao"


def test_sem_diferencial_e_sem_rendimento_rejeitam():
    fs = fichas_aprovaveis()
    fs[3]["fatos"]["ingredientes"].pop()
    fs[3]["fatos"]["tecnicas"] = ["cozinhar mexendo sem parar até soltar do fundo"]
    fs[0]["fatos"]["problemas_comuns"] = []
    assert gate(analista_ok().consolidar(PAUTA, fs))["GATE-09"]["ok"] is False
    fs = fichas_aprovaveis()
    for f in fs:
        f["fatos"]["rendimento"] = None
    assert gate(analista_ok().consolidar(PAUTA, fs))["GATE-08"]["ok"] is False


def test_tecnica_flags_em_vocabulario_e_sem_texto_bruto_na_saida():
    fs = fichas_aprovaveis()
    fs[0]["fatos"]["tecnica_flags"] = ["ganache"]
    assert analista_ok().consolidar(PAUTA, fs)["tecnica_flags"] == ["ganache"]


def test_sem_fichas_nao_quebra():
    res = analista_ok().consolidar(PAUTA, [])
    assert res["status"] == "rejeitada" and gate(res)["GATE-01"]["ok"] is False
