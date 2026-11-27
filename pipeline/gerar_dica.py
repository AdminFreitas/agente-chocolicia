"""Geração e publicação automática de dicas culinárias pela API Chocolícia.

O modelo de linguagem é selecionado pelo serviço compartilhado services.llm_service.
O contrato de publicação é a API dedicada /api/tips do site.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import date
from pathlib import Path
from uuid import uuid4

from agente_receitas.integration.cliente_site import ClienteSite
from services import llm_service

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

TOPICOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "preparo": ("Preparo de doces", ("erros comuns", "passo a passo", "temperatura e ponto", "como corrigir")),
    "montagem-e-apresentacao": ("Montagem e apresentação", ("acabamento", "embalagem", "fotografia de doces")),
    "ornamentacao": ("Ornamentação", ("decoração com chocolate", "confeitos e coberturas", "técnicas de bico")),
    "equipamentos-uso": ("Uso de equipamentos", ("cuidados e limpeza", "uso correto", "aproveitamento")),
    "equipamentos-compra": ("Compra de equipamentos", ("o que priorizar", "iniciante ou profissional", "custo-benefício")),
    "negocios": ("Negócios de doces", ("precificação", "atendimento e vendas", "organização da produção")),
}

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
    return f"""Você é redator culinário da Chocolícia, em português do Brasil.
Escreva uma dica prática, original e útil sobre {rotulo}, com foco em {angulo}.
Use Markdown, subtítulos e linguagem acessível. Não invente dados, preços ou estatísticas.
O resumo deve ter entre 20 e 160 caracteres.
Não transforme o conteúdo em orientação médica ou nutricional.
Responda exatamente:
TITULO: ...
RESUMO: frase de até 160 caracteres
TEMPO_LEITURA: X min
===CORPO===
texto em Markdown."""


def _recortar(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[:limite - 1].rstrip() + "…"


def _cover_image_url() -> str | None:
    bruto = os.getenv("CHOCOLICIA_COVER_JSON", "").strip()
    if not bruto:
        return None
    try:
        cover = json.loads(bruto)
    except ValueError as exc:
        raise DicaInvalida("CHOCOLICIA_COVER_JSON não contém JSON válido.") from exc
    if not isinstance(cover, dict) or cover.get("mode") not in {"stock", "generate"}:
        raise DicaInvalida("CHOCOLICIA_COVER_JSON deve conter mode=stock ou mode=generate.")
    url = cover.get("sourceImageUrl") if cover.get("mode") == "stock" else None
    if url and not str(url).startswith("https://"):
        raise DicaInvalida("A imagem de capa precisa usar HTTPS.")
    return url


def montar_payload(dados: dict, topico: str, meta: dict, status: str, run_id: str) -> dict:
    titulo = dados["titulo"].strip()
    corpo = dados["corpo"].strip()
    resumo_bruto = (dados.get("excerpt") or "").strip()
    if len(resumo_bruto) < 20:
        resumo_bruto = f"{titulo}. {corpo}"
    resumo = _recortar(resumo_bruto, 160)
    payload = {
        "title": titulo,
        "slug": llm_service.gerar_slug(titulo),
        "excerpt": resumo,
        "content": corpo,
        "tipType": "dica",
        "topicSlug": topico,
        "agentTopicSlug": topico,
        "tags": [],
        "status": status,
        "reviewStatus": "approved" if status == "published" else "pending",
        "agentIdempotencyKey": hashlib.sha256(f"tip|{topico}|{run_id}".encode("utf-8")).hexdigest(),
        "generationMeta": {
            "run_id": run_id,
            "topic_slug": topico,
            "prompt_version": "chocolicia-tips-1.1.0",
            "phase": int(os.getenv("AGENT_PHASE", "0")),
            "sources": [],
            "validators_version": "culinary-content-1.0.0",
            "provider": meta.get("provedor", ""),
            "model": meta.get("modelo", ""),
        },
    }
    cover_url = _cover_image_url()
    if cover_url:
        payload["coverImageUrl"] = cover_url
        payload["coverImageAlt"] = _recortar(titulo, 240) if len(titulo) >= 8 else f"Dica: {titulo}"
    return payload


def validar_payload(payload: dict) -> None:
    if len(payload["title"]) < 5:
        raise DicaInvalida("Título muito curto.")
    if len(payload["content"]) < 600:
        raise DicaInvalida("A dica precisa ter pelo menos 600 caracteres.")
    if len(payload["content"]) > 30000:
        raise DicaInvalida("A dica excede o limite de 30000 caracteres aceito pelo site.")
    if payload["topicSlug"] not in TOPICOS:
        raise DicaInvalida("Tópico de dica inválido.")
    if not payload.get("agentIdempotencyKey") or len(payload["agentIdempotencyKey"]) > 128:
        raise DicaInvalida("Chave de idempotência inválida.")


def gerar_dica(assunto: str | None = "automatico", target: str = "preview", dry_run: bool = False, publish: bool = False) -> dict:
    if target not in {"preview", "producao"}:
        raise DicaInvalida("target deve ser 'preview' ou 'producao'.")
    topico = escolher_topico(assunto)
    angulo = random.choice(TOPICOS[topico][1])
    resposta = llm_service.gerar_texto_com_metadados("criacao", montar_prompt(topico, angulo))
    dados = llm_service.parsear_resposta_padrao(resposta["texto"])
    run_id = os.getenv("GITHUB_RUN_ID", "").strip() or str(uuid4())
    phase = int(os.getenv("AGENT_PHASE", "0"))
    status = "published" if publish else "draft"
    payload = montar_payload(dados, topico, resposta, status, run_id)
    validar_payload(payload)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"dica-{payload['slug']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if dry_run:
        return {"enviado": False, "payload": payload}

    base_url = os.getenv("SITE_BASE_URL", "").strip()
    if not base_url:
        base_url = os.getenv("SITE_BASE_URL_PROD" if target == "producao" else "SITE_BASE_URL_PREVIEW", "").strip()
    token_publish = os.getenv("SITE_TOKEN_PUBLISH", "").strip()
    if not token_publish:
        token_publish = os.getenv("SITE_TOKEN_PUBLISH_PROD" if target == "producao" else "SITE_TOKEN_PUBLISH_PREVIEW", "").strip()
    token_draft = os.getenv("SITE_TOKEN_DRAFT", "").strip()
    if not token_draft:
        token_draft = os.getenv("SITE_TOKEN_DRAFT_PROD" if target == "producao" else "SITE_TOKEN_DRAFT_PREVIEW", "").strip()
    if not base_url:
        raise DicaInvalida("URL do ambiente Chocolícia não configurada.")
    token_escolhido = token_publish if publish else token_draft
    if not token_escolhido:
        tipo_token = "publicação" if publish else "rascunho"
        raise DicaInvalida(f"Configure o token de {tipo_token} do ambiente escolhido.")

    cliente = ClienteSite(
        base_url,
        token_draft=token_draft,
        token_publish=token_publish,
        fase=phase,
        contract_version=os.getenv("CONTRACT_VERSION", "1"),
        dry_run=False,
        allow_production=(target == "producao"),
        articles_enabled=False,
        contract="v1",
    )
    resposta_site = cliente.criar_dica(payload, run_id=run_id)
    return {"enviado": True, "payload": payload, "site": resposta_site.__dict__}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Gera e publica automaticamente uma dica Chocolícia.")
    parser.add_argument("--assunto", default="automatico")
    parser.add_argument("--target", choices=("preview", "producao"), default=os.getenv("TARGET", "preview"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    resultado = gerar_dica(args.assunto, args.target, args.dry_run, args.publish)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
