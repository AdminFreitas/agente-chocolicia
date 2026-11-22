"""Fluxo de dicas: LLM em nuvem -> validação -> POST /api/articles do site.

Não usa banco do agente nem Ollama. O payload segue o schema estrito do site
(``articleInputSchema``): campos extras são rejeitados com HTTP 400.
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import date, datetime, timezone
from pathlib import Path

from integration import site_client
from services import llm_service

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# slug do tópico (tip_topics.slug no site) -> (rótulo, ângulos editoriais)
TOPICOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "preparo": ("Preparo de doces", ("erros comuns", "passo a passo rápido", "temperatura e ponto", "como corrigir")),
    "montagem-e-apresentacao": ("Montagem e apresentação", ("acabamento profissional", "embalagem", "fotografar doces")),
    "ornamentacao": ("Ornamentação", ("decoração com chocolate", "confeitos e coberturas", "técnicas de bico")),
    "equipamentos-uso": ("Uso de equipamentos", ("cuidados e limpeza", "uso correto", "aproveitar melhor")),
    "equipamentos-compra": ("Compra de equipamentos", ("o que priorizar", "iniciante x profissional", "custo-benefício")),
    "negocios": ("Negócios de doces", ("precificação", "atendimento e vendas", "organização da produção")),
}

TAMANHO_MINIMO_CORPO = 600


class DicaInvalida(ValueError):
    pass


def escolher_topico(assunto: str | None, rng: random.Random | None = None) -> str:
    if assunto and assunto != "automatico":
        if assunto not in TOPICOS:
            raise DicaInvalida(f"Assunto desconhecido '{assunto}'. Válidos: {', '.join(TOPICOS)}.")
        return assunto
    return (rng or random).choice(list(TOPICOS))


def montar_prompt(topico: str, angulo: str) -> str:
    rotulo = TOPICOS[topico][0]
    return f"""Você é editor do blog Chocolícia, sobre chocolate e confeitaria, em português do Brasil.
Escreva uma DICA prática e original sobre: {rotulo} (ângulo: {angulo}).
Use Markdown, de 400 a 700 palavras, com subtítulos (##), listas curtas e linguagem acessível.
Não invente dados, preços ou estatísticas.
Responda exatamente neste formato:
TITULO: ...
RESUMO: uma frase de até 160 caracteres
TEMPO_LEITURA: X min
===CORPO===
(texto em Markdown)"""


def _tags(topico: str, titulo: str) -> list[str]:
    base = ["dicas", TOPICOS[topico][0].lower(), "chocolate"]
    vistos: list[str] = []
    for tag in base:
        if tag not in vistos:
            vistos.append(tag)
    return vistos


def _recortar(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def montar_payload(dados: dict, topico: str, meta: dict, status: str, cover: dict | None = None) -> dict:
    slug = llm_service.gerar_slug(dados["titulo"]).strip("-")
    payload = {
        "title": dados["titulo"].strip(),
        "slug": slug,
        "excerpt": _recortar(dados.get("excerpt") or "", 300) or None,
        "content": dados["corpo"].strip(),
        "articleType": "dica",
        "status": status,
        "topicSlug": topico,
        "seoTitle": _recortar(dados["titulo"], 60),
        "seoDescription": _recortar(dados.get("excerpt") or dados["titulo"], 160),
        "author": "Chocolícia",
        "aiModel": f"{meta.get('provedor', '')}:{meta.get('modelo', '')}".strip(":") or None,
        "generationMeta": {
            "agent": "agente-chocolicia",
            "run_date": date.today().isoformat(),
            "provider": meta.get("provedor", ""),
            "model": meta.get("modelo", ""),
            "readTime": dados.get("readTime", ""),
        },
        "tags": _tags(topico, dados["titulo"]),
    }
    if cover and cover.get("sourceImageUrl"):
        payload["coverImageUrl"] = cover["sourceImageUrl"]
        payload["coverImageAlt"] = cover.get("alt") or dados["titulo"]
    return {k: v for k, v in payload.items() if v is not None}


def validar_payload(payload: dict) -> None:
    erros = []
    if not payload.get("title"):
        erros.append("título vazio")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", payload.get("slug", "")):
        erros.append("slug inválido")
    if len(payload.get("content", "")) < TAMANHO_MINIMO_CORPO:
        erros.append(f"conteúdo com menos de {TAMANHO_MINIMO_CORPO} caracteres")
    if payload.get("articleType") != "dica":
        erros.append("articleType deve ser 'dica'")
    if payload.get("status") not in ("draft", "published"):
        erros.append("status inválido")
    if payload.get("topicSlug") not in TOPICOS:
        erros.append("topicSlug desconhecido")
    if erros:
        raise DicaInvalida("Dica reprovada na validação: " + "; ".join(erros))


def _cover_do_ambiente() -> dict | None:
    bruto = os.getenv("CHOCOLICIA_COVER_JSON", "").strip()
    if not bruto:
        return None
    try:
        cover = json.loads(bruto)
    except ValueError as exc:
        raise DicaInvalida("CHOCOLICIA_COVER_JSON não é JSON válido.") from exc
    return cover if cover.get("mode", "stock") == "stock" else None


def _status(target: str) -> str:
    """Dicas editoriais são sempre rascunhos; target escolhe apenas o host."""
    return "draft"


def gerar_dica(assunto: str | None = "automatico", target: str = "preview", dry_run: bool = False) -> dict:
    """Gera, valida e (se não for dry-run) envia uma dica. Lança exceção em qualquer falha."""
    if target not in {"preview", "producao"}:
        raise DicaInvalida("target deve ser 'preview' ou 'producao'.")
    topico = escolher_topico(assunto)
    angulo = random.choice(TOPICOS[topico][1])
    resposta = llm_service.gerar_texto_com_metadados("criacao", montar_prompt(topico, angulo))
    dados = llm_service.parsear_resposta_padrao(resposta["texto"])
    payload = montar_payload(dados, topico, resposta, _status(target), _cover_do_ambiente())
    validar_payload(payload)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"dica-{payload['slug']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if dry_run:
        return {"enviado": False, "payload": payload}

    try:
        resposta_site = site_client.post_content(payload, "dica", topico)
    except site_client.SiteAPIError as exc:
        if exc.status_code != 409:
            raise
        sufixo = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        payload["slug"] = f"{payload['slug']}-{sufixo}"[:180]
        resposta_site = site_client.post_content(payload, "dica", topico)
    return {"enviado": True, "payload": payload, "site": resposta_site}
