"""Adaptador único de inferência local para Ollama, compartilhado por receitas e dicas."""
from __future__ import annotations

import os
import httpx


def gerar_texto(prompt: str, modelo: str | None = None) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")).strip().rstrip("/")
    modelo = (modelo or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")).strip()
    timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
    if not base_url:
        raise RuntimeError("OLLAMA_BASE_URL não configurada")
    if not modelo:
        raise RuntimeError("OLLAMA_MODEL não configurado")
    response = httpx.post(
        f"{base_url}/api/chat",
        json={
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.4},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama retornou uma resposta vazia")
    return content.strip()
