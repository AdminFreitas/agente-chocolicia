from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

import httpx


@dataclass
class ImagemGerada:
    conteudo: bytes
    mime: str = "image/png"
    sha256: str = ""

    def __post_init__(self):
        if not self.sha256:
            self.sha256 = hashlib.sha256(self.conteudo).hexdigest()


def gerar_imagem(prompt: str) -> ImagemGerada:
    api_key = os.getenv("IMAGE_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    base = (os.getenv("IMAGE_API_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"))
    model = os.getenv("IMAGE_MODEL", "gpt-image-1").strip()
    if not api_key:
        raise RuntimeError("IMAGE_API_KEY ou OPENAI_API_KEY é obrigatório para gerar capas")
    response = httpx.post(
        f"{base}/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt, "size": "1536x1024", "quality": "medium", "response_format": "b64_json"},
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"serviço de imagens respondeu HTTP {response.status_code}")
    encoded = (response.json().get("data") or [{}])[0].get("b64_json")
    if not encoded:
        raise RuntimeError("serviço de imagens não devolveu conteúdo codificado")
    return ImagemGerada(base64.b64decode(encoded))
