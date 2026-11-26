"""CLI segura do agente Chocolícia, sem leitura de `.env` no import."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

# O runtime lê as configurações durante a importação de alguns módulos. Carregue
# o arquivo uma única vez, antes de importar qualquer adaptador do runtime, sem
# sobrescrever variáveis já fornecidas pelo ambiente de execução.
try:
    from dotenv import load_dotenv
except ImportError:  # mantém o CLI utilizável sem tornar dotenv obrigatório
    def load_dotenv(dotenv_path, *, override=False):
        caminho = Path(dotenv_path)
        if not caminho.is_file():
            return False
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, valor = linha.split("=", 1)
            nome = nome.strip()
            valor = valor.strip().strip('"').strip("'")
            if nome and (override or nome not in os.environ):
                os.environ[nome] = valor
        return True

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from runtime_adapters.cli_contract import build_services


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
        raise ValueError("O provedor LLM não retornou um tema de receita utilizável")
    return tema


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Executa o agente Chocolícia")
    dry_run_env = os.environ.get("DRY_RUN", "true").strip().lower()
    if dry_run_env not in {"true", "false"}:
        p.error("DRY_RUN deve ser true ou false")
    target_env = os.environ.get("TARGET", "preview").strip().lower()
    if target_env not in {"preview", "production"}:
        p.error("TARGET deve ser preview ou production")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--receita", action="store_true")
    grupo.add_argument("--dica", action="store_true")
    p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=dry_run_env == "true",
    )
    p.add_argument(
        "--target",
        choices=("preview", "production"),
        default=target_env,
    )
    p.add_argument("--assunto", default=os.environ.get("ASSUNTO", "automatico"))
    p.add_argument("--subcategoria")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    # O portão AGENT_ENABLED só bloqueia execuções automáticas (em CI).
    # Comandos manuais no terminal local rodam sempre.
    is_ci = os.environ.get("CI", "false").lower() == "true"
    if is_ci and os.environ.get("AGENT_ENABLED", "false").lower() != "true":
        print(json.dumps(
            {"estado": "desabilitado", "motivo": "AGENT_ENABLED=false em ambiente CI"},
            ensure_ascii=False,
        ))
        return 0
    if is_ci and args.dica and os.environ.get("AGENT_DICAS_ENABLED", "false").lower() != "true":
        print(json.dumps({
            "estado": "desabilitado",
            "motivo": "AGENT_DICAS_ENABLED=false em ambiente CI",
        }, ensure_ascii=False))
        return 2
    fase_env = os.environ.get("AGENT_PHASE", "0").strip()
    try:
        fase = int(fase_env)
    except ValueError:
        print(json.dumps({
            "estado": "erro",
            "tipo": "configuracao",
            "motivo": "AGENT_PHASE deve ser um inteiro entre 0 e 3",
        }, ensure_ascii=False))
        return 2
    if fase not in (0, 1, 2, 3):
        print(json.dumps({
            "estado": "erro",
            "tipo": "configuracao",
            "motivo": "AGENT_PHASE deve estar entre 0 e 3",
        }, ensure_ascii=False))
        return 2
    if args.target == "production":
        if fase < 1:
            print(json.dumps({
                "estado": "bloqueado",
                "motivo": "publicação exige AGENT_PHASE >= 1",
            }, ensure_ascii=False))
            return 2
        if not args.dry_run and os.environ.get("AGENT_PUBLISHING_ENABLED", "false").strip().lower() != "true":
            print(json.dumps({
                "estado": "bloqueado",
                "motivo": "AGENT_PUBLISHING_ENABLED não está habilitado",
            }, ensure_ascii=False))
            return 2
    tipo = "receita" if args.receita else "dica"
    run_id = os.environ.get("AGENT_RUN_ID") or uuid.uuid4().hex
    try:
        services = build_services(
            dry_run=args.dry_run,
            target=args.target,
            tipo=tipo,
            assunto=args.assunto,
            subcategoria=args.subcategoria,
            run_id=run_id,
        )
        fase = services["runtime"].settings.site_phase
        dependencias = services.get(f"dependencias_{tipo}")
        if dependencias is None:
            faltantes = services.get("dependencias_pendentes", {}).get(
                tipo, []
            )
            raise RuntimeError(
                "composição do pipeline incompleta"
                + (f": {', '.join(faltantes)}" if faltantes else "")
            )

        if args.receita:
            classificacao = services["catalogo"].selecionar_subcategoria(
                fase, slug=args.subcategoria
            )
            from agents.planejador import gerar_topic_slug
            from pipeline.gerar_receitas import gerar_receita

            store = services["runtime"].store
            if args.assunto == "automatico":
                if args.target == "production" and store is None:
                    raise ValueError("DATABASE_URL_AGENTE é necessário para bloquear duplicatas")
                tema = _gerar_tema_receita(
                    services["gerar"], store, classificacao["category_name"]
                )
            else:
                tema = args.assunto.strip()
            topic_slug = gerar_topic_slug(tema)
            pauta = {
                "tema": tema,
                "topic_slug": topic_slug,
                "categoria": classificacao["category_name"],
                "subcategoria": classificacao.get("subcategory_slug"),
                "categoria_legada": classificacao["category_name"],
                "tipo_conteudo": "receita",
                "origem": "manual",
            }
            if not args.dry_run:
                if store is None:
                    raise ValueError("DATABASE_URL_AGENTE é necessário para bloquear duplicatas")
                store.start_run(run_id, "recipe", args.target, pauta["topic_slug"])
                from runtime_adapters.persistence import DuplicateContent

                try:
                    store.claim_topic("recipe", topic_slug, run_id)
                except DuplicateContent:
                    store.update_run(
                        run_id, "rejected", "pauta",
                        {"rejection_code": "DUP-HIST", "motivo": "topic_slug já reservado"},
                    )
                    print(json.dumps({
                        "estado": "rejected",
                        "etapa": "pauta",
                        "codigo": "DUP-HIST",
                        "motivos": ["topic_slug já reservado"],
                    }, ensure_ascii=False))
                    return 1
                if services["catalogo"].existe(topic_slug, tema):
                    store.update_run(
                        run_id, "rejected", "pauta",
                        {"rejection_code": "SIM-04", "motivo": "conteúdo já existe no site"},
                    )
                    print(json.dumps({
                        "estado": "rejected",
                        "etapa": "pauta",
                        "codigo": "SIM-04",
                        "motivos": ["conteúdo já existe no site"],
                    }, ensure_ascii=False))
                    return 1
            resultado = gerar_receita(
                dependencias, pauta, fase=fase, run_id=run_id,
                dry_run=args.dry_run,
                publicar=args.target == "production" and not args.dry_run,
                idempotency_key=topic_slug,
            )
            if not args.dry_run:
                envio = resultado.envio
                details = {"codigo": resultado.codigo}
                if envio is not None:
                    details.update({
                        "remote_id": envio.id,
                        "slug": envio.slug,
                        "status": envio.status,
                        "url": envio.url,
                    })
                store.update_run(run_id, resultado.estado, resultado.etapa, details)
                if envio is not None and envio.status in {"draft", "published"}:
                    store.record_publication(
                        run_id, str(envio.id), envio.slug or "", envio.status or "",
                        envio.url,
                    )
        else:
            from pipeline.gerar_conteudo_educativo import gerar_dica

            store = services["runtime"].store
            if not args.dry_run and store is not None:
                store.start_run(run_id, "tip", args.target)
            publicadas_na_semana = None
            if fase >= 1:
                publicadas_na_semana = services["catalogo"].tip_coverage()
            resultado = gerar_dica(
                dependencias, fase=fase, run_id=run_id,
                publicar=args.target == "production" and not args.dry_run,
                geracao_imagem_permitida=(
                    os.environ.get("AGENT_IMAGE_GENERATION_ENABLED", "false").strip().lower() == "true"
                ),
                publicadas_na_semana=publicadas_na_semana,
                validators_version="dica-code-v1",
            )
            if not args.dry_run and store is not None:
                details = {"codigo": resultado.codigo}
                if resultado.envio is not None:
                    details.update({
                        "remote_id": resultado.envio.id,
                        "slug": resultado.envio.slug,
                        "status": resultado.envio.status,
                        "url": resultado.envio.url,
                    })
                store.update_run(run_id, resultado.estado, resultado.etapa, details)
                if resultado.envio is not None and resultado.envio.status in {"draft", "published"}:
                    store.record_publication(
                        run_id, str(resultado.envio.id), resultado.envio.slug or "",
                        resultado.envio.status or "", resultado.envio.url,
                    )
        saida = dict(resultado.__dict__)
        saida["pauta"] = pauta if args.receita else saida.get("pauta")
        if getattr(resultado, "envio", None) is not None:
            envio = resultado.envio
            saida["publicacao"] = {
                "id": envio.id,
                "slug": envio.slug,
                "status": envio.status,
                "url": envio.url,
                "http_status": envio.http_status,
            }
        print(json.dumps(saida, ensure_ascii=False, default=str))
        estados_ok = {
            "generated", "sent", "published", "sem_pauta", "adiada_cadencia"
        }
        return 0 if resultado.estado in estados_ok else 1
    except Exception as exc:
        message = str(exc)
        for name in (
            "SITE_TOKEN_DRAFT", "SITE_TOKEN_DRAFT_PREVIEW", "SITE_TOKEN_PUBLISH",
            "RECIPES_AGENT_TOKEN", "GEMINI_API_KEY", "GROQ_API_KEY",
            "OPENROUTER_API_KEY", "BRAVE_SEARCH_API_KEY", "PEXELS_API_KEY",
            "PIXABAY_API_KEY", "AGENT_DATABASE_URL", "DATABASE_URL_AGENTE",
        ):
            secret = os.environ.get(name, "")
            if secret:
                message = message.replace(secret, "[redacted]")
        print(json.dumps({
            "estado": "erro",
            "tipo": tipo,
            "etapa": "composicao",
            "erro": type(exc).__name__,
            "motivo": message,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
