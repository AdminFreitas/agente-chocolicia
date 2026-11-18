#!/usr/bin/env python3
"""Gera uma receita ou dica com Ollama; dry-run e rascunho são o padrão."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from integration.content import build_payload, prompt_for, slugify
from integration.ollama_client import generate_json
from integration.site_client import post_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rodar_conteudo")


def run(args: argparse.Namespace) -> dict:
    load_dotenv()
    run_id = str(uuid.uuid4())
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{run_id}.json"
    try:
        if args.send and os.getenv("AGENT_ENABLED", "false").lower() != "true":
            raise RuntimeError("Envio bloqueado: defina AGENT_ENABLED=true explicitamente.")
        if args.publish and not args.send:
            raise RuntimeError("--publish exige também --send.")
        if args.publish and not (os.getenv("CHOCOLICIA_TOKEN_PUBLISH") or os.getenv("SITE_TOKEN_PUBLISH")):
            raise RuntimeError("Publicação exige CHOCOLICIA_TOKEN_PUBLISH/SITE_TOKEN_PUBLISH específico.")
        phase = int(os.getenv("AGENT_PHASE", "0"))
        if args.publish and phase == 0:
            raise RuntimeError("Publicação direta bloqueada na Fase 0; use rascunho.")
        cover_raw = os.getenv("CHOCOLICIA_COVER_JSON", "")
        cover = json.loads(cover_raw) if cover_raw else None
        prompt = prompt_for(args.tipo, args.tema, args.subcategoria, args.assunto)
        generated, model = generate_json(prompt)
        payload, schema_org, slug = build_payload(
            args.tipo,
            generated,
            topic=args.tema,
            cover=cover,
            model=model,
            phase=phase,
            publish=args.publish,
            subcategoria=args.subcategoria,
            assunto=args.assunto,
            run_id=run_id,
        )
        result = {"status": payload["status"], "payload": payload}
        # SEO metadata and JSON-LD are saved locally; API v1 in docs/06 does not
        # accept arbitrary meta_description/schema_org request fields.
        result["meta_description"] = payload["excerpt"]
        if schema_org:
            (output_dir / f"{slug}.schema.jsonld").write_text(
                json.dumps(schema_org, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if args.send:
            result["site_response"] = post_content(payload, args.tipo, slugify(args.tema) or slug)
            result["status"] = result["site_response"].get("status", "sent")
        else:
            logger.info("Dry-run concluído; payload salvo sem envio.")
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    except Exception as exc:
        logger.exception("Geração/publicação falhou; nenhum erro será propagado ao processo contínuo")
        failed = {"status": "failed", "error": str(exc), "run_id": run_id}
        try:
            result_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Não foi possível salvar resultado de falha")
        return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tipo", choices=("receita", "dica"), required=True)
    parser.add_argument("--tema", required=True, help="Tema ou pergunta específica")
    parser.add_argument("--subcategoria", help="Slug da subcategoria válida no site")
    parser.add_argument("--assunto", choices=(
        "preparo", "montagem-e-apresentacao", "ornamentacao", "equipamentos-uso",
        "equipamentos-compra", "negocios",
    ), help="Obrigatório para dicas; slug tipTopic do site")
    parser.add_argument("--send", action="store_true", help="Envia para o site; requer AGENT_ENABLED=true")
    parser.add_argument("--publish", action="store_true", help="Cria publicado; requer --send, fase > 0 e token publish")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
