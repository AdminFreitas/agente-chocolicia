from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from integration.cliente_site import ClienteSite, RespostaCriacao
from .config import Settings, ConfigurationError


class BloqueadorRedeSite:
    """Garantia estrutural de que nenhuma requisição externa ao site ou Neon ocorre em dry-run."""

    def __init__(
        self,
        *,
        contract: str = "v1",
        contract_version: str = "1",
        articles_enabled: bool = True,
        fase: int = 0,
    ):
        self.contract = contract
        self.contract_version = contract_version
        self.articles_enabled = articles_enabled
        self.fase = fase
        self.dry_run = True

    def criar_receita(
        self, payload, *, run_id: str = "", idempotency_key: str | None = None, **kwargs
    ) -> RespostaCriacao:
        from integration.contratos import ReceitaLegada, ReceitaV1
        modelo = ReceitaLegada if self.contract == "legacy" else ReceitaV1
        validado = payload if isinstance(payload, modelo) else modelo.model_validate(payload)
        corpo = validado.model_dump(mode="json", exclude_none=True)
        return RespostaCriacao("dry_run", payload=corpo)

    def criar_tip(
        self, payload, *, run_id: str = "", **kwargs
    ) -> RespostaCriacao:
        from integration.contratos import ArtigoV1
        validado = payload if isinstance(payload, ArtigoV1) else ArtigoV1.model_validate(payload)
        corpo = validado.model_dump(mode="json", exclude_none=True)
        return RespostaCriacao("dry_run", payload=corpo)

    criar_artigo = criar_tip

    def publicar_receita(self, slug: str):
        raise RuntimeError("Chamada de publicação externa indevida em dry-run")

    def _requisitar(self, *args, **kwargs):
        raise RuntimeError("Tentativa indevida de requisição HTTP externa ao site em dry-run")

    def __getattr__(self, name: str):
        def _bloqueado(*args, **kwargs):
            raise RuntimeError(f"Chamada externa indevida ao site em dry-run: {name}")
        return _bloqueado


def build_site_client(settings: Settings, *, dry_run: bool, target: str = "preview"):
    if dry_run:
        return BloqueadorRedeSite(
            contract=settings.site_contract,
            contract_version=settings.contract_version,
            articles_enabled=settings.site_tips_enabled,
            fase=settings.site_phase,
        )
    if target == "production" and not settings.site_token_publish:
        raise ConfigurationError("Configure SITE_TOKEN_PUBLISH para a API de produção")
    if not settings.site_base_url:
        raise ConfigurationError("SITE_BASE_URL ausente")
    production = target == "production"
    if production and settings.environment != "production":
        raise ConfigurationError("target production exige AGENT_ENV=production")
    if production and dry_run:
        raise ConfigurationError("produção exige envio explícito; dry-run não é permitido")
    if production and settings.site_contract != "v1":
        raise ConfigurationError(
            "SITE_CONTRACT=legacy só cria rascunho; publicação exige SITE_CONTRACT=v1"
        )
    # O alvo de produção nunca é inferido: deve ser explicitamente configurado.
    if not production and settings.environment == "production":
        raise ConfigurationError("AGENT_ENV=production exige target=production")
    return ClienteSite(
        settings.site_base_url,
        token_draft=settings.site_token_draft,
        token_publish=settings.site_token_publish,
        fase=settings.site_phase,
        contract_version=settings.contract_version,
        dry_run=dry_run,
        allow_local_http=settings.environment == "test",
        allow_production=production,
        articles_enabled=settings.site_tips_enabled,
        contract=settings.site_contract,
    )
