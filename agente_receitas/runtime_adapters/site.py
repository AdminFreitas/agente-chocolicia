from __future__ import annotations
from agente_receitas.integration.cliente_site import ClienteSite
from .config import Settings, ConfigurationError

def build_site_client(settings: Settings, *, dry_run: bool, target: str = "preview"):
    if not settings.site_base_url:
        raise ConfigurationError("SITE_BASE_URL ausente")
    production = target == "production"
    if production and settings.environment != "production":
        raise ConfigurationError("target production exige AGENT_ENV=production")
    if production and dry_run:
        raise ConfigurationError("produção exige envio explícito; dry-run não é permitido")
    legacy = settings.site_contract == "legacy"
    if production and legacy and not settings.recipes_agent_token:
        raise ConfigurationError("Configure RECIPES_AGENT_TOKEN para publicar em produção")
    if production and not legacy and not settings.site_token_publish:
        raise ConfigurationError("Configure SITE_TOKEN_PUBLISH para a API de produção")
    # O alvo de produção nunca é inferido: deve ser explicitamente configurado.
    if not production and settings.environment == "production":
        raise ConfigurationError("AGENT_ENV=production exige target=production")
    return ClienteSite(
        settings.site_base_url,
        token_draft=settings.recipes_agent_token if legacy else settings.site_token_draft,
        token_publish=settings.recipes_agent_token if legacy else settings.site_token_publish,
        fase=settings.site_phase,
        contract_version=settings.contract_version,
        dry_run=dry_run,
        allow_local_http=settings.environment == "test",
        allow_production=production,
        articles_enabled=settings.site_articles_enabled,
        contract=settings.site_contract,
        upload_images=False if legacy else not dry_run,  # sem /api/uploads: capa vem de banco de imagens
    )
