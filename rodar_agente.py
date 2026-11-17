"""CLI segura do agente Chocolícia, sem leitura de `.env` no import."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from runtime_adapters.cli_contract import build_services


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Executa o agente Chocolícia")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--receita", action="store_true")
    grupo.add_argument("--dica", action="store_true")
    grupo.add_argument(
        "--artigo", action="store_true", help="legado; removido na refatoração"
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--target", choices=("preview", "producao"), default="preview"
    )
    p.add_argument("--contrato", choices=("v1", "site-atual"), default="v1")
    p.add_argument("--fase", type=int, choices=(0, 1, 2, 3), default=0)
    p.add_argument("--assunto", default="automatico")
    p.add_argument("--subcategoria")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.artigo:
        print(
            "FALHA: --artigo foi removido na refatoração; use --receita no prompt 3"
        )
        return 1
    if os.environ.get("AGENT_ENABLED", "false").lower() != "true":
        print(json.dumps(
            {"estado": "desabilitado", "motivo": "AGENT_ENABLED=false"},
            ensure_ascii=False,
        ))
        return 0
    tipo = "receita" if args.receita else "dica"
    try:
        services = build_services(
            dry_run=args.dry_run, fase=args.fase, contrato=args.contrato,
            target=args.target,
        )
        dependencias = services.get(f"dependencias_{tipo}")
        if dependencias is None:
            faltantes = services.get("dependencias_pendentes", {}).get(
                tipo, []
            )
            raise RuntimeError(
                "composição do pipeline incompleta"
                + (f": {', '.join(faltantes)}" if faltantes else "")
            )

        run_id = os.environ.get("AGENT_RUN_ID") or uuid.uuid4().hex
        if args.receita:
            if not args.subcategoria:
                raise ValueError(
                    "--subcategoria é obrigatória para execução manual de receita"
                )
            from pipeline.gerar_receitas import gerar_receita

            pauta = {
                "tema": args.assunto,
                "topic_slug": args.assunto,
                "subcategoria": args.subcategoria,
                "tipo_conteudo": "receita",
                "origem": "manual",
            }
            resultado = gerar_receita(
                dependencias, pauta, fase=args.fase, run_id=run_id,
                dry_run=args.dry_run, publicar=args.target == "producao",
            )
        else:
            from pipeline.gerar_conteudo_educativo import gerar_dica

            resultado = gerar_dica(
                dependencias, fase=args.fase, run_id=run_id,
                publicar=args.target == "producao",
            )
        print(json.dumps(resultado.__dict__, ensure_ascii=False, default=str))
        estados_ok = {
            "generated", "sent", "published", "sem_pauta", "adiada_cadencia"
        }
        return 0 if resultado.estado in estados_ok else 1
    except Exception as exc:
        print(json.dumps({
            "estado": "erro",
            "tipo": tipo,
            "etapa": "composicao",
            "erro": type(exc).__name__,
            "motivo": str(exc),
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
