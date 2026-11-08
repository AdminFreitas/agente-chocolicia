"""
Ponto de entrada para automação do agente.

Gera um artigo por execução e abre uma sessão curta do banco apenas
para ler os títulos recentes usados como contexto de sugestão de tema.
"""

import argparse
import random
import sys
from datetime import datetime

from config.database import SessionLocal
from agents import pesquisador
from repositories.artigo_repository import ArtigoRepository
from pipeline.gerar_artigos import gerar_e_processar_artigo


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Gera um artigo — para uso via cron."
    )
    parser.add_argument(
        "--artigo",
        action="store_true",
        help="Gera um artigo evergreen",
    )
    args = parser.parse_args()

    if not args.artigo:
        parser.error("Use --artigo.")

    ok_artigo = True

    if args.artigo:
        ok_artigo = rodar_artigo()

    sys.exit(0 if ok_artigo else 1)