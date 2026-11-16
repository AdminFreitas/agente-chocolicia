"""Compatibilidade opcional com a API atual do site.

Este módulo não é usado pelo fluxo v1 principal e não consulta o site ao
importar. O mapa de categorias é obrigatório para evitar assumir a taxonomia
do repositório externo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


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

    `categorias_aceitas` deve vir do contrato do site atual. Status diferente
    de ``draft`` é rejeitado deliberadamente neste caminho de compatibilidade.
    """
    if status != "draft":
        raise CompatSiteAtualError("compatibilidade com o site atual aceita somente status='draft'")
    meta = payload_v1.get("generationMeta") or {}
    subcat = payload_v1.get("subcategorySlug")
    categoria = categorias_aceitas.get(subcat)
    if not categoria:
        raise CompatSiteAtualError(f"subcategoria sem mapeamento no site atual: {subcat!r}")

    lacunas: list[str] = []
    cover = payload_v1.get("cover") or {}
    if cover.get("mode") != "stock":
        lacunas.append("coverImageUrl")
    if not payload_v1.get("intro"):
        lacunas.append("intro")
    if not payload_v1.get("yieldLabel"):
        lacunas.append("yieldLabel")

    ingredientes = []
    for sec in payload_v1.get("ingredients", []):
        ingredientes.extend(
            {"name": item["name"], "quantity": item["quantity"], "unit": item["unit"], "note": item.get("note")}
            for item in sec.get("items", [])
        )
    result = {
        "title": payload_v1.get("title"),
        "excerpt": payload_v1.get("excerpt"),
        "category": categoria,
        "subcategory": subcat,
        "prepTimeMin": payload_v1.get("prepTimeMin"),
        "cookTimeMin": payload_v1.get("cookTimeMin"),
        "servings": payload_v1.get("servings"),
        "ingredients": ingredientes,
        "steps": [p.get("instruction", "") for p in payload_v1.get("steps", [])],
        "tags": payload_v1.get("tags", []),
        "coverImageUrl": cover.get("sourceImageUrl"),
        "coverImageAlt": payload_v1.get("coverImageAlt"),
        "status": "draft",
        "agentTopicSlug": meta.get("topic_slug"),
    }
    return PayloadCompat(result, tuple(lacunas))


def preparar_dica_para_saida(dica: Mapping[str, Any], destino: str | Path) -> Path:
    """Grava dica validada em JSON local; não tenta enviá-la como artigo."""
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dict(dica), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return caminho


def enviar_rascunho(transport, url: str, payload: PayloadCompat, *, headers: Mapping[str, str] | None = None):
    """Envia somente quando o chamador fornece um transporte explícito de teste."""
    if transport is None:
        raise CompatSiteAtualError("transporte explícito obrigatório; use MockTransport nos testes")
    return transport.post(url, json=payload.payload, headers=dict(headers or {}))
