import copy

import pytest
from pydantic import ValidationError

from integration import contratos as C
from helpers_integracao import COVER_GERAR, COVER_STOCK, payload


def base():
    return payload().model_dump(mode="json", exclude_none=True)


def invalido(**mudancas):
    d = base(); d.update(mudancas)
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)


def test_schemas_em_contracts_estao_em_dia():
    assert C.desatualizados() == []
    s = C.gerar_schemas()
    assert set(s) == {"recipe.v1.schema.json", "article.v1.schema.json"} and "NÃO é a cópia canônica" in s["recipe.v1.schema.json"]["x-origem"]


def test_payload_valido_e_status_padrao_draft():
    d = base(); d.pop("status")
    assert C.validar_receita(d).status == "draft"
    assert C.CONTRACT_VERSION == "1"


@pytest.mark.parametrize("campo,valor", [
    ("title", "abc"), ("excerpt", "curto"), ("prepTimeMin", 0), ("servings", 501), ("restTimeMin", 10081),
    ("difficulty", "Impossível"), ("coverImageAlt", "curto"), ("aiModel", "x" * 121), ("status", "archived"),
    ("slug", "Slug Inválido"), ("subcategorySlug", "Com Espaço"), ("yieldLabel", "x" * 81), ("storageNotes", "x" * 3001),
    ("tips", ["a"] * 6), ("tags", [f"t{i}" for i in range(13)]), ("diet", ["sem-gluten"]), ("diet", ["vegana", "vegana"]),
    ("tags", ["sem-gluten"]), ("tags", ["Com Espaço"]), ("occasions", ["a", "a"]),
])
def test_limites_e_regras(campo, valor):
    invalido(**{campo: valor})


def test_passos_unidades_e_secoes():
    d = base(); d["steps"] = d["steps"][:3]
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)
    d = base(); d["ingredients"][0]["items"][0]["unit"] = "xícaras"
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)
    d = base(); d["ingredients"][0]["name"] = "x" * 101  # SITE: seção até 100
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)
    d = base(); d["ingredients"][0]["items"][0]["ingredientSlug"] = "Com Espaço"
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)
    for u in C.UNIDADES:
        d = base(); d["ingredients"][0]["items"][0]["unit"] = u
        C.ReceitaV1.model_validate(d)


def test_campos_extras_sao_proibidos():
    d = base(); d["dificuldade"] = "Fácil"
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)
    d = base(); d["generationMeta"]["extra"] = 1
    with pytest.raises(ValidationError):
        C.ReceitaV1.model_validate(d)


def test_cover_discriminado():
    for cover in (COVER_GERAR, COVER_STOCK):
        d = base(); d["cover"] = copy.deepcopy(cover); C.ReceitaV1.model_validate(d)
    ruins = [{"mode": "stock", **{k: v for k, v in COVER_STOCK.items() if k != "mode"}, "sourceImageUrl": "http://x/y.jpg"},
             {"mode": "stock", "provider": "pexels"}, {"mode": "generate"}, {"mode": "outro"}, {**COVER_GERAR, "imagePrompt": "x" * 2001},
             {**COVER_GERAR, "provider": "pexels"}]
    for cover in ruins:
        d = base(); d["cover"] = cover
        with pytest.raises(ValidationError):
            C.ReceitaV1.model_validate(d)


def test_cc0_pode_ter_autor_e_atribuicao_vazios():
    d = base(); d["cover"] = {**COVER_STOCK, "author": "", "attributionText": "", "license": "CC0"}
    assert C.ReceitaV1.model_validate(d).cover.author == ""


def test_generation_meta():
    d = base()["generationMeta"]
    for campo in ("run_id", "topic_slug", "prompt_version", "phase", "validators_version"):
        x = copy.deepcopy(d); x.pop(campo)
        with pytest.raises(ValidationError):
            C.GenerationMetaV1.model_validate(x)
    with pytest.raises(ValidationError):
        C.GenerationMetaV1.model_validate({**d, "phase": 4})
    with pytest.raises(ValidationError):
        C.GenerationMetaV1.model_validate({**d, "sources": [{"domain": "a", "url": "b", "date": "06/11/2026"}]})


def artigo(**ch):
    d = {"type": "tip", "title": "Ganache talhou? Como recuperar", "excerpt": "Como recuperar uma ganache que talhou, em poucos passos simples.",
         "tipTopic": "preparo", "bodyMd": "Resposta direta...", "cover": COVER_GERAR, "coverImageAlt": "Ganache cremosa na tigela",
         "aiModel": "p/m", "generationMeta": base()["generationMeta"]}
    d.update(ch)
    return d


def test_artigo_regras_por_tipo():
    C.ArtigoV1.model_validate(artigo())
    C.ArtigoV1.model_validate(artigo(subcategorySlug="doces-de-colher"))  # subcategoria é opcional em dica
    C.ArtigoV1.model_validate(artigo(type="technique", tipTopic=None, subcategorySlug="trufas-e-bombons",
                                     sources=[{"name": "Fonte", "title": "Título", "url": "https://x.test"}], relatedTopics=["a", "b"]))
    for ruim in (artigo(tipTopic=None), artigo(type="feature", subcategorySlug="x"), artigo(type="technique", tipTopic=None),
                 artigo(type="technique", tipTopic=None, subcategorySlug="x", sources=[{"name": "F", "title": "T", "url": "u"}], relatedTopics=["so um"]),
                 artigo(type="technique", subcategorySlug="x", sources=[{"name": "F", "title": "T", "url": "u"}]),  # tipTopic em técnica
                 artigo(type="noticia"), artigo(relatedTopics=["a"] * 7)):
        with pytest.raises(ValidationError):
            C.ArtigoV1.model_validate(ruim)
