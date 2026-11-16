"""Compatibilidade opcional com a API atual do site.

Este módulo não é usado pelo fluxo v1 principal e não consulta o site ao
importar. O mapa de categorias é obrigatório para evitar assumir a taxonomia
do repositório externo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CATEGORIAS_SITE_ATUAL = frozenset({
    "Bolos", "Brigadeiros e docinhos", "Tortas", "Sobremesas",
    "Chocolates", "Festas e buffet", "Datas especiais",
})


class CompatSiteAtualError(ValueError):
    pass


@dataclass(frozen=True)
class PayloadCompat:
    payload: dict[str, Any]
    lacunas: tuple[str, ...]


def converter_receita(
    payload_v1: Mapping[str, Any],
    *,
    categorias_aceitas: Mapping[str, str],
    status: str = "draft",
) -> PayloadCompat:
    """Converte o payload v1 para o formato mínimo da API atual.

    `categorias_aceitas` deve vir do contrato do site atual e mapear
    subcategoria -> categoria. Status diferente de ``draft`` é rejeitado.
    """
    if status != "draft":
        raise CompatSiteAtualError("compatibilidade com o site atual aceita somente status='draft'")
    meta = payload_v1.get("generationMeta") or {}
    subcat = payload_v1.get("subcategorySlug")
    categoria = categorias_aceitas.get(subcat)
    if not categoria:
        raise CompatSiteAtualError(f"categoria_sem_equivalente_no_site: {subcat!r}")
    if categoria not in CATEGORIAS_SITE_ATUAL:
        raise CompatSiteAtualError(f"categoria fora do enum do site atual: {categoria!r}")

    lacunas: list[str] = []
    cover = payload_v1.get("cover") or {}
    if cover.get("mode") != "stock" or not cover.get("sourceImageUrl"):
        raise CompatSiteAtualError("coverImageUrl_obrigatoria: imagem gerada não pode ser enviada ao site atual")
    for campo in ("intro", "restTimeMin", "yieldLabel", "collections", "diet", "generationMeta"):
        if payload_v1.get(campo) not in (None, [], {}):
            lacunas.append(campo)

    ingredientes = []
    for sec in payload_v1.get("ingredients", []):
        ingredientes.append({
            "name": sec.get("name", ""),
            "items": [{
                "name": item.get("name", ""),
                "quantity": str(item.get("quantity", "")),
                "unit": str(item.get("unit", "")),
                "note": item.get("note"),
            } for item in sec.get("items", [])],
        })
    if not 1 <= len(ingredientes) <= 20:
        raise CompatSiteAtualError("ingredients: esperado 1..20 seções")
    passos = [{"title": p.get("title"), "instruction": p.get("instruction", "")} for p in payload_v1.get("steps", [])]
    if not 2 <= len(passos) <= 30:
        raise CompatSiteAtualError("steps: esperado 2..30 passos")
    title, excerpt = payload_v1.get("title"), payload_v1.get("excerpt")
    if not isinstance(title, str) or not 5 <= len(title) <= 180:
        raise CompatSiteAtualError("title fora do intervalo 5..180")
    if not isinstance(excerpt, str) or not 20 <= len(excerpt) <= 160:
        raise CompatSiteAtualError("excerpt fora do intervalo 20..160")
    alt = payload_v1.get("coverImageAlt", "")
    if not isinstance(alt, str) or not 8 <= len(alt) <= 240:
        raise CompatSiteAtualError("coverImageAlt fora do intervalo 8..240")
    result = {
        "title": title,
        "excerpt": excerpt,
        "slug": payload_v1.get("slug"),
        "category": categoria,
        "subcategory": subcat,
        "prepTimeMin": payload_v1.get("prepTimeMin"),
        "cookTimeMin": payload_v1.get("cookTimeMin"),
        "servings": payload_v1.get("servings"),
        "ingredients": ingredientes,
        "steps": passos,
        "tips": payload_v1.get("tips", [])[:12],
        "storageNotes": payload_v1.get("storageNotes"),
        "faq": payload_v1.get("faq", [])[:12],
        "tags": payload_v1.get("tags", [])[:12],
        "coverImageUrl": cover.get("sourceImageUrl"),
        "coverImageAlt": payload_v1.get("coverImageAlt"),
        "status": "draft",
        "imagePrompt": cover.get("imagePrompt") if cover.get("mode") == "generate" else None,
    }
    if result["imagePrompt"] is None:
        result.pop("imagePrompt")
    if result["slug"] is None:
        result.pop("slug")
    if result["storageNotes"] is None:
        result.pop("storageNotes")
    return PayloadCompat(result, tuple(lacunas))


def preparar_dica_para_saida(dica: Mapping[str, Any], destino: str | Path) -> Path:
    """Grava dica validada em JSON local; não tenta enviá-la como artigo."""
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dict(dica), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return caminho


def enviar_rascunho(cliente, url: str, payload: PayloadCompat, *, token: str):
    """Envia via cliente httpx fornecido pelo teste, nunca via configuração implícita."""
    if not token:
        raise CompatSiteAtualError("token obrigatório")
    corpo = json.dumps(payload.payload, ensure_ascii=False).encode("utf-8")
    if len(corpo) > 1_000_000:
        raise CompatSiteAtualError("payload excede 1.000.000 bytes")
    return cliente.post(url, content=corpo, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
