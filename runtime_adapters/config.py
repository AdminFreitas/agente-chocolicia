from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlparse
from dotenv import load_dotenv

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
    site_articles_enabled: bool
    request_timeout: float
    llm_timeout: float
    max_searches: int
    max_pages: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT_DIR / ".env", override=False)
        enabled = os.getenv("AGENT_ENABLED", "false").lower() == "true"
        env = (os.getenv("AGENT_ENV") or "development").strip().lower()
        if env not in {"development", "test", "preview", "production"}:
            raise ConfigurationError("AGENT_ENV inválido")
        configured_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        # Ollama local é a rota padrão quando o endpoint local está configurado.
        # O provedor compatível continua disponível para ambientes explicitamente
        # configurados, mas nunca é usado como fallback para um serviço pago.
        provider = configured_provider or "ollama"
        search = (os.getenv("SEARCH_PROVIDER") or "brave").strip().lower()
        phase = _int("AGENT_PHASE", 0, 0)
        if phase > 3:
            raise ConfigurationError("SITE_PHASE deve estar entre 0 e 3")
        contract = (os.getenv("SITE_CONTRACT") or "legacy").strip().lower()
        if contract != "legacy":
            raise ConfigurationError("SITE_CONTRACT deve ser legacy; o destino atual não aceita contrato v1")
        contract_version = "1"
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
            required_tasks = {"creation", "review", "seo", "extraction", "vision"}
            if provider == "ollama" and not model and task != "vision":
                model = os.getenv("OLLAMA_MODEL", "").strip()
            if provider == "ollama" and not family:
                family = "ollama-local"
            if enabled and task in required_tasks and (not model or not family):
                raise ConfigurationError(
                    f"Defina LLM_MODEL_{task.upper()} e LLM_FAMILY_{task.upper()}; "
                    "famílias não são inferidas automaticamente."
                )
            if model and family:
                models[task] = {"model": model, "family": family}
        if enabled and search == "brave" and not os.getenv("BRAVE_SEARCH_API_KEY"):
            raise ConfigurationError("BRAVE_SEARCH_API_KEY ausente")
        if enabled and provider == "openai-compatible" and not os.getenv("LLM_API_KEY"):
            raise ConfigurationError("LLM_API_KEY ausente")
        ollama_base = (
            os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_URL")
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        if ollama_base.startswith("http://localhost:"):
            ollama_base = ollama_base.replace("http://localhost:", "http://127.0.0.1:", 1)
        if provider == "ollama" and ollama_base.endswith("/v1"):
            llm_base_url = ollama_base
        elif provider == "ollama":
            llm_base_url = ollama_base + "/v1"
        else:
            llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        return cls(
            enabled=enabled, environment=env,
            database_url=(os.getenv("AGENT_DATABASE_URL") or os.getenv("DATABASE_URL_AGENTE", "")).strip(),
            search_provider=search,
            brave_api_key=os.getenv("BRAVE_SEARCH_API_KEY", "").strip(),
            llm_provider=provider,
            llm_api_key=os.getenv("LLM_API_KEY", "").strip() or ("ollama-local" if provider == "ollama" else ""),
            llm_base_url=llm_base_url,
            llm_models=models,
            site_base_url=base,
            site_token_draft=os.getenv("RECIPES_AGENT_TOKEN", "").strip(),
            site_token_publish="",
            site_phase=phase,
            site_contract=contract,
            contract_version=contract_version,
            site_articles_enabled=os.getenv("SITE_ARTICLES_ENABLED", "false").lower() == "true",
            request_timeout=float(os.getenv("AGENT_REQUEST_TIMEOUT") or "30"),
            llm_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT") or ("180" if provider == "ollama" else "90")),
            max_searches=_int("SEARCH_MAX_QUERIES", 8),
            max_pages=_int("SEARCH_MAX_RESULTS", 6),
        )
