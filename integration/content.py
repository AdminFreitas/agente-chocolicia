"""Adaptação de conteúdo gerado para o contrato documentado da API do site."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


PROMPT_BASE = """Você é redator culinário da Chocolícia. Escreva em português do Brasil,
com tom acolhedor, direto, preciso e natural. Evite clichês de IA, introduções
longas e conclusões artificiais. Não use primeira pessoa, alegue testes,
invente fontes, marcas, dados técnicos ou promessas de saúde. Use apenas os
fatos do tema fornecido. Responda somente com um objeto JSON válido, sem cercas.
"""


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:180].strip("-")


def prompt_for(tipo: str, tema: str, subcategoria: str | None, assunto: str | None) -> str:
    if tipo == "receita":
        contract = """JSON fields: title, excerpt (20-160 characters), intro, prepTimeMin
(integer 1-1440), cookTimeMin (integer 0-1440), restTimeMin (integer 0-10080),
servings (integer 1-500), yieldLabel, difficulty (Fácil/Média/Difícil),
ingredients (array of sections {name, items:[{name,quantity,unit,note,ingredientSlug}]}),
steps (4-20 objects {title,instruction}), tips (array up to 5), coverImageAlt,
faq (optional array of {question,answer}), tags (array of slugs),
subcategorySlug. Align all ingredient quantities with the sequential instructions.
Use standardized culinary units and provide precise, plausible quantities/times.
Do not invent safety/storage claims. Do not invent ingredient catalog slugs; omit
ingredientSlug when unknown. No schema_org or slug is needed; code derives both.
"""
    else:
        contract = """JSON fields: title, excerpt (20-160 characters), bodyMd (short helpful
Markdown article, 150-400 words), directAnswer (one or two direct sentences),
coverImageAlt, tags (array of slugs), relatedTopics (array of 2-4 topics).
Use only conservative, generally reliable culinary guidance. For safety or
storage claims, omit specifics that cannot be verified. No brands, health
claims, invented citations, schema_org or slug; code derives the slug.
"""
    return (
        f"{PROMPT_BASE}\nTipo: {tipo}\nTema: {tema}\n"
        f"Subcategoria: {subcategoria or 'não aplicável'}\n"
        f"Assunto da dica: {assunto or 'não aplicável'}\n\nContrato de saída:\n{contract}"
    )


def _require_text(data: dict[str, Any], key: str, minimum: int = 1, maximum: int | None = None) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Campo obrigatório inválido: {key}")
    value = value.strip()
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise ValueError(f"Campo {key} deve ter entre {minimum} e {maximum or '∞'} caracteres.")
    return value


def _validate_cover(cover: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(cover, dict) or cover.get("mode") not in {"stock", "generate"}:
        raise ValueError("CHOCOLICIA_COVER_JSON precisa ser objeto cover válido (stock ou generate).")
    if cover["mode"] == "stock" and not all(
        isinstance(cover.get(key), str) and cover[key].strip()
        for key in ("provider", "sourceImageUrl", "sourcePageUrl", "author", "license", "attributionText")
    ):
        raise ValueError("Capa stock exige provider, URLs, autor, licença e crédito verificados.")
    if cover["mode"] == "generate" and not cover.get("imagePrompt"):
        raise ValueError("Capa generate exige imagePrompt.")
    return cover


def build_payload(
    tipo: str,
    generated: dict[str, Any],
    *,
    topic: str,
    cover: dict[str, Any] | None,
    model: str,
    phase: int = 0,
    publish: bool = False,
    subcategoria: str | None = None,
    assunto: str | None = None,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    title = _require_text(generated, "title", 5, 180)
    excerpt = _require_text(generated, "excerpt", 20, 160)
    slug = slugify(title)
    if len(slug) < 3:
        raise ValueError("O título não produziu slug válido.")
    cover_data = _validate_cover(cover)
    common = {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
        "tags": list(dict.fromkeys(slugify(str(tag))[:40] for tag in generated.get("tags", []) if slugify(str(tag))))[:12],
        "cover": cover_data,
        "coverImageAlt": _require_text(generated, "coverImageAlt", 8, 240),
        "status": "published" if publish else "draft",
        "aiModel": model[:120],
        "generationMeta": {
            "run_id": run_id,
            "topic_slug": slugify(topic) or slug,
            "prompt_version": "chocolicia-cloud-1.0.0",
            "phase": phase,
            "sources": [],
            "validators_version": "basic-structure-1.0.0",
        },
    }
    if tipo == "receita":
        required = ("prepTimeMin", "cookTimeMin", "servings", "difficulty", "ingredients", "steps")
        missing = [key for key in required if key not in generated]
        if missing:
            raise ValueError(f"Campos de receita ausentes: {', '.join(missing)}")
        ingredients = generated["ingredients"]
        steps = generated["steps"]
        if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 20:
            raise ValueError("ingredients deve conter de 1 a 20 seções.")
        if not isinstance(steps, list) or not 4 <= len(steps) <= 20:
            raise ValueError("steps deve conter de 4 a 20 passos.")
        for section in ingredients:
            if not isinstance(section, dict) or not section.get("name") or not isinstance(section.get("items"), list) or not section["items"]:
                raise ValueError("Cada seção de ingredientes exige name e items não vazios.")
            for item in section["items"]:
                if not isinstance(item, dict) or not all(item.get(k) for k in ("name", "quantity", "unit")):
                    raise ValueError("Cada ingrediente exige name, quantity e unit.")
        for step in steps:
            if not isinstance(step, dict) or not step.get("instruction"):
                raise ValueError("Cada passo exige instruction.")
        if generated["difficulty"] not in {"Fácil", "Média", "Difícil"}:
            raise ValueError("difficulty deve ser Fácil, Média ou Difícil conforme contrato do site.")
        payload = {
            **common,
            "intro": str(generated.get("intro", "")).strip(),
            "subcategorySlug": subcategoria or generated.get("subcategorySlug"),
            "prepTimeMin": generated["prepTimeMin"],
            "cookTimeMin": generated["cookTimeMin"],
            "restTimeMin": generated.get("restTimeMin", 0),
            "servings": generated["servings"],
            "yieldLabel": str(generated.get("yieldLabel", ""))[:80],
            "difficulty": generated["difficulty"],
            "ingredients": ingredients,
            "steps": steps,
            "tips": [str(t).strip() for t in generated.get("tips", []) if str(t).strip()][:5],
            "faq": generated.get("faq", [])[:12],
        }
        if not payload["subcategorySlug"]:
            raise ValueError("Receita exige subcategoria válida.")
        jsonld = {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": title,
            "description": excerpt,
            "recipeCategory": payload["subcategorySlug"],
            "prepTime": f"PT{payload['prepTimeMin']}M",
            "cookTime": f"PT{payload['cookTimeMin']}M",
            "recipeYield": payload["yieldLabel"] or f"{payload['servings']} porções",
            "recipeIngredient": [
                " ".join(str(item.get(k, "")).strip() for k in ("quantity", "unit", "name", "note") if item.get(k))
                for section in ingredients for item in section["items"]
            ],
            "recipeInstructions": [
                {"@type": "HowToStep", "text": step["instruction"]} for step in steps
            ],
        }
    elif tipo == "dica":
        body = _require_text(generated, "bodyMd", 1, 20000)
        direct_answer = _require_text(generated, "directAnswer", 1, 1000)
        payload = {
            **common,
            "type": "tip",
            "bodyMd": body,
            "structured": {"direct_answer": direct_answer},
            "relatedTopics": [str(t).strip() for t in generated.get("relatedTopics", []) if str(t).strip()][:6],
            "tipTopic": assunto,
        }
        if not assunto:
            raise ValueError("Dica exige --assunto com um tipTopic habilitado no site.")
        if subcategoria:
            payload["subcategorySlug"] = subcategoria
        jsonld = None
    else:
        raise ValueError("tipo deve ser receita ou dica.")
    return payload, jsonld, slug


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
