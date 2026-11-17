from __future__ import annotations
import os
from dataclasses import dataclass
from urllib.parse import urlparse

class ConfigurationError(RuntimeError):
    pass

def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Variável obrigatória ausente: {name}")
    return value

def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
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
    request_timeout: float
    max_searches: int
    max_pages: int

    @classmethod
    def from_env(cls) -> "Settings":
        enabled = os.getenv("AGENT_ENABLED", "false").lower() == "true"
        env = os.getenv("AGENT_ENV", "development").lower()
        if env not in {"development", "test", "preview", "production"}:
            raise ConfigurationError("AGENT_ENV inválido")
        provider = os.getenv("LLM_PROVIDER", "openai-compatible").lower()
        search = os.getenv("SEARCH_PROVIDER", "brave").lower()
        phase = _int("SITE_PHASE", 0, 0)
        if phase > 3:
            raise ConfigurationError("SITE_PHASE deve estar entre 0 e 3")
        base = os.getenv("SITE_BASE_URL", "").strip()
        if base:
            p = urlparse(base)
            if p.scheme != "https" and env != "development":
                raise ConfigurationError("SITE_BASE_URL deve usar HTTPS fora do desenvolvimento")
        models = {}
        for task in (
            "creation", "repair", "review", "seo", "extraction", "vision"
        ):
            model = os.getenv(f"LLM_MODEL_{task.upper()}", "").strip()
            family = os.getenv(f"LLM_FAMILY_{task.upper()}", "").strip()
            required_tasks = {"creation", "review", "seo", "extraction"}
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
        return cls(
            enabled=enabled, environment=env,
            database_url=os.getenv("AGENT_DATABASE_URL", "").strip(),
            search_provider=search,
            brave_api_key=os.getenv("BRAVE_SEARCH_API_KEY", "").strip(),
            llm_provider=provider,
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_models=models,
            site_base_url=base,
            site_token_draft=os.getenv("SITE_TOKEN_DRAFT", "").strip(),
            site_token_publish=os.getenv("SITE_TOKEN_PUBLISH", "").strip(),
            site_phase=phase,
            site_contract=os.getenv("SITE_CONTRACT", "v1").strip(),
            request_timeout=float(os.getenv("AGENT_REQUEST_TIMEOUT", "30")),
            max_searches=_int("SEARCH_MAX_QUERIES", 8),
            max_pages=_int("SEARCH_MAX_RESULTS", 6),
        )
