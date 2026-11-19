from __future__ import annotations
import os
from dataclasses import dataclass
from .config import Settings, ConfigurationError
from .search import BraveSearch
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
    settings = Settings.from_env(target=target)
    is_ci = os.environ.get("CI", "false").lower() == "true"
    if is_ci and not settings.enabled:
        raise ConfigurationError("AGENT_ENABLED=false: execução bloqueada em CI")
    if target not in {"preview", "production"}:
        raise ConfigurationError(f"target não suportado: {target}")
    if not settings.site_base_url:
        raise ConfigurationError("SITE_BASE_URL_PREVIEW ausente")
    if target == "production":
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
    if settings.search_provider != "brave":
        raise ConfigurationError(
            f"SEARCH_PROVIDER não suportado: {settings.search_provider}"
        )
    from services.llm_service import validar_configuracao_modelos

    validar_configuracao_modelos(["criacao", "reparo", "revisao", "extracao", "seo"])
    if not dry_run and not settings.site_token_draft:
        raise ConfigurationError("SITE_TOKEN_DRAFT ausente")
    if not dry_run and not settings.database_url:
        raise ConfigurationError("DATABASE_URL_AGENTE ausente para bloqueio de duplicatas")
    store = None
    if settings.database_url and not dry_run:
        store = PostgresStore(settings.database_url)
        store.migrate()
    elif settings.database_url:
        store = PostgresStore(settings.database_url)
    catalog = SiteCatalog(
        settings.site_base_url, settings.site_token_draft,
        timeout=settings.request_timeout,
    )
    search = BraveSearch(
        settings.brave_api_key, timeout=settings.request_timeout
    )
    from services.llm_cliente import gerar_padrao

    def generate(task: str, prompt: str, *, familia_excluida: str | None = None):
        task_names = {
            "creation": "criacao",
            "repair": "reparo",
            "review": "revisao",
            "extraction": "extracao",
        }
        return gerar_padrao(
            task_names.get(task, task),
            prompt,
            familia_excluida=familia_excluida,
        )

    client = build_site_client(settings, dry_run=dry_run, target=target)
    return Runtime(settings, [search], generate, client, catalog, store, None)
