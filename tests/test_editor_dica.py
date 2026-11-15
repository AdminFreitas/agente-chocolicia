import pytest

from agents import editor as E
from helpers_criacao import GerarFalso
from helpers_dica import corpo_dica, dica_valida, ficha_dica, js

PAUTA = {"tema": "Ganache talhou? Como recuperar", "assunto": "preparo", "subcategoria": "doces-de-colher", "categoria": "doces-e-sobremesas"}


def criar(respostas, pauta=PAUTA, **kw):
    g = GerarFalso(respostas)
    return E.criar_dica(ficha_dica(), pauta, gerar=g, **kw), g


def test_dica_valida_pendente_sem_validador_e_prompt_em_camadas():
    r, g = criar([js(dica_valida())])
    assert r.status == "pendente_validacao" and r.tentativas == 1 and r.prompt_version == "base@1.0.0+dica@1.1.0"
    tarefa, prompt, _ = g.chamadas[0]
    assert tarefa == "criacao" and "TIPO DE CONTEÚDO: dica" in prompt and '"assunto": "preparo"' in prompt
    assert prompt.index("Você é o Chef IA") < prompt.index("TAREFA: criar uma DICA") < prompt.index("TIPO DE CONTEÚDO")
    assert r.conteudo["subcategoria"] == "doces-de-colher" and r.conteudo["assunto"] == "preparo"


def test_regras_por_assunto_estao_no_prompt():
    _, g = criar([js(dica_valida())])
    p = " ".join(g.chamadas[0][1].split())  # o prompt quebra linhas no meio das frases
    for trecho in ("equipamentos-compra", "NUNCA cite marcas", "negocios", "aconselhamento jurídico", "manual do fabricante"):
        assert trecho in p


def test_ficha_nao_aprovada_e_pauta_sem_assunto():
    f = ficha_dica(status="rejeitada")
    with pytest.raises(ValueError, match="não aprovada"):
        E.criar_dica(f, PAUTA, gerar=GerarFalso([]))
    with pytest.raises(ValueError, match="assunto"):
        E.criar_dica(ficha_dica(), {"tema": "x"}, gerar=GerarFalso([]))


@pytest.mark.parametrize("palavras,ok", [(149, False), (150, True), (400, True), (401, False)])
def test_tamanho_do_corpo_e_sch_03(palavras, ok):
    resp, falhas = E.validar_saida_dica(js(dica_valida(corpo=corpo_dica(palavras))), PAUTA)
    assert (resp is not None) is ok and ([f.id for f in falhas] == [] if ok else {f.id for f in falhas} == {"SCH-03"})
    assert ok or falhas[0].campo == "corpo"


def test_assunto_e_subcategoria_vem_da_pauta():
    resp, falhas = E.validar_saida_dica(js(dica_valida(assunto="negocios")), PAUTA)
    assert resp is not None and [(f.id, f.campo) for f in falhas] == [("SCH-04", "assunto")]
    resp, falhas = E.validar_saida_dica(js(dica_valida(subcategoria="bolos-simples")), PAUTA)
    assert [(f.id, f.campo) for f in falhas] == [("SCH-04", "subcategoria")]
    resp, falhas = E.validar_saida_dica(js(dica_valida(subcategoria="")), PAUTA)  # pauta tem subcategoria; vazio diverge
    assert falhas and falhas[0].campo == "subcategoria"


def test_pauta_sem_subcategoria_aceita_vazia_e_recusa_preenchida():
    p = {"tema": "x", "assunto": "negocios", "subcategoria": None, "categoria": None}
    assert E.validar_saida_dica(js(dica_valida(assunto="negocios", subcategoria="")), p)[1] == []
    assert E.validar_saida_dica(js(dica_valida(assunto="negocios", subcategoria=None)), p)[1] == []
    assert E.validar_saida_dica(js(dica_valida(assunto="negocios")), p)[1][0].campo == "subcategoria"
    _, g = criar([js(dica_valida(assunto="negocios", subcategoria=""))], pauta=p)
    assert "nenhuma (esta pauta não tem subcategoria" in g.chamadas[0][1]


def test_campos_do_sistema_e_limites():
    for ch in ({"slug": "x"}, {"status": "published"}, {"texto_alt_imagem": "x" * 30}):  # alt vem do SEO, não da dica
        resp, falhas = E.validar_saida_dica(js(dica_valida(**ch)), PAUTA)
        assert resp is None and falhas[0].id == "SCH-04"
    for ch in ({"titulo": "abc"}, {"temas_relacionados": ["só um"]}, {"temas_relacionados": list("abcde")},
               {"termos_busca_imagem": ["a", "b"]}, {"resposta_direta": ""}, {"descricao_curta": "curta"}):
        resp, falhas = E.validar_saida_dica(js(dica_valida(**ch)), PAUTA)
        assert resp is None and falhas[0].id in ("SCH-03", "SCH-02")


def test_reparo_de_dica_com_tamanho_e_rejeicao_final():
    r, g = criar([js(dica_valida(corpo=corpo_dica(100))), js(dica_valida())])
    assert r.status == "pendente_validacao" and r.tentativas == 2 and [c[0] for c in g.chamadas] == ["criacao", "reparo"]
    assert "SCH-03 (corpo)" in g.chamadas[1][1] and "100 palavras" in g.chamadas[1][1] and r.prompt_version.endswith("reparo@1.0.0")
    r, g = criar(["x", "y", "z"])
    assert r.status == "rejeitado" and r.rejection_code == "SCH-01" and r.tentativas == 3


def test_validador_aprova_e_receita_continua_funcionando():
    class V:
        def validar(self, c, ctx): return [E.Falha("HON-08", "marca citada", campo="corpo")] if "marca" in c["corpo"] else []
    r, _ = criar([js(dica_valida())], validador=V())
    assert r.status == "aprovado"
    r, g = criar([js(dica_valida(corpo=corpo_dica(200) + " marca")), js(dica_valida())], validador=V())
    assert r.status == "aprovado" and "HON-08 (corpo)" in g.chamadas[1][1]
    assert E.RespostaReceita.model_fields and E.criar_receita  # a receita não foi afetada
