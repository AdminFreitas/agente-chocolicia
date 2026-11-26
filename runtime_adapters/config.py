from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlparse

class ConfigurationError(RuntimeError):
    pass

ROOT_DIR = Path(__file__).resolve().parents[1]
PRODUCTION_HOSTS = {"chocolicia.site", "www.chocolicia.site"}


def _validate_site_url(base: str, environment: str) -> None:
    parsed = urlparse(base)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("SITE_BASE_URL deve ser uma origem válida, sem credenciais, query ou fragmento")
    if parsed.path not in ("", "/"):
        raise ConfigurationError("SITE_BASE_URL deve conter somente a origem, sem caminho")
    if environment == "production":
        if parsed.scheme != "https" or host != "www.chocolicia.site":
            raise ConfigurationError("production aceita somente https://www.chocolicia.site")
        return
    if host in PRODUCTION_HOSTS or host.endswith(".chocolicia.site"):
        raise ConfigurationError("SITE_BASE_URL de produção exige AGENT_ENV=production explícito")
    if parsed.scheme == "http":
        if environment != "test" or host not in {"localhost", "127.0.0.1"}:
            raise ConfigurationError("HTTP só é permitido para loopback com AGENT_ENV=test")
        return
    if parsed.scheme != "https":
        raise ConfigurationError("SITE_BASE_URL deve usar HTTPS, exceto loopback em teste")
    if environment != "preview" or not host.endswith(".vercel.app"):
        raise ConfigurationError("HTTPS remoto só é permitido para Preview .vercel.app com AGENT_ENV=preview")


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Variável obrigatória ausente: {name}")
    return value

def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name) or str(default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} deve ser inteiro") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} deve ser >= {minimum}")
    return value

@dataclass(frozen=True)
class Settings:
    enabled: bool
    environment: str
    database_url: str
    search_provider: str
    brave_api_key: str
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    llm_models: dict
    site_base_url: str
    site_token_draft: str
    site_token_publish: str
    site_phase: int
    site_contract: str
    contract_version: str
    site_tips_enabled: bool
    request_timeout: float
    llm_timeout: float
    max_searches: int
    max_pages: int

    @classmethod
    def from_env(cls, *, target: str = "preview") -> "Settings":
        if target not in {"preview", "production"}:
            raise ConfigurationError("target deve ser preview ou production")
        enabled = os.getenv("AGENT_ENABLED", "false").lower() == "true"
        env = (os.getenv("AGENT_ENV") or "development").strip().lower()
        if env not in {"development", "test", "preview", "production"}:
            raise ConfigurationError("AGENT_ENV inválido")
        provider = (os.getenv("LLM_PROVIDER") or "openai-compatible").strip().lower()
        if provider == "ollama":
            raise ConfigurationError("LLM_PROVIDER=ollama não é suportado")
        search = (os.getenv("SEARCH_PROVIDER") or "brave").strip().lower()
        phase = _int("AGENT_PHASE", 0, 0)
        if phase > 3:
            raise ConfigurationError("SITE_PHASE deve estar entre 0 e 3")
        # O endpoint oficial do agente é POST /api/recipes no contrato v1.
        # O contrato legado permanece disponível apenas para compatibilidade
        # explícita; nunca deve ser escolhido por omissão.
        contract = (os.getenv("SITE_CONTRACT") or "v1").strip().lower()
        if contract not in {"legacy", "v1"}:
            raise ConfigurationError("SITE_CONTRACT deve ser legacy ou v1")
        contract_version = (os.getenv("CONTRACT_VERSION") or "1").strip()
        if contract == "v1" and contract_version != "1":
            raise ConfigurationError("CONTRACT_VERSION deve ser 1 para SITE_CONTRACT=v1")
        base_name = "SITE_BASE_URL" if target == "production" else "SITE_BASE_URL_PREVIEW"
        # Ambientes são isolados: preview nunca herda a URL de produção.
        base = os.getenv(base_name, "").strip()
        if not base:
            alias = "CHOCOLICIA_SITE_URL" if target == "production" else "CHOCOLICIA_SITE_URL_PREVIEW"
            base = os.getenv(alias, "").strip()
        # Em testes locais, SITE_BASE_URL é o nome histórico aceito pelo
        # harness; fora de test não há fallback entre preview e produção.
        if not base and env == "test":
            base = os.getenv("SITE_BASE_URL", "").strip()
        if not base and env == "test":
            base = "http://127.0.0.1:3000"
        if base:
            _validate_site_url(base, env)
        models = {}
        for task in (
            "creation", "repair", "review", "seo", "extraction", "vision"
        ):
            model = os.getenv(f"LLM_MODEL_{task.upper()}", "").strip()
            family = os.getenv(f"LLM_FAMILY_{task.upper()}", "").strip()
            if model and family:
                models[task] = {"model": model, "family": family}
        # Brave sem chave fica indisponível e é ignorado pelo adaptador; a
        # ausência de busca não deve interromper uma execução de custo zero.
        llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        return cls(
            enabled=enabled, environment=env,
            database_url=(os.getenv("AGENT_DATABASE_URL") or os.getenv("DATABASE_URL_AGENTE", "")).strip(),
            search_provider=search,
            brave_api_key=os.getenv("BRAVE_SEARCH_API_KEY", "").strip(),
            llm_provider=provider,
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_base_url=llm_base_url,
            llm_models=models,
            site_base_url=base,
            site_token_draft=(
                os.getenv("SITE_TOKEN_DRAFT", "").strip()
                if target == "production"
                else (os.getenv("SITE_TOKEN_DRAFT_PREVIEW") or os.getenv("SITE_TOKEN_DRAFT", "")).strip()
            ),
            site_token_publish=os.getenv("SITE_TOKEN_PUBLISH", "").strip() if target == "production" else "",
            site_phase=phase,
            site_contract=contract,
            contract_version=contract_version,
            site_tips_enabled=os.getenv("SITE_TIPS_ENABLED", "false").lower() == "true",
            request_timeout=float(os.getenv("AGENT_REQUEST_TIMEOUT") or "30"),
            llm_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT") or "90"),
            max_searches=_int("SEARCH_MAX_QUERIES", 8),
            max_pages=_int("SEARCH_MAX_RESULTS", 6),
        )
