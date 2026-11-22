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
    """Origem do site: CHOCOLICIA_API_URL, depois SITE_BASE_URL (definida pelos workflows)."""
    base = (os.getenv("CHOCOLICIA_API_URL") or os.getenv("SITE_BASE_URL") or DEFAULT_SITE_URL).strip().rstrip("/")
    if os.getenv("TARGET", "").strip().lower() == "preview" and base == DEFAULT_SITE_URL:
        raise SiteAPIError(
            f"TARGET=preview não pode enviar ao site de produção ({base}); aponte CHOCOLICIA_API_URL "
            "ou SITE_BASE_URL para o Preview, ou defina TARGET=producao."
        )
    return base


def resolve_endpoint(tipo: str) -> str:
    base = resolve_base_url()
    if base.endswith("/api/recipes") or base.endswith("/api/articles"):
        return base
    return f"{base}/api/recipes" if tipo == "receita" else f"{base}/api/articles"


def select_token(status: str) -> str:
    """Token Bearer do envio; o valor deve ser igual ao RECIPES_AGENT_TOKEN do site."""
    if status == "published":
        token = os.getenv("CHOCOLICIA_TOKEN_PUBLISH") or os.getenv("SITE_TOKEN_PUBLISH")
    else:
        token = os.getenv("CHOCOLICIA_TOKEN_DRAFT") or os.getenv("SITE_TOKEN_DRAFT")
    if not token:
        raise SiteAPIError(
            "Token Bearer ausente; configure CHOCOLICIA_TOKEN_DRAFT/CHOCOLICIA_TOKEN_PUBLISH "
            "(ou SITE_TOKEN_DRAFT/SITE_TOKEN_PUBLISH) com o mesmo valor do RECIPES_AGENT_TOKEN do site."
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
    for attempt in range(1, 4):
        try:
            response = httpx.post(endpoint, json=body, headers=headers, timeout=30)
            if response.status_code < 500:
                if not response.is_success:
                    if response.status_code == 404 and endpoint.endswith("/api/articles"):
                        raise SiteAPIError(
                            "O site não expõe POST /api/articles; faça deploy da versão do site com a rota de artigos no ambiente de destino.",
                            404,
                        )
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
