from __future__ import annotations
import os
from dataclasses import dataclass
from .config import Settings, ConfigurationError
from .search import BraveSearch
from .llm import OpenAICompatibleGenerator, OpenAICompatibleVisionVerifier
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
    store: object | None
    vision: object | None = None


def build_runtime(*, dry_run: bool = True, target: str = "preview") -> Runtime:
    settings = Settings.from_env()
    is_ci = os.environ.get("CI", "false").lower() == "true"
    if is_ci and not settings.enabled:
        raise ConfigurationError("AGENT_ENABLED=false: execução bloqueada em CI")
    if target not in {"preview", "production"}:
        raise ConfigurationError(f"target não suportado: {target}")
    if target == "production":
        if settings.site_contract == "legacy":
            raise ConfigurationError(
                "publicação bloqueada: o endpoint atual só permite criação como draft"
            )
        if settings.environment != "production":
            raise ConfigurationError("target production exige AGENT_ENV=production")
        if settings.site_base_url != "https://www.chocolicia.site":
            raise ConfigurationError("produção aceita somente https://www.chocolicia.site")
        if settings.site_phase < 1:
            raise ConfigurationError("publicação exige SITE_PHASE >= 1")
        if dry_run:
            raise ConfigurationError("production exige DRY_RUN=false; use preview para dry-run")
        if os.environ.get("AGENT_PUBLISHING_ENABLED", "false").strip().lower() != "true":
            raise ConfigurationError("AGENT_PUBLISHING_ENABLED não está habilitado")
        raise ConfigurationError(
            "produção bloqueada: tetos de custo e sua aplicação no runtime ainda não estão configurados"
        )
    elif settings.environment == "production":
        raise ConfigurationError("AGENT_ENV=production exige target=production")
    if settings.site_contract != "legacy":
        raise ConfigurationError("o destino atual exige SITE_CONTRACT=legacy")
    if settings.search_provider != "brave":
        raise ConfigurationError(
            f"SEARCH_PROVIDER não suportado: {settings.search_provider}"
        )
    if settings.llm_provider not in {"openai-compatible", "ollama"}:
        raise ConfigurationError(
            f"LLM_PROVIDER não suportado: {settings.llm_provider}"
        )
    if not dry_run and target != "production" and not settings.site_token_draft:
        raise ConfigurationError("RECIPES_AGENT_TOKEN ausente")
    if not dry_run and not settings.database_url:
        raise ConfigurationError("DATABASE_URL_AGENTE ausente para bloqueio de duplicatas")
    store = None
    if settings.database_url:
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
        timeout=settings.llm_timeout, provider=settings.llm_provider,
    )
    vision_config = settings.llm_models.get("vision")
    vision = OpenAICompatibleVisionVerifier(
        settings.llm_api_key,
        settings.llm_base_url,
        vision_config["model"],
        timeout=settings.llm_timeout,
        provider=settings.llm_provider,
    ) if vision_config else None
    client = build_site_client(settings, dry_run=dry_run, target=target)
    return Runtime(settings, [search], generate, client, catalog, store, vision)
