import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AGENT_ENABLED = env("AGENT_ENABLED", "false").lower() == "true"
AGENT_DICAS_ENABLED = env("AGENT_DICAS_ENABLED", "false").lower() == "true"
AGENT_PHASE = env("AGENT_PHASE", "0")
CONTRACT_VERSION = env("CONTRACT_VERSION", "1")
TARGET = env("TARGET", "preview")
DRY_RUN = env("DRY_RUN", "true").lower() == "true"
ASSUNTO = env("ASSUNTO", "automatico")
DATABASE_URL_AGENTE = env("DATABASE_URL_AGENTE")
SITE_BASE_URL = env("SITE_BASE_URL")
SITE_BASE_URL_PREVIEW = env("SITE_BASE_URL_PREVIEW")
SITE_TOKEN_DRAFT = env("SITE_TOKEN_DRAFT")
SITE_TOKEN_PUBLISH = env("SITE_TOKEN_PUBLISH")
SITE_TOKEN_DRAFT_PREVIEW = env("SITE_TOKEN_DRAFT_PREVIEW")
PESQUISA_PROVEDOR = env("PESQUISA_PROVEDOR", "mock")
# Preferência global de fallback. Só são usados provedores com adaptador,
# modelo aprovado na configuração da tarefa e credencial disponível.
FALLBACK_ORDER = env("FALLBACK_ORDER", "groq,gemini,openai,anthropic,openrouter,deepseek,grok,huggingface,mistral,cohere,together,kimi,ollama")
GEMINI_API_KEY = env("GEMINI_API_KEY")
GROQ_API_KEY = env("GROQ_API_KEY")
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
PIXABAY_API_KEY = env("PIXABAY_API_KEY")
PEXELS_API_KEY = env("PEXELS_API_KEY")
PESQUISA_API_KEY = env("PESQUISA_API_KEY")
OUTPUT_ARTIGOS = str(BASE_DIR / "output" / "artigos")
