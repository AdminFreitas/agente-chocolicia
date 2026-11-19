import os
import pytest
import runtime_adapters.config as runtime_config
from runtime_adapters.config import Settings, ConfigurationError


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_ENABLED", raising=False)
    assert Settings.from_env().enabled is False

def test_enabled_requires_search_credential_not_unapproved_llm_environment(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    settings = Settings.from_env()
    assert settings.enabled is True
    assert settings.site_contract == "v1"


def test_site_local_requer_test_explicito_e_origem_loopback(monkeypatch):
    monkeypatch.setenv("AGENT_ENV", "test")
    monkeypatch.setenv("SITE_BASE_URL", "http://127.0.0.1:3000")
    assert Settings.from_env().site_base_url == "http://127.0.0.1:3000"

    monkeypatch.setenv("SITE_BASE_URL", "http://example.test")
    with pytest.raises(ConfigurationError, match="loopback"):
        Settings.from_env()


def test_ollama_default_usa_loopback_e_timeout_local(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    settings = Settings.from_env()
    assert settings.llm_provider == "ollama"
    assert settings.llm_base_url == "http://127.0.0.1:11434/v1"
    assert settings.llm_timeout == 180


def test_token_publish_nao_e_lido_no_contrato_legado(monkeypatch):
    monkeypatch.setenv("RECIPES_AGENT_TOKEN_PUBLISH", "publish-only")
    monkeypatch.delenv("SITE_TOKEN_PUBLISH", raising=False)
    monkeypatch.delenv("SITE_TOKEN_DRAFT", raising=False)
    monkeypatch.delenv("SITE_TOKEN_DRAFT_PREVIEW", raising=False)
    monkeypatch.delenv("RECIPES_AGENT_TOKEN_DRAFT", raising=False)
    monkeypatch.delenv("RECIPES_AGENT_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.site_token_publish == ""
    assert settings.site_token_draft == ""


def test_token_legado_nao_e_usado_pelo_cliente_v1(monkeypatch):
    monkeypatch.setenv("RECIPES_AGENT_TOKEN", "site-agent-token")
    monkeypatch.delenv("SITE_TOKEN_DRAFT", raising=False)
    monkeypatch.delenv("SITE_TOKEN_DRAFT_PREVIEW", raising=False)
    monkeypatch.delenv("RECIPES_AGENT_TOKEN_DRAFT", raising=False)
    settings = Settings.from_env()
    assert settings.site_token_draft == ""
    assert settings.site_token_publish == ""
    assert settings.site_contract == "v1"


def test_cliente_production_exige_token_publish(monkeypatch):
    from runtime_adapters.site import build_site_client

    monkeypatch.setenv("AGENT_ENV", "production")
    monkeypatch.setenv("SITE_BASE_URL", "https://www.chocolicia.site")
    settings = Settings.from_env()
    with pytest.raises(ConfigurationError, match="SITE_TOKEN_PUBLISH"):
        build_site_client(settings, dry_run=False, target="production")


def test_categoria_legada_nao_consulta_taxonomia_nao_disponivel(monkeypatch):
    from runtime_adapters.catalog import SiteCatalog

    def falha_rede(*args, **kwargs):
        raise AssertionError("o contrato atual não disponibiliza taxonomia")

    monkeypatch.setattr(SiteCatalog, "taxonomy", falha_rede)
    categoria = SiteCatalog("https://site.test", "").selecionar_categoria_legada()
    assert categoria["category_name"] in {
        "Bolos", "Brigadeiros e docinhos", "Tortas", "Sobremesas",
        "Chocolates", "Festas e buffet", "Datas especiais",
    }


@pytest.mark.parametrize("base", [
    "https://www.chocolicia.site",
    "https://chocolicia.site",
    "https://example.com/receitas",
])
def test_site_url_de_producao_ou_com_caminho_e_bloqueada(monkeypatch, base):
    monkeypatch.setenv("AGENT_ENV", "preview")
    monkeypatch.setenv("SITE_BASE_URL_PREVIEW", base)
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_settings_nao_le_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENT_ENV=test\nSITE_BASE_URL=http://127.0.0.1:3000\nOLLAMA_MODEL=modelo-do-arquivo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "ROOT_DIR", tmp_path)
    monkeypatch.delenv("AGENT_ENV", raising=False)
    monkeypatch.delenv("SITE_BASE_URL", raising=False)
    monkeypatch.delenv("SITE_BASE_URL_PREVIEW", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    settings = Settings.from_env()
    assert settings.environment == "development"
    assert settings.site_base_url == ""
    assert settings.llm_models == {}


def test_composicao_entrega_dependencias_reais_de_receita(monkeypatch):
    from types import SimpleNamespace
    import runtime_adapters.cli_contract as cli_contract
    from pipeline.gerar_receitas import DependenciasReceita

    generator = object()
    runtime = SimpleNamespace(
        settings=SimpleNamespace(site_phase=0, request_timeout=30, site_articles_enabled=True),
        search_providers=[],
        generate=generator,
        site_client=object(),
        catalog=object(),
        store=None,
    )
    monkeypatch.setattr(cli_contract, "build_runtime", lambda **kwargs: runtime)
    services = cli_contract.build_services()
    deps = services["dependencias_receita"]
    assert isinstance(deps, DependenciasReceita)
    assert deps.gerar is generator
    assert deps.cliente is runtime.site_client
    assert deps.catalogo is runtime.catalog
    assert callable(deps.pesquisar)
    assert deps.usadas is not None


def test_cli_default_dry_run_e_opcao_legada_rejeitada(monkeypatch):
    from rodar_agente import construir_parser

    monkeypatch.delenv("DRY_RUN", raising=False)
    parser = construir_parser()
    assert parser.parse_args(["--receita"]).dry_run is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--receita", "--enviar"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--receita", "--target", "producao"])


def test_cli_dry_run_nao_pode_ser_desabilitado_por_argumento(monkeypatch):
    from rodar_agente import construir_parser

    monkeypatch.setenv("DRY_RUN", "false")
    parser = construir_parser()
    assert parser.parse_args(["--receita"]).dry_run is False
    with pytest.raises(SystemExit):
        parser.parse_args(["--receita", "--publicar-slug", "brigadeiro-cremoso"])
