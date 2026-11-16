"""CLI segura do agente Chocolícia, sem leitura de `.env` no import."""
from __future__ import annotations

import argparse
import json
import os
import sys

from pipeline.gerar_receitas import executar_modo_teste


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Executa o agente Chocolícia")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--receita", action="store_true")
    grupo.add_argument("--dica", action="store_true")
    grupo.add_argument("--artigo", action="store_true", help="legado; removido na refatoração")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--target", choices=("preview", "producao"), default="preview")
    p.add_argument("--contrato", choices=("v1", "site-atual"), default="v1")
    p.add_argument("--fase", type=int, choices=(0, 1, 2, 3), default=0)
    p.add_argument("--assunto", default="automatico")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.artigo:
        print("FALHA: --artigo foi removido na refatoração; use --receita no prompt 3")
        return 1
    if os.environ.get("AGENT_ENABLED", "false").lower() != "true":
        print(json.dumps({"estado": "desabilitado", "motivo": "AGENT_ENABLED=false"}, ensure_ascii=False))
        return 0
    resultado = executar_modo_teste(
        "receita" if args.receita else "dica", target=args.target, fase=args.fase,
    )
    print(json.dumps({**resultado.__dict__, "contrato": args.contrato, "assunto": args.assunto}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
