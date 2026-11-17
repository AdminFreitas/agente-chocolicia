"""Gera, valida e publica uma receita sem aprovação manual.

O caminho padrão envia `status: published` para POST /api/recipes.
`--somente-rascunho` grava só no banco do agente. `--dry-run` valida o
contrato e não chama a rede.

No servidor onde o Ollama fica ligado, um agendador dispara o comando.
Exemplo de crontab (08h, 14h e 20h, horário de Brasília = UTC-3):

    0 11,17,23 * * * /usr/bin/python3 -m motor_local.main_agent --subcategoria bolos "tema do dia" >> /var/log/chocolicia_bot.log 2>&1
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from pydantic import ValidationError

from integration.cliente_site import ConfiguracaoInvalida, ContratoInvalido, ErroSite
from motor_local.database_manager import RecipeDatabaseManager
from motor_local.publicador import AutonomousPublisher
from motor_local.recipe_processor import ChocoliciaRecipeAgent


def run_recipe_pipeline(
    topic: str,
    *,
    agent: ChocoliciaRecipeAgent | None = None,
    db_manager: RecipeDatabaseManager | None = None,
    model_name: str | None = None,
) -> dict:
    gerador = agent or ChocoliciaRecipeAgent(model_name=model_name)
    resultado = gerador.generate_recipe(topic)
    banco = db_manager or RecipeDatabaseManager()
    resultado["recipe_id"] = banco.save_recipe_to_db(resultado, topic=topic)
    resultado["published"] = False
    return resultado


def run_fully_autonomous_pipeline(
    topic: str,
    *,
    agent: ChocoliciaRecipeAgent | None = None,
    db_manager: RecipeDatabaseManager | None = None,
    publisher: AutonomousPublisher | None = None,
    model_name: str | None = None,
    subcategoria: str | None = None,
    dry_run: bool = False,
) -> dict:
    gerador = agent or ChocoliciaRecipeAgent(model_name=model_name)
    resultado = gerador.generate_recipe(topic)
    banco = db_manager or RecipeDatabaseManager()
    if resultado["status"] != "success":
        resultado["recipe_id"] = banco.save_recipe_to_db(resultado, topic=topic)
        resultado["published"] = False
        return resultado

    dados = resultado["data"]
    if not dados.get("ingredients") or not dados.get("steps"):
        return _registrar_falha(banco, topic, "receita incompleta: faltam ingredientes ou passos")

    publicador = publisher or AutonomousPublisher(subcategoria=subcategoria, dry_run=dry_run)
    run_id = uuid.uuid4().hex
    try:
        resposta = publicador.publish_recipe(dados, run_id=run_id, model_name=gerador.model_name)
    except (ValueError, ValidationError, ContratoInvalido, ConfiguracaoInvalida, ErroSite, RuntimeError) as exc:
        falha = _registrar_falha(banco, topic, f"{type(exc).__name__}: {exc}")
        return falha

    if resposta.situacao == "duplicada":
        return _registrar_falha(banco, topic, "esta pauta já existe no site em outra execução")

    publicado = resposta.situacao in {"criado", "repetido", "confirmado_apos_409"} and not publicador.dry_run
    resultado["recipe_id"] = banco.save_recipe_to_db(
        resultado,
        topic=topic,
        persistir_como="published" if publicado else "draft",
    )
    resultado["published"] = publicado
    resultado["site"] = {
        "situacao": resposta.situacao,
        "slug": resposta.slug,
        "url": resposta.url,
        "id": resposta.id,
    }
    return resultado


def _registrar_falha(banco: RecipeDatabaseManager, topic: str, erro: str) -> dict:
    falha = {"status": "failed", "error": erro}
    falha["recipe_id"] = banco.save_recipe_to_db(falha, topic=topic)
    falha["published"] = False
    return falha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera uma receita no Ollama, valida e publica no site.")
    parser.add_argument("topic", nargs="?", default="Torta holandesa clássica com cobertura de ganache")
    parser.add_argument("--model", default=None, help="Modelo Ollama. Padrão: OLLAMA_MODEL ou mistral:7b-instruct.")
    parser.add_argument("--subcategoria", default=os.getenv("MOTOR_SUBCATEGORIA"), help="Slug da subcategoria no site.")
    parser.add_argument("--dry-run", action="store_true", help="Valida o contrato e não envia ao site.")
    parser.add_argument("--somente-rascunho", action="store_true", help="Grava só no banco do agente, sem chamar a API.")
    args = parser.parse_args(argv)

    print(f"[AUTÔNOMO] Iniciando ciclo para: {args.topic}")
    try:
        if args.somente_rascunho:
            resultado = run_recipe_pipeline(args.topic, model_name=args.model)
        else:
            resultado = run_fully_autonomous_pipeline(
                args.topic,
                model_name=args.model,
                subcategoria=args.subcategoria,
                dry_run=args.dry_run,
            )
    except Exception as exc:
        print(f"[FALHA] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if resultado["status"] != "success":
        print(f"[FALHA NA GERAÇÃO] {resultado.get('error')} (ID local: {resultado.get('recipe_id')})")
        return 1
    if args.somente_rascunho:
        print(f"[RASCUNHO] Salvo no banco do agente (ID: {resultado['recipe_id']}).")
        return 0
    if resultado.get("published"):
        print(f"[AUTOMAÇÃO] Receita publicada: {resultado['data']['title']}")
        print(f"[CICLO CONCLUÍDO] Publicação registrada (ID local: {resultado['recipe_id']}).")
        return 0
    if args.dry_run:
        print(f"[DRY-RUN] Contrato válido para: {resultado['data']['title']} (ID local: {resultado['recipe_id']}).")
        return 0
    print(f"[FALHA] A receita não foi publicada (ID local: {resultado.get('recipe_id')}).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
