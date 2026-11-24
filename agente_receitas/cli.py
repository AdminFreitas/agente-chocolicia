"""CLI de receitas do agente Chocolícia (modo legacy, publicação direta em produção).

Escopo: somente `--receita`. O fluxo de dicas continua em `rodar_agente.py` (main).
Em produção este comando exige SITE_CONTRACT=legacy explícito, porque o site atual
só expõe `POST /api/recipes` (ver agente_receitas/README-LEGACY.md).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

from agente_receitas.runtime_adapters.cli_contract import build_services

_SEGREDOS = (
    "RECIPES_AGENT_TOKEN", "SITE_TOKEN_DRAFT", "SITE_TOKEN_PUBLISH",
    "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "BRAVE_SEARCH_API_KEY",
    "PEXELS_API_KEY", "PIXABAY_API_KEY", "AGENT_DATABASE_URL", "DATABASE_URL_AGENTE",
)


def _gerar_tema_receita(gerar, store, categoria: str) -> str:
    recentes = store.recent_topic_slugs("recipe") if store is not None else []
    prompt = (
        "Proponha um único tema específico e não redundante para uma receita de confeitaria. "
        f"A categoria aceita pelo site é exatamente {categoria!r}. "
        "Responda somente com o tema em português, sem título, aspas ou explicações. "
        "Evite estes topic_slug já usados: " + ", ".join(recentes)
    )
    tema = gerar("creation", prompt).texto.strip().splitlines()[0].strip().strip('"')
    if not 5 <= len(tema) <= 120 or tema.casefold() == "automatico":
        raise ValueError("o modelo não retornou um tema de receita utilizável")
    return tema


def _saida(obj: dict, codigo: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, default=str))
    return codigo


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Gera e publica uma receita (modo legacy)")
    dry_env = os.environ.get("DRY_RUN", "true").strip().lower()
    if dry_env not in {"true", "false"}:
        p.error("DRY_RUN deve ser true ou false")
    alvo_env = os.environ.get("TARGET", "preview").strip().lower()
    if alvo_env not in {"preview", "production"}:
        p.error("TARGET deve ser preview ou production")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=dry_env == "true")
    p.add_argument("--target", choices=("preview", "production"), default=alvo_env)
    p.add_argument("--assunto", default=os.environ.get("ASSUNTO", "automatico"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    is_ci = os.environ.get("CI", "false").lower() == "true"
    if is_ci and os.environ.get("AGENT_ENABLED", "false").lower() != "true":
        return _saida({"estado": "desabilitado", "motivo": "AGENT_ENABLED=false em ambiente CI"}, 0)
    try:
        fase = int(os.environ.get("AGENT_PHASE", "0").strip())
    except ValueError:
        return _saida({"estado": "erro", "tipo": "configuracao", "motivo": "AGENT_PHASE deve ser inteiro"}, 2)
    if args.target == "production":
        if os.environ.get("SITE_CONTRACT", "").strip().lower() != "legacy":
            return _saida({"estado": "bloqueado", "motivo": "produção exige SITE_CONTRACT=legacy explícito"}, 2)
        if fase < 1:
            return _saida({"estado": "bloqueado", "motivo": "publicação exige AGENT_PHASE >= 1"}, 2)
        if args.dry_run:
            return _saida({"estado": "bloqueado", "motivo": "production exige DRY_RUN=false"}, 2)
        if os.environ.get("AGENT_PUBLISHING_ENABLED", "false").strip().lower() != "true":
            return _saida({"estado": "bloqueado", "motivo": "AGENT_PUBLISHING_ENABLED não está habilitado"}, 2)

    run_id = os.environ.get("AGENT_RUN_ID") or uuid.uuid4().hex
    try:
        services = build_services(
            dry_run=args.dry_run, target=args.target, tipo="receita",
            assunto=args.assunto, run_id=run_id,
        )
        runtime = services["runtime"]
        fase = runtime.settings.site_phase
        legacy = runtime.settings.site_contract == "legacy"
        deps = services["dependencias_receita"]

        from agente_receitas.agents.planejador import gerar_topic_slug
        from agente_receitas.pipeline.gerar_receitas import gerar_receita

        if legacy:
            classificacao = services["catalogo"].selecionar_categoria_legada()
            subcategoria = None  # o site valida subcategoria contra a categoria; legacy não envia
        else:
            classificacao = services["catalogo"].selecionar_subcategoria(fase)
            subcategoria = classificacao.get("subcategory_slug")
        store = runtime.store
        if not args.dry_run and store is None:
            raise ValueError("AGENT_DATABASE_URL é necessário para bloquear duplicatas")
        if args.assunto == "automatico":
            tema = _gerar_tema_receita(services["gerar"], store, classificacao["category_name"])
        else:
            tema = args.assunto.strip()
        topic_slug = gerar_topic_slug(tema)
        pauta = {
            "tema": tema, "topic_slug": topic_slug,
            "categoria": classificacao["category_name"], "subcategoria": subcategoria,
            "categoria_legada": classificacao["category_name"],
            "tipo_conteudo": "receita", "origem": "manual",
        }
        if not args.dry_run:
            from agente_receitas.runtime_adapters.persistence import DuplicateContent

            store.start_run(run_id, "recipe", args.target, topic_slug)
            try:
                store.claim_topic("recipe", topic_slug, run_id)
            except DuplicateContent:
                store.update_run(run_id, "rejected", "pauta",
                                 {"rejection_code": "DUP-HIST", "motivo": "topic_slug já reservado"})
                return _saida({"estado": "rejected", "etapa": "pauta", "codigo": "DUP-HIST",
                               "motivos": ["topic_slug já reservado"]}, 1)
            if not legacy and services["catalogo"].existe(topic_slug, tema):
                store.update_run(run_id, "rejected", "pauta",
                                 {"rejection_code": "SIM-04", "motivo": "conteúdo já existe no site"})
                return _saida({"estado": "rejected", "etapa": "pauta", "codigo": "SIM-04",
                               "motivos": ["conteúdo já existe no site"]}, 1)
        resultado = gerar_receita(
            deps, pauta, fase=fase, run_id=run_id, dry_run=args.dry_run,
            publicar=args.target == "production" and not args.dry_run,
            idempotency_key=topic_slug,
        )
        envio = resultado.envio
        if not args.dry_run:
            detalhes = {"codigo": resultado.codigo}
            if envio is not None:
                detalhes.update({"remote_id": envio.id, "slug": envio.slug,
                                 "status": envio.status, "url": envio.url})
            store.update_run(run_id, resultado.estado, resultado.etapa, detalhes)
            if envio is not None and envio.status in {"draft", "published"}:
                store.record_publication(run_id, str(envio.id), envio.slug or "",
                                         envio.status or "", envio.url)
        saida = dict(resultado.__dict__)
        saida["pauta"] = pauta
        if envio is not None:
            saida["publicacao"] = {"id": envio.id, "slug": envio.slug, "status": envio.status,
                                   "url": envio.url, "http_status": envio.http_status}
        ok = {"generated", "sent", "published", "sem_pauta", "adiada_cadencia"}
        return _saida(saida, 0 if resultado.estado in ok else 1)
    except Exception as exc:  # noqa: BLE001 - a saída JSON é o contrato do workflow
        mensagem = str(exc)
        for nome in _SEGREDOS:
            valor = os.environ.get(nome, "")
            if valor:
                mensagem = mensagem.replace(valor, "[redacted]")
        return _saida({"estado": "erro", "tipo": "receita", "etapa": "composicao",
                       "erro": type(exc).__name__, "motivo": mensagem}, 2)


if __name__ == "__main__":
    sys.exit(main())
