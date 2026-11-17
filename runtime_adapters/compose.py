from __future__ import annotations
from dataclasses import dataclass, replace
from .config import Settings, ConfigurationError
from .search import BraveSearch
from .llm import OpenAICompatibleGenerator
from .site import build_site_client
from .catalog import SiteCatalog
from .persistence import PostgresStore

@dataclass
class Runtime:
    settings: Settings
    search_providers: list
    generate: object
    site_client: object
    catalog: object
    store: object


def build_runtime(
    *, dry_run: bool = True, fase: int | None = None, contrato: str = "v1",
    target: str = "preview",
) -> Runtime:
    settings = Settings.from_env()
    if not settings.enabled:
        raise ConfigurationError("AGENT_ENABLED=false: execução bloqueada")
    if target not in {"preview", "producao"}:
        raise ConfigurationError(f"target não suportado: {target}")
    if target == "producao" and settings.environment != "production":
        raise ConfigurationError(
            "--target producao exige AGENT_ENV=production"
        )
    if target == "preview" and settings.environment == "production":
        raise ConfigurationError(
            "AGENT_ENV=production exige --target producao"
        )
    if contrato != "v1":
        raise ConfigurationError(
            "somente v1 está implementado; site-atual não foi confirmado"
        )
    if fase is not None:
        settings = replace(settings, site_phase=fase, site_contract=contrato)
    if settings.search_provider != "brave":
        raise ConfigurationError(
            f"SEARCH_PROVIDER não suportado: {settings.search_provider}"
        )
    if settings.llm_provider != "openai-compatible":
        raise ConfigurationError(
            f"LLM_PROVIDER não suportado: {settings.llm_provider}"
        )
    if not settings.database_url:
        raise ConfigurationError("AGENT_DATABASE_URL ausente")
    if not settings.site_token_draft and not dry_run:
        raise ConfigurationError("SITE_TOKEN_DRAFT ausente")
    store = PostgresStore(settings.database_url)
    store.migrate()
    catalog = SiteCatalog(
        settings.site_base_url, settings.site_token_draft,
        timeout=settings.request_timeout,
    )
    search = BraveSearch(
        settings.brave_api_key, timeout=settings.request_timeout
    )
    generate = OpenAICompatibleGenerator(
        settings.llm_api_key, settings.llm_base_url, settings.llm_models,
        timeout=settings.request_timeout,
    )
    client = build_site_client(settings, dry_run=dry_run)
    return Runtime(settings, [search], generate, client, catalog, store)
