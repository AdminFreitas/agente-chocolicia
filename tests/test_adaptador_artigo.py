import pytest

from integration.adaptador_artigo import montar_payload_dica
from integration.cliente_site import ContratoInvalido
from helpers_criacao import PAUTA_RECEITA
from helpers_dica import dica_valida, ficha_dica, seo_dica
from helpers_integracao import COVER_GERAR, COVER_STOCK

PAUTA = {"tema": "Ganache talhou? Como recuperar", "tipo_conteudo": "dica", "assunto": "preparo", "subcategoria": "doces-de-colher",
         "categoria": "doces-e-sobremesas", "topic_slug": "ganache-talhou-como-recuperar"}


def conteudo(**ch):
    d = dica_valida(); d.update({"texto_alt_imagem": seo_dica()["texto_alt_imagem"]}); d.update(ch)
    return d


def montar(c=None, pauta=PAUTA, **kw):
    args = dict(pauta=pauta, ficha=ficha_dica(), cover=COVER_GERAR, run_id="run-7", fase=1, modelo={"provedor": "p", "modelo": "m"},
                prompt_version="base@1.0.0+dica@1.1.0")
    args.update(kw)
    return montar_payload_dica(c or conteudo(), **args)


def test_mapeamento_da_dica():
    d = montar(status="published", cover=COVER_STOCK).model_dump(mode="json", exclude_none=True)
    c = conteudo()
    assert d["type"] == "tip" and d["tipTopic"] == "preparo" and d["subcategorySlug"] == "doces-de-colher"
    assert (d["title"], d["excerpt"], d["bodyMd"]) == (c["titulo"], c["descricao_curta"], c["corpo"])
    assert d["slug"] == "ganache-talhou-como-recuperar" and d["structured"] == {"direct_answer": c["resposta_direta"]}
    assert d["relatedTopics"] == c["temas_relacionados"] and d["status"] == "published" and d["cover"] == COVER_STOCK
    assert d["coverImageAlt"] == "Ganache de chocolate lisa e brilhante em uma tigela" and d["aiModel"] == "p/m"
    gm = d["generationMeta"]
    assert (gm["run_id"], gm["topic_slug"], gm["phase"], gm["validators_version"]) == ("run-7", PAUTA["topic_slug"], 1, "pendente")
    assert gm["sources"][0] == {"domain": "panelinha.com.br", "url": "https://panelinha.com.br/x", "date": "2026-11-12"}
    assert not any(k in d for k in ("alertas_internos", "prompt_imagem", "termos_busca_imagem")) and montar().status == "draft"
    assert d["sources"] == []  # fontes de dica: só em generationMeta (06 §8 exige sources apenas em técnica e matéria)


def test_dica_sem_subcategoria():
    p = dict(PAUTA, subcategoria=None, categoria=None)
    d = montar(conteudo(subcategoria=None), pauta=p).model_dump(mode="json", exclude_none=True)
    assert "subcategorySlug" not in d and d["tipTopic"] == "preparo"
    assert montar(conteudo(subcategoria=""), pauta=p).subcategorySlug is None


def test_tags_sem_repetir_assunto_ou_subcategoria():
    t = montar(conteudo(tags=["Preparo", "doces de colher", "Ganache", "ganache", "Chocolate Quente", "  "])).tags
    assert t == ["ganache", "chocolate-quente"]  # 'preparo' (assunto) e 'doces-de-colher' (subcategoria) saem


def test_alt_vem_do_seo_e_sem_ele_nao_ha_payload():
    c = dica_valida()  # sem texto_alt_imagem
    with pytest.raises(ContratoInvalido, match="IMG-08"):
        montar(c)
    with pytest.raises(ContratoInvalido, match="IMG-08"):
        montar(conteudo(texto_alt_imagem="   "))


def test_assunto_e_subcategoria_da_pauta_e_capa():
    with pytest.raises(ContratoInvalido, match="assunto"):
        montar(conteudo(assunto="negocios"))
    with pytest.raises(ContratoInvalido, match="subcategoria"):
        montar(conteudo(subcategoria="bolos-simples"))
    with pytest.raises(ContratoInvalido, match="sem capa"):
        montar(cover=None)
    with pytest.raises(ContratoInvalido, match="topic_slug"):
        montar(pauta={k: v for k, v in PAUTA.items() if k != "topic_slug"})
    with pytest.raises(ContratoInvalido):
        montar(pauta=PAUTA_RECEITA)  # pauta de receita (sem assunto)


def test_contrato_do_artigo_e_validado():
    with pytest.raises(ContratoInvalido):
        montar(conteudo(temas_relacionados=["só um"]))
    with pytest.raises(ContratoInvalido):
        montar(conteudo(titulo="abc"))
