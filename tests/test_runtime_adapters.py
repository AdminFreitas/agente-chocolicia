import os
import pytest
import runtime_adapters.config as runtime_config
from runtime_adapters.config import Settings, ConfigurationError


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    monkeypatch.setattr(runtime_config, "load_dotenv", lambda *args, **kwargs: None)

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_ENABLED", raising=False)
    assert Settings.from_env().enabled is False

def test_enabled_requires_model_and_family(monkeypatch):
    for name in (
        "OLLAMA_MODEL",
        "LLM_MODEL_CREATION", "LLM_MODEL_REPAIR", "LLM_MODEL_REVIEW",
        "LLM_MODEL_SEO", "LLM_MODEL_EXTRACTION", "LLM_MODEL_VISION",
        "LLM_FAMILY_CREATION", "LLM_FAMILY_REPAIR", "LLM_FAMILY_REVIEW",
        "LLM_FAMILY_SEO", "LLM_FAMILY_EXTRACTION", "LLM_FAMILY_VISION",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://x")
    with pytest.raises(ConfigurationError, match="LLM_MODEL_CREATION"):
        Settings.from_env()


def test_enabled_requires_specific_vision_model(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("OLLAMA_MODEL", "text-model")
    monkeypatch.delenv("LLM_MODEL_VISION", raising=False)
    with pytest.raises(ConfigurationError, match="LLM_MODEL_VISION"):
        Settings.from_env()

def test_family_must_be_explicit(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "true")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("LLM_MODEL_CREATION", "example-model")
    with pytest.raises(ConfigurationError, match="LLM_FAMILY_CREATION"):
        Settings.from_env()


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


def test_credencial_publish_nao_e_usada_como_token_draft(monkeypatch):
    monkeypatch.setenv("RECIPES_AGENT_TOKEN_PUBLISH", "publish-only")
    monkeypatch.delenv("SITE_TOKEN_DRAFT", raising=False)
    monkeypatch.delenv("RECIPES_AGENT_TOKEN_DRAFT", raising=False)
    monkeypatch.delenv("RECIPES_AGENT_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.site_token_publish == "publish-only"
    assert settings.site_token_draft == ""


@pytest.mark.parametrize("base", [
    "https://www.chocolicia.site",
    "https://chocolicia.site",
    "https://example.com/receitas",
])
def test_site_url_de_producao_ou_com_caminho_e_bloqueada(monkeypatch, base):
    monkeypatch.setenv("AGENT_ENV", "preview")
    monkeypatch.setenv("SITE_BASE_URL", base)
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_dotenv_da_raiz_e_processo_tem_precedencia(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENT_ENV=test\nSITE_BASE_URL=http://127.0.0.1:3000\nOLLAMA_MODEL=modelo-do-arquivo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_config, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(runtime_config, "load_dotenv", __import__("dotenv").load_dotenv)
    monkeypatch.delenv("AGENT_ENV", raising=False)
    monkeypatch.delenv("SITE_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "modelo-do-processo")
    settings = Settings.from_env()
    assert settings.environment == "test"
    assert settings.site_base_url == "http://127.0.0.1:3000"
    assert settings.llm_models["creation"]["model"] == "modelo-do-processo"


def test_composicao_entrega_dependencias_reais_de_receita(monkeypatch):
    from types import SimpleNamespace
    import runtime_adapters.cli_contract as cli_contract
    from pipeline.gerar_receitas import DependenciasReceita

    generator = object()
    runtime = SimpleNamespace(
        settings=SimpleNamespace(site_phase=0),
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
