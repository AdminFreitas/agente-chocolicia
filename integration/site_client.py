"""Cliente autenticado para a API do site Chocolícia.

Contrato que o site (AdminFreitas/chocolicia) implementa hoje:

* ``POST /api/recipes``: Bearer igual ao ``RECIPES_AGENT_TOKEN`` do site; corpo
  validado por ``recipeInputSchema`` (``shared/recipes.ts``). Exige ``category`` e
  ``coverImageUrl`` (imagem já hospedada) e aceita ``status`` ``draft`` ou
  ``published``. O site não aplica escopos por token nem usa ``Idempotency-Key``.
* ``POST /api/articles`` (dicas): mesmo Bearer; corpo estrito (``articleInputSchema``),
  aceita ``topicSlug``/``categorySlug``. Respostas: 400 validação, 401/403 token,
  409 slug duplicado, 422 categoria/tópico inexistente, 503 token não configurado.
* O site não usa o objeto ``cover`` do contrato v1 planejado em ``docs/06-INTEGRACAO.md``.

O payload local (``integration/content.py``) segue o contrato v1 e é salvo assim em
``output/``; aqui ele é convertido para o formato que o site aceita antes do envio.
"""

from __future__ import annotations

import logging
import os
import time
import uuid

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SITE_URL = "https://www.chocolicia.site"

# Espelho de RECIPE_TAXONOMY (shared/recipes.ts do repositório do site): categoria -> subcategorias.
SITE_TAXONOMY: dict[str, tuple[str, ...]] = {
    "Bolos": ("bolos-de-chocolate", "bolos-de-aniversario", "bolos-caseiros", "bolos-recheados", "bolos-especiais"),
    "Brigadeiros e docinhos": ("brigadeiros", "docinhos"),
    "Tortas": ("tortas-doces",),
    "Sobremesas": ("mousses",),
    "Chocolates": ("trufas-e-bombons",),
    "Festas e buffet": ("docinhos-para-festa",),
    "Datas especiais": ("celebracoes",),
}

# Campos de recipeInputSchema que o agente preenche. Os demais campos do payload local
# (intro, restTimeMin, yieldLabel, cover...) continuam só no JSON salvo em output/.
SITE_RECIPE_FIELDS = (
    "slug", "title", "excerpt", "subcategorySlug", "tags", "coverImageAlt", "ingredients",
    "steps", "tips", "faq", "prepTimeMin", "cookTimeMin", "servings", "difficulty", "status", "aiModel",
)


class SiteAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def resolve_base_url() -> str:
    """SITE_BASE_URL é a origem explícita selecionada pelo workflow."""
    base = (os.getenv("SITE_BASE_URL") or os.getenv("CHOCOLICIA_API_URL") or DEFAULT_SITE_URL).strip().rstrip("/")
    if not base:
        raise SiteAPIError("SITE_BASE_URL não está configurada.")
    if os.getenv("TARGET", "").strip().lower() == "preview":
        from urllib.parse import urlparse
        host = (urlparse(base).hostname or "").lower()
        if host in {"chocolicia.site", "www.chocolicia.site"}:
            raise SiteAPIError("TARGET=preview não pode enviar ao domínio de produção; configure SITE_BASE_URL para o Preview.")
    return base


def resolve_endpoint(tipo: str) -> str:
    base = resolve_base_url()
    if base.endswith("/api/recipes") or base.endswith("/api/articles"):
        return base
    return f"{base}/api/recipes" if tipo == "receita" else f"{base}/api/articles"


def select_token(status: str) -> str:
    """Seleciona o Bearer do site; nunca usa CRON_SECRET."""
    if status == "published":
        token = os.getenv("SITE_TOKEN_PUBLISH") or os.getenv("CHOCOLICIA_TOKEN_PUBLISH")
    else:
        token = os.getenv("SITE_TOKEN_DRAFT") or os.getenv("CHOCOLICIA_TOKEN_DRAFT")
    if not token:
        raise SiteAPIError(
            "Token Bearer ausente. Configure SITE_TOKEN_DRAFT com o mesmo valor de "
            "RECIPES_AGENT_TOKEN no site (compatibilidade: CHOCOLICIA_TOKEN_DRAFT)."
        )
    return token


def category_for_subcategory(subcategory_slug: str | None) -> str:
    for category, subcategories in SITE_TAXONOMY.items():
        if subcategory_slug in subcategories:
            return category
    valid = ", ".join(slug for subs in SITE_TAXONOMY.values() for slug in subs)
    raise SiteAPIError(f"Subcategoria '{subcategory_slug}' não existe no site. Válidas: {valid}.")


def to_site_recipe_payload(payload: dict) -> dict:
    """Converte o payload local (contrato v1) para o corpo de ``POST /api/recipes`` do site."""
    cover = payload.get("cover") or {}
    image_url = cover.get("sourceImageUrl") if cover.get("mode") == "stock" else None
    if not image_url:
        raise SiteAPIError(
            "POST /api/recipes exige imagem já hospedada (coverImageUrl). Configure CHOCOLICIA_COVER_JSON com "
            "mode=stock e sourceImageUrl; cover.mode=generate não é suportado pelo site atual."
        )
    body = {key: payload[key] for key in SITE_RECIPE_FIELDS if key in payload}
    body["category"] = category_for_subcategory(payload.get("subcategorySlug"))
    body["coverImageUrl"] = image_url
    # O site não tem campo de crédito da imagem; preserva a atribuição em generationMeta.
    body["generationMeta"] = {**(payload.get("generationMeta") or {}), "cover": cover}
    return body


def _safe_response_text(response: httpx.Response, token: str) -> str:
    """Extrai uma mensagem curta sem permitir que o servidor reflita o Bearer no log."""
    body = (response.text or "").replace(token, "[REDACTED]")
    return body[:600]


def _http_message(status: int, body: str) -> str:
    details = body.strip()
    if status == 400:
        return "Payload rejeitado (HTTP 400). Confira os campos e o contrato da API."
    if status == 401:
        return "A API do site não recebeu autenticação válida (HTTP 401). Confira o Bearer."
    if status == 403:
        return "A API do site recusou o token (HTTP 403). Confira se corresponde a RECIPES_AGENT_TOKEN."
    if status == 404:
        return "A rota do site não foi encontrada (HTTP 404). Confirme se /api/articles está implantada no ambiente escolhido."
    if status == 409:
        return "Slug duplicado (HTTP 409). Gere um slug novo antes de repetir o envio."
    if status == 422:
        return "Categoria ou tópico não cadastrado/aceito pelo site (HTTP 422). Verifique os registros existentes no Neon."
    if status == 503:
        return "A API do site está indisponível ou sem configuração obrigatória (HTTP 503)."
    if status == 429:
        return "A API do site limitou as requisições (HTTP 429)."
    return f"API do site respondeu HTTP {status}." + (f" Detalhe: {details}" if details else "")


def post_content(payload: dict, tipo: str, topic_slug: str) -> dict:
    endpoint = resolve_endpoint(tipo)
    status = payload.get("status", "draft")
    token = select_token(status)
    body = to_site_recipe_payload(payload) if tipo == "receita" else payload
    run_id = payload.get("generationMeta", {}).get("run_id", "")
    idempotency_key = f"chocolicia-{tipo}-{topic_slug}-{run_id}"[:200]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
        "X-Contract-Version": os.getenv("CONTRACT_VERSION", "1"),
        "X-Request-Id": str(uuid.uuid4()),
    }
    retryable_statuses = {429, 500, 502, 504}
    last_status: int | None = None
    for attempt in range(1, 4):
        try:
            response = httpx.post(endpoint, json=body, headers=headers, timeout=30)
            if response.is_success:
                try:
                    return response.json()
                except ValueError:
                    return {"status": "sent", "http_status": response.status_code}
            last_status = response.status_code
            safe_body = _safe_response_text(response, token)
            if response.status_code not in retryable_statuses:
                raise SiteAPIError(_http_message(response.status_code, safe_body), response.status_code)
            logger.warning("API do site HTTP %s; tentativa %s/3", response.status_code, attempt)
        except SiteAPIError:
            raise
        except httpx.TimeoutException:
            logger.warning("Timeout na API do site; tentativa %s/3", attempt)
        except httpx.HTTPError as exc:
            logger.warning("Falha de conexão com a API do site (%s); tentativa %s/3", type(exc).__name__, attempt)
        if attempt < 3:
            time.sleep(2 ** (attempt - 1))
    if last_status is not None:
        raise SiteAPIError(_http_message(last_status, ""), last_status)
    raise SiteAPIError("A API do site não respondeu após três tentativas de conexão/timeout.")
