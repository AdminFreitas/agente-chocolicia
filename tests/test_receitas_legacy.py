"""Testes offline do modo legacy de receitas (sem rede, LLM, banco ou GitHub)."""
import json

import httpx
import pytest

from agente_receitas.integration.cliente_site import ClienteSite
from agente_receitas.integration.contratos import ReceitaLegada
from agente_receitas.runtime_adapters.catalog import SiteCatalogLegado
from agente_receitas.runtime_adapters.config import ConfigurationError, Settings

SITE = "https://www.chocolicia.site"
TOKEN = "token-de-teste"


def _env(monkeypatch, **extra):
    base = {
        "AGENT_ENV": "production", "SITE_BASE_URL": SITE, "AGENT_PHASE": "1",
        "SITE_CONTRACT": "legacy", "RECIPES_AGENT_TOKEN": TOKEN,
    }
    base.update(extra)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def _receita(status="published"):
    return ReceitaLegada.model_validate({
        "title": "Brigadeiro gourmet de chocolate meio amargo",
        "excerpt": "Brigadeiro cremoso com ponto perfeito de enrolar.",
        "category": "Brigadeiros e docinhos",
        "coverImageUrl": "https://images.pexels.com/photos/1/brigadeiro.jpg",
        "coverImageAlt": "Brigadeiros gourmet enrolados em chocolate granulado",
        "ingredients": [{"name": "Massa", "items": [
            {"name": "Leite condensado", "quantity": "1", "unit": "lata"}]}],
        "steps": [{"instruction": "Misture tudo na panela."}, {"instruction": "Cozinhe até soltar do fundo."}],
        "prepTimeMin": 10, "cookTimeMin": 15, "servings": 20, "difficulty": "Fácil",
        "status": status,
    })


def test_legacy_precisa_ser_explicito(monkeypatch):
    _env(monkeypatch)
    assert Settings.from_env(target="production").site_contract == "legacy"
    monkeypatch.delenv("SITE_CONTRACT")
    assert Settings.from_env(target="production").site_contract == "v1"
    monkeypatch.setenv("SITE_CONTRACT", "qualquer")
    with pytest.raises(ConfigurationError):
        Settings.from_env(target="production")


def test_token_do_agente_so_em_producao(monkeypatch):
    _env(monkeypatch)
    assert Settings.from_env(target="production").recipes_agent_token == TOKEN
    monkeypatch.setenv("SITE_BASE_URL_PREVIEW", "https://x.vercel.app")
    monkeypatch.setenv("AGENT_ENV", "preview")
    assert Settings.from_env(target="preview").recipes_agent_token == ""


def test_catalogo_legacy_nao_usa_rede():
    cat = SiteCatalogLegado(SITE, TOKEN)
    assert cat.disponivel and cat.ingredients() == [] and cat.coverage() == {}
    assert cat.existe("qualquer", "tema") is False
    assert cat.resolver("Leite condensado")["needs_label_check"] is True
    assert cat.resolver("  ") is None
    assert cat.selecionar_categoria_legada()["category_name"]


def test_post_publicado_usa_bearer_e_corpo_do_contrato_real():
    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        corpo = json.loads(request.content)
        return httpx.Response(201, json={"id": "abc", "slug": "brigadeiro-gourmet", "status": corpo["status"]})

    cliente = ClienteSite(
        SITE, token_draft=TOKEN, token_publish=TOKEN, fase=1, contract="legacy",
        allow_production=True, cliente=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    resp = cliente.criar_receita(_receita(), run_id="r1", idempotency_key="brigadeiro")
    assert (resp.status, resp.slug) == ("published", "brigadeiro-gourmet")
    assert len(vistos) == 1
    req = vistos[0]
    assert req.method == "POST" and str(req.url) == SITE + "/api/recipes"
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    corpo = json.loads(req.content)
    assert corpo["status"] == "published"
    assert set(corpo) <= {
        "title", "excerpt", "category", "categorySlug", "subcategorySlug", "coverImageUrl",
        "coverImageAlt", "ingredients", "steps", "prepTimeMin", "cookTimeMin", "servings",
        "difficulty", "status",
    }


def test_legacy_sem_token_nao_publica():
    cliente = ClienteSite(SITE, fase=1, contract="legacy", allow_production=True,
                          cliente=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(Exception):
        cliente.criar_receita(_receita(), run_id="r1")


def test_resposta_sem_status_confirmado_nao_conta_como_publicada():
    def handler(request):
        return httpx.Response(201, json={"id": "abc", "slug": "x-y-z", "status": "draft"})

    cliente = ClienteSite(SITE, token_draft=TOKEN, token_publish=TOKEN, fase=1, contract="legacy",
                          allow_production=True,
                          cliente=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Exception):
        cliente.criar_receita(_receita(), run_id="r1")
