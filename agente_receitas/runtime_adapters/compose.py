from __future__ import annotations
import os
from dataclasses import dataclass
from .config import Settings, ConfigurationError
from .search import BraveSearch, TavilySearch
from .site import build_site_client
from .catalog import SiteCatalog, SiteCatalogLegado
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
        if settings.site_contract != "legacy":
            raise ConfigurationError(
                "produção só é liberada no modo legacy explícito (SITE_CONTRACT=legacy): "
                "o contrato v1 depende de rotas que o site ainda não implantou"
            )
        if not settings.recipes_agent_token:
            raise ConfigurationError("RECIPES_AGENT_TOKEN ausente para publicar em produção")
    elif settings.environment == "production":
        raise ConfigurationError("AGENT_ENV=production exige target=production")
    if settings.search_provider not in {"brave", "tavily"}:
        raise ConfigurationError(
            f"SEARCH_PROVIDER não suportado: {settings.search_provider}"
        )
    from agente_receitas.services.llm_service import validar_configuracao_modelos

    validar_configuracao_modelos(["criacao", "reparo", "revisao", "extracao", "seo"])
    if not dry_run and settings.site_contract != "legacy" and not settings.site_token_draft:
        raise ConfigurationError("SITE_TOKEN_DRAFT ausente")
    # A persistência do agente é opcional no modo legacy: sem banco, o site
    # continua protegendo slugs duplicados na própria API. Quando configurado,
    # o PostgresStore mantém histórico, reservas de pauta e uso de imagens.
    store = None
    if settings.database_url and not dry_run:
        store = PostgresStore(settings.database_url)
        store.migrate()
    elif settings.database_url:
        store = PostgresStore(settings.database_url)
    if settings.site_contract == "legacy":
        # O site atual não expõe taxonomia, catálogo, cobertura nem lookup.
        catalog = SiteCatalogLegado(
            settings.site_base_url, settings.recipes_agent_token,
            timeout=settings.request_timeout,
        )
    else:
        catalog = SiteCatalog(
            settings.site_base_url, settings.site_token_draft,
            timeout=settings.request_timeout,
        )
    if settings.search_provider == "tavily":
        search = TavilySearch(settings.tavily_api_key, timeout=settings.request_timeout)
    else:
        search = BraveSearch(settings.brave_api_key, timeout=settings.request_timeout)
    from agente_receitas.services.llm_cliente import gerar_padrao

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
