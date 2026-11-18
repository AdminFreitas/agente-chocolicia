"""Cliente autenticado e idempotente para a API documentada Chocolícia."""

from __future__ import annotations

import logging
import os
import time
import uuid

import httpx

logger = logging.getLogger(__name__)


class SiteAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def post_content(payload: dict, tipo: str, topic_slug: str) -> dict:
    base = os.getenv("CHOCOLICIA_API_URL", "https://www.chocolicia.site").rstrip("/")
    if base.endswith("/api/recipes") or base.endswith("/api/articles"):
        endpoint = base
    else:
        endpoint = f"{base}/api/recipes" if tipo == "receita" else f"{base}/api/articles"
    status = payload.get("status", "draft")
    token = (
        os.getenv("CHOCOLICIA_TOKEN_PUBLISH") or os.getenv("SITE_TOKEN_PUBLISH")
        if status == "published"
        else os.getenv("CHOCOLICIA_TOKEN_DRAFT") or os.getenv("SITE_TOKEN_DRAFT")
    ) or os.getenv("CRON_SECRET")
    if not token:
        raise SiteAPIError("Token Bearer ausente; configure o token de escopo ou CRON_SECRET.")
    run_id = payload.get("generationMeta", {}).get("run_id", "")
    idempotency_key = f"chocolicia-{tipo}-{topic_slug}-{run_id}"[:200]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
        "X-Contract-Version": os.getenv("CONTRACT_VERSION", "1"),
        "X-Request-Id": str(uuid.uuid4()),
    }
    for attempt in range(1, 4):
        try:
            response = httpx.post(endpoint, json=payload, headers=headers, timeout=30)
            if response.status_code < 500:
                if not response.is_success:
                    raise SiteAPIError(
                        f"API do site respondeu HTTP {response.status_code}: {response.text[:1000]}",
                        response.status_code,
                    )
                try:
                    return response.json()
                except ValueError:
                    return {"status": "sent", "http_status": response.status_code}
            logger.warning("API do site HTTP %s, tentativa %s/3", response.status_code, attempt)
        except SiteAPIError:
            raise
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede na API do site, tentativa %s/3: %s", attempt, exc)
        if attempt < 3:
            time.sleep(2 ** (attempt - 1))
    raise SiteAPIError("API do site indisponível após três tentativas.")
