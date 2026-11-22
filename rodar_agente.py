"""
Ponto de entrada para automação do agente.

Gera um artigo por execução e abre uma sessão curta do banco apenas
para ler os títulos recentes usados como contexto de sugestão de tema.
"""

import argparse
import os
import random
import sys
from datetime import datetime



PUBLICAR_IMEDIATAMENTE = True

CATEGORIAS_ARTIGOS = [
    "Inteligência Artificial",
    "Programação",
    "Banco de Dados",
    "Cibersegurança",
    "Cloud e DevOps",
    "Desenvolvimento Web",
    "Engenharia de Software",
    "Hardware",
    "Open Source",
    "Carreira",
]


def _log(mensagem: str) -> None:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {mensagem}", flush=True)


def _buscar_temas_recentes(limite: int = 30) -> list[str]:
    """
    Busca os títulos mais recentes no banco para servir de contexto ao
    sugerir_tema() (evita repetir assunto). Protegido por try/except
    porque a assinatura exata de ArtigoRepository.listar_todos() ainda
    não foi confirmada — se ela não aceitar 'limite', ou qualquer outra
    coisa falhar aqui, a geração do artigo não deve travar por causa
    disso, só perde o contexto de "não repita esses temas".
    """
    from config.database import SessionLocal
    from repositories.artigo_repository import ArtigoRepository

    db = SessionLocal()
    try:
        artigos = ArtigoRepository(db).listar_todos(limite=limite)
        return [a.titulo for a in artigos]
    except TypeError as e:
        _log(
            f"AVISO: listar_todos() não aceitou 'limite' ({e}) — "
            "seguindo sem temas recentes"
        )
        return []
    except Exception as e:
        _log(
            f"AVISO: falha ao buscar temas recentes ({e}) — "
            "seguindo sem temas recentes"
        )
        return []
    finally:
        db.close()


def rodar_artigo(publicar: bool | None = None) -> bool:
    """
    Gera um artigo evergreen. Retorna True em sucesso, False em falha
    real — nunca lança exceção, quem chama decide o que fazer com o
    resultado (ex.: exit code pro cron/GitHub Actions perceber falha).
    """
    from agents import pesquisador
    from pipeline.gerar_artigos import gerar_e_processar_artigo

    publicar_imediatamente = (
        PUBLICAR_IMEDIATAMENTE if publicar is None else publicar
    )

    categoria = random.choice(CATEGORIAS_ARTIGOS)
    temas_recentes = _buscar_temas_recentes(limite=30)

    try:
        tema = pesquisador.sugerir_tema(
            categoria,
            temas_recentes=temas_recentes,
        )
    except Exception as e:
        _log(f"FALHA ao sugerir tema: {e}")
        return False

    _log(f"Tema sugerido ({categoria}): {tema}")

    try:
        resultado = gerar_e_processar_artigo(
            tema,
            categoria,
            publicar_imediatamente=publicar_imediatamente,
        )
        _log(f"Artigo OK: {resultado}")

        return True

    except Exception as e:
        _log(f"FALHA ao gerar artigo: {e}")
        return False


def rodar_dica(assunto: str | None = "automatico", target: str = "preview", dry_run: bool = False) -> bool:
    """Gera uma dica e a envia ao site (POST /api/articles). True em sucesso, False em falha."""
    from pipeline.gerar_dica import gerar_dica

    try:
        resultado = gerar_dica(assunto, target=target, dry_run=dry_run)
    except Exception as e:
        _log(f"FALHA ao gerar dica: {type(e).__name__}: {e}")
        return False
    slug = resultado["payload"]["slug"]
    _log(f"Dica OK ({'dry-run, não enviada' if not resultado['enviado'] else 'enviada ao site'}): {slug}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera conteúdo — para uso via cron.")
    parser.add_argument("--artigo", action="store_true", help="Gera um artigo evergreen")
    parser.add_argument("--dica", action="store_true", help="Gera uma dica e envia ao site")
    parser.add_argument("--assunto", default="automatico", help="Slug do tópico da dica")
    parser.add_argument("--target", default=os.getenv("TARGET", "preview"), choices=["preview", "producao"])
    parser.add_argument("--dry-run", action="store_true", help="Gera e valida, sem enviar ao site")
    args = parser.parse_args(argv)

    if not (args.artigo or args.dica):
        parser.error("Use --artigo e/ou --dica.")

    ok = True
    if args.artigo:
        ok = rodar_artigo() and ok
    if args.dica:
        ok = rodar_dica(args.assunto, args.target, args.dry_run) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
