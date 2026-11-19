"""
integration/adaptador_artigo.py — Converte a dica do agente (docs/03 §7) para o payload
v1 de POST /api/articles (docs/06 §8). Técnica e matéria: PENDENTE (prompts de docs/03 §8
e §9 ainda não escritos).

Código decide (como em adaptador_receita.py): slug, tipTopic e subcategoria (da pauta),
status (parâmetro), aiModel e generationMeta. `structured` leva {"direct_answer": ...}
(docs/04 §10). O texto alternativo da imagem vem do passo de SEO (docs/05 §13, tarefa 4):
a dica não o escreve (docs/03 §7). Sem ele, o payload não existe (IMG-08).
"""

from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from integration.adaptador_receita import slugificar
from integration.cliente_site import ContratoInvalido
from integration.contratos import ArtigoV1


def montar_payload_dica(
    conteudo: dict,
    *,
    pauta: dict,
    ficha: dict,
    cover: Optional[dict],
    run_id: str,
    fase: int,
    modelo: dict,
    prompt_version: str,
    status: str = "draft",
    validators_version: str = "pendente",
) -> ArtigoV1:
    if cover is None:
        raise ContratoInvalido([{"campo": "cover", "detalhe": "sem capa (IMG-07: geração indisponível)"}])
    if not pauta.get("topic_slug") or not pauta.get("assunto"):
        raise ContratoInvalido([{"campo": "pauta", "detalhe": "a pauta de dica precisa de topic_slug e assunto"}])
    if conteudo.get("assunto") != pauta["assunto"]:
        raise ContratoInvalido([{"campo": "tipTopic", "detalhe": "o assunto vem da pauta e não pode mudar"}])
    if (conteudo.get("subcategoria") or None) != (pauta.get("subcategoria") or None):
        raise ContratoInvalido([{"campo": "subcategorySlug", "detalhe": "a subcategoria vem da pauta e não pode mudar"}])
    alt = (conteudo.get("texto_alt_imagem") or "").strip()
    if not alt:
        raise ContratoInvalido([{"campo": "coverImageAlt", "detalhe": "sem texto alternativo (IMG-08); ele vem do passo de SEO"}])

    reservados = {pauta["assunto"], pauta.get("subcategoria"), pauta.get("categoria")}
    tags: list[str] = []
    for t in conteudo.get("tags", []):
        s = slugificar(t, 40)
        if s and s not in reservados and s not in tags:
            tags.append(s)

    modelo_ia = "/".join(x for x in (modelo.get("provedor"), modelo.get("modelo")) if x)[:120] or "nao-informado"
    bruto = {
        "type": "tip",
        "title": conteudo["titulo"],
        "slug": slugificar(conteudo["titulo"], 180),
        "excerpt": conteudo["descricao_curta"],
        "subcategorySlug": pauta.get("subcategoria"),
        "tipTopic": pauta["assunto"],
        "bodyMd": conteudo["corpo"],
        "structured": {"direct_answer": conteudo["resposta_direta"]},
        "sources": [
            {
                "name": str(ref.get("fonte") or ref["dominio"])[:200],
                "title": str(ref.get("titulo_pagina") or ref["dominio"])[:300],
                "url": ref["url"],
            }
            for ref in ficha.get("referencias_registro", [])
        ],
        "tags": tags[:12],
        "relatedTopics": list(conteudo.get("temas_relacionados") or []),
        "cover": cover,
        "coverImageAlt": alt,
        "status": status,
        "aiModel": modelo_ia,
        "generationMeta": {
            "run_id": run_id,
            "topic_slug": pauta["topic_slug"],
            "prompt_version": prompt_version,
            "phase": fase,
            "sources": [
                {"domain": r["dominio"], "url": r["url"], "date": str(r["acessado_em"])[:10]}
                for r in ficha.get("referencias_registro", [])
            ],
            "validators_version": validators_version,
        },
    }
    try:
        return ArtigoV1.model_validate({k: v for k, v in bruto.items() if v is not None})
    except ValidationError as exc:
        raise ContratoInvalido(
            [{"campo": ".".join(map(str, e["loc"])), "detalhe": e["msg"]} for e in exc.errors()]
        ) from None
