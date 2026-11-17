from __future__ import annotations
from integration.cliente_site import ClienteSite
from .config import Settings, ConfigurationError

def build_site_client(settings: Settings, *, dry_run: bool):
    if not settings.site_base_url:
        raise ConfigurationError("SITE_BASE_URL ausente")
    if settings.environment == "production" and not settings.site_token_publish and not dry_run:
        raise ConfigurationError("SITE_TOKEN_PUBLISH ausente para ambiente production")
    # O alvo de produção nunca é inferido: deve ser explicitamente configurado.
    if settings.environment != "production" and settings.site_token_publish:
        raise ConfigurationError("Não configure token publish fora do ambiente production")
    return ClienteSite(
        settings.site_base_url,
        token_draft=settings.site_token_draft,
        token_publish=settings.site_token_publish,
        fase=settings.site_phase,
        dry_run=dry_run,
    )
