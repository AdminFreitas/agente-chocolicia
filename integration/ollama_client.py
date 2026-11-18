"""Cliente HTTP pequeno para inferência JSON estruturada via Ollama."""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Falha de comunicação ou resposta inválida do Ollama."""


def generate_json(prompt: str) -> tuple[dict, str]:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
    timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
    try:
        response = httpx.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.4},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
        content = result.get("message", {}).get("content", "")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("A resposta JSON do modelo precisa ser um objeto.")
        return parsed, str(result.get("model") or model)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.exception("Falha na inferência Ollama (modelo=%s, host=%s)", model, host)
        raise OllamaError(f"Falha na inferência ou parsing do Ollama: {exc}") from exc
