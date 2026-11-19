from types import SimpleNamespace

from helpers_criacao import ficha_aprovada
from helpers_integracao import COVER_STOCK, PAUTA, conteudo_editor
from integration.contratos import ReceitaLegada
from integration.cliente_site import RespostaCriacao
from pipeline import gerar_receitas as pipeline


def test_pipeline_usa_adaptador_aceito_pelo_site_atual(monkeypatch):
    conteudo = conteudo_editor()
    ficha = ficha_aprovada()
    payloads = []
    client = SimpleNamespace(
        contract="legacy",
        criar_receita=lambda payload, **kwargs: (
            payloads.append(payload)
            or RespostaCriacao("dry_run", payload=payload.model_dump(mode="json"))
        ),
    )
    deps = SimpleNamespace(
        pesquisar=lambda pauta: {
            "status": "aprovada_para_criacao",
            "ficha_consolidada": ficha,
        },
        gerar=object(),
        cliente=client,
        catalogo=object(),
        selector=object(),
        usadas=object(),
        visao=object(),
        validador=None,
        tags_existentes=[],
        baixar=None,
    )
    criacao = SimpleNamespace(
        status="aprovado",
        conteudo=conteudo,
        modelo={"familia": "ollama-local"},
        prompt_version="receita@1",
        rejection_code=None,
    )
    monkeypatch.setattr(pipeline.editor, "criar_receita", lambda *a, **k: criacao)
    monkeypatch.setattr(pipeline.revisor, "revisar_conteudo", lambda *a, **k: object())
    monkeypatch.setattr(pipeline.revisor, "decisao_final", lambda *a, **k: True)
    monkeypatch.setattr(
        pipeline.seo, "ajustar_seo",
        lambda **k: SimpleNamespace(aplicado=True, conteudo=conteudo),
    )
    monkeypatch.setattr(
        pipeline, "escolher_capa",
        lambda *a, **k: SimpleNamespace(cover=COVER_STOCK, meta=None),
    )

    resultado = pipeline.gerar_receita(
        deps,
        {
            **PAUTA,
            "subcategoria": None,
            "categoria_legada": "Brigadeiros e docinhos",
        },
        fase=0,
        run_id="pipeline-test",
    )

    assert resultado.estado == "generated"
    assert isinstance(payloads[0], ReceitaLegada)
    assert payloads[0].status == "draft"
    assert payloads[0].category == "Brigadeiros e docinhos"
