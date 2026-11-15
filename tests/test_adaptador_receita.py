import pytest

from agents.analista import CatalogoMemoria, SemCatalogo
from integration import adaptador_receita as A
from integration.cliente_site import ContratoInvalido
from helpers_criacao import ficha_aprovada
from helpers_integracao import COVER_GERAR, COVER_STOCK, PAUTA, conteudo_editor, payload
from helpers_pesquisa import CATALOGO


def test_mapeamento_completo():
    p = payload(status="published", cover=COVER_STOCK, storage_notes="Conserve na geladeira.", colecoes=["chocolate"])
    d = p.model_dump(mode="json", exclude_none=True)
    c = conteudo_editor()
    assert d["title"] == c["titulo"] and d["excerpt"] == c["descricao_curta"] and d["intro"] == c["introducao"]
    assert d["subcategorySlug"] == "brigadeiros-e-docinhos" and d["slug"] == "brigadeiro-de-colher-cremoso-com-chocolate"
    assert (d["prepTimeMin"], d["cookTimeMin"], d["servings"], d["yieldLabel"]) == (10, 15, 8, "8 porções") and "restTimeMin" not in d
    assert d["status"] == "published" and d["cover"] == COVER_STOCK and d["coverImageAlt"] == c["texto_alt_imagem"]
    assert d["storageNotes"] == "Conserve na geladeira." and d["collections"] == ["chocolate"] and d["occasions"] == ["festas"]
    item = d["ingredients"][0]["items"][0]
    assert item == {"name": "leite condensado", "quantity": "395", "unit": "g", "note": "1 lata", "ingredientSlug": "leite-condensado"}
    assert d["steps"][0] == {"title": "Misturar", "instruction": c["modo_preparo"][0]["instrucao"]}
    assert d["aiModel"] == "p/m" and d["diet"] == ["vegetariana"]
    gm = d["generationMeta"]
    assert gm["run_id"] == "run-1" and gm["topic_slug"] == "brigadeiro-de-colher-cremoso" and gm["phase"] == 1
    assert gm["prompt_version"] == "base@1.0.0+receita@1.1.0" and gm["validators_version"] == "pendente"
    assert gm["sources"][0] == {"domain": "panelinha.com.br", "url": "https://panelinha.com.br/receita", "date": "2026-11-11"}
    assert gm["technique_flags"] == []
    assert not any(k in d for k in ("dificuldade", "autor", "aviso_leitor", "alertas_internos", "termos_busca_imagem", "prompt_imagem"))


def test_status_padrao_draft_e_dica_extra_vai_para_tips_e_faq():
    assert payload().status == "draft"
    p = payload(conteudo=conteudo_editor(dica_extra="Use fogo baixo.", perguntas_frequentes=[{"pergunta": "Posso congelar?", "resposta": "Sim."}]))
    d = p.model_dump(mode="json", exclude_none=True)
    assert d["tips"] == ["Use fogo baixo."] and d["faq"] == [{"question": "Posso congelar?", "answer": "Sim."}]
    assert payload().tips == []


@pytest.mark.parametrize("passos,flags,esperado", [
    (4, [], "Fácil"), (8, [], "Fácil"), (9, [], "Média"), (15, [], "Média"), (16, [], "Difícil"), (20, [], "Difícil"),
    (5, ["ganache"], "Média"), (5, ["creme", "ganache"], "Média"), (5, ["caramelo"], "Difícil"), (12, ["massa-fermentada"], "Difícil"),
    (5, ["temagem-desconhecida"], "Difícil"), (16, ["ganache"], "Difícil"),
])
def test_dificuldade_por_codigo(passos, flags, esperado):
    assert A.calcular_dificuldade(passos, flags) == esperado


def test_dificuldade_usa_as_flags_da_ficha():
    f = ficha_aprovada(); f["tecnica_flags"] = ["ganache"]
    p = payload(ficha=f)
    assert p.difficulty == "Média" and p.generationMeta.technique_flags == ["ganache"]


def test_slug_e_tags():
    assert A.slugificar("Pão de Mel — Chocolate!", 180) == "pao-de-mel-chocolate"
    assert A.slugificar("Ação " * 30, 40) == A.slugificar("Ação " * 30, 40) and len(A.slugificar("a" * 100, 40)) == 40
    c = conteudo_editor(tags=["Chocolate", "chocolate", "Doce de Colher", "festas", "brigadeiros-e-docinhos", "vegetariana", "Pão de mel", "  ", "festa infantil"])
    assert payload(conteudo=c).tags == ["chocolate", "doce-de-colher", "pao-de-mel", "festa-infantil"]  # sem repetir ocasião, subcategoria ou dieta
    assert len(payload(conteudo=conteudo_editor(tags=[f"tag{i}" for i in range(12)])).tags) == 12


def test_tag_reservada_desabilitada_nao_passa():
    with pytest.raises(ContratoInvalido) as e:
        payload(conteudo=conteudo_editor(tags=["chocolate", "sem glúten"]))
    assert "sem-gluten" in str(e.value)


def test_ingrediente_fora_do_catalogo_por_fase():
    c = conteudo_editor()
    c["ingredientes"][0]["itens"][2]["nome"] = "manteiga clarificada"
    with pytest.raises(A.IngredienteForaDoCatalogo) as e:
        payload(conteudo=c, fase=1)
    assert e.value.nomes == ["manteiga clarificada"] and isinstance(e.value, ContratoInvalido)
    with pytest.raises(A.IngredienteForaDoCatalogo):
        payload(conteudo=c, fase=0)
    p = payload(conteudo=c, fase=2)  # Fase 2+: unresolved aceito, sem slug (docs/04 §7.2)
    assert p.ingredients[0].items[2].ingredientSlug is None and p.ingredients[0].items[0].ingredientSlug == "leite-condensado"


def test_catalogo_indisponivel_trava_nas_fases_0_e_1():
    with pytest.raises(A.IngredienteForaDoCatalogo):
        payload(catalogo=SemCatalogo(), fase=1)
    assert payload(catalogo=SemCatalogo(), fase=2).ingredients[0].items[0].ingredientSlug is None


def test_cover_obrigatoria_e_subcategoria_da_pauta():
    with pytest.raises(ContratoInvalido, match="sem capa"):
        A.montar_payload_receita(
            conteudo_editor(), pauta=PAUTA, ficha=ficha_aprovada(), cover=None, run_id="r", fase=1, modelo={}, prompt_version="x",
            catalogo=CatalogoMemoria(CATALOGO))
    with pytest.raises(ContratoInvalido, match="subcategoria"):
        payload(pauta=dict(PAUTA, subcategoria="bolos-simples"))
    with pytest.raises(ContratoInvalido, match="topic_slug"):
        payload(pauta={k: v for k, v in PAUTA.items() if k != "topic_slug"})


def test_unidade_fora_do_vocabulario_e_contrato():
    c = conteudo_editor(); c["ingredientes"][0]["itens"][1]["unidade"] = "xícaras"
    with pytest.raises(ContratoInvalido, match="unit"):
        payload(conteudo=c)


def test_ai_model():
    assert payload(modelo={"provedor": "groq", "modelo": "llama"}).aiModel == "groq/llama"
    assert payload(modelo={}).aiModel == "nao-informado"
    assert len(payload(modelo={"provedor": "p", "modelo": "m" * 300}).aiModel) == 120


def test_reduzir_opcionais_nunca_toca_o_essencial():
    d = payload(conteudo=conteudo_editor(dica_extra="d", perguntas_frequentes=[{"pergunta": "a?", "resposta": "b"}])).model_dump(mode="json", exclude_none=True)
    r1 = A.reduzir_opcionais(d); r2 = A.reduzir_opcionais(r1); r3 = A.reduzir_opcionais(r2)
    assert "faq" not in r1 and "tips" in r1 and "tips" not in r2 and r3 == r2
    assert r3["ingredients"] == d["ingredients"] and r3["steps"] == d["steps"] and "faq" in d
