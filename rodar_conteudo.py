#!/usr/bin/env python3
"""Gera conteúdo culinário com o serviço compartilhado de IA e integra com a API Chocolícia."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from integration.content import build_payload, prompt_for, slugify
from integration.site_client import post_content
from services import llm_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rodar_conteudo")


def _json_da_resposta(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^\x60{3}(?:json)?\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s*\x60{3}$", "", texto)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim < inicio:
        raise ValueError("O modelo não retornou um objeto JSON.")
    dados = json.loads(texto[inicio:fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("A resposta do modelo precisa ser um objeto JSON.")
    return dados


def run(args: argparse.Namespace) -> dict:
    load_dotenv()
    run_id = str(uuid.uuid4())
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{run_id}.json"
    try:
        if args.send and os.getenv("AGENT_ENABLED", "false").lower() != "true":
            raise RuntimeError("Envio desabilitado: AGENT_ENABLED precisa estar true.")
        if args.publish and not args.send:
            raise RuntimeError("--publish exige --send.")
        if args.publish and not (os.getenv("SITE_TOKEN_PUBLISH") or os.getenv("CHOCOLICIA_TOKEN_PUBLISH") or os.getenv("RECIPES_AGENT_TOKEN")):
            raise RuntimeError("Token de publicação SITE_TOKEN_PUBLISH não configurado.")

        cover_raw = os.getenv("CHOCOLICIA_COVER_JSON", "").strip()
        cover = json.loads(cover_raw) if cover_raw else None
        prompt = prompt_for(args.tipo, args.tema, args.subcategoria, args.assunto)
        resposta = llm_service.gerar_texto_com_metadados("criacao", prompt)
        generated = _json_da_resposta(resposta["texto"])
        modelo = f"{resposta.get('provedor', '')}:{resposta.get('modelo', '')}"[:120]
        payload, schema_org, slug = build_payload(
            args.tipo,
            generated,
            topic=args.tema,
            cover=cover,
            model=modelo,
            phase=int(os.getenv("AGENT_PHASE", "1")),
            publish=args.publish,
            subcategoria=args.subcategoria,
            assunto=args.assunto,
            run_id=run_id,
        )
        result = {"status": payload["status"], "payload": payload, "provider": resposta.get("provedor"), "model": resposta.get("modelo")}
        result["meta_description"] = payload["excerpt"]
        if schema_org:
            (output_dir / f"{slug}.schema.jsonld").write_text(
                json.dumps(schema_org, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if args.send:
            result["site_response"] = post_content(payload, args.tipo, slugify(args.tema) or slug)
        else:
            logger.info("Execução local concluída sem envio ao site.")
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    except Exception as exc:
        logger.exception("Geração/publicação falhou.")
        failed = {"status": "failed", "error": str(exc), "run_id": run_id}
        result_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tipo", choices=("receita", "dica"), required=True)
    parser.add_argument("--tema", required=True)
    parser.add_argument("--subcategoria")
    parser.add_argument("--assunto")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
