"""
linkedin_share_repository.py — Acesso ao banco de dados para linkedin_shares

Grava e consulta o rastreamento de publicações de artigos no LinkedIn,
seguindo o mesmo padrão de acesso (SQLAlchemy Session + text()) usado em
artigo_repository.py.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text


class LinkedInShareRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_pendentes(self, limite: int = 2):
        """Artigos publicados no blog que ainda não têm registro em
        linkedin_shares (nunca foram enviados ao LinkedIn)."""

        return self.db.execute(
            text("""
                SELECT
                    a.id,
                    a.titulo,
                    a.slug,
                    a.resumo,
                    a.imagem_url
                FROM artigos a
                LEFT JOIN linkedin_shares ls
                    ON ls.artigo_id = a.id
                WHERE a.status = 'publicado'
                  AND ls.artigo_id IS NULL
                ORDER BY a.data_publicacao DESC
                LIMIT :limite
            """),
            {"limite": limite},
        ).fetchall()

    def marcar_pendente(self, artigo_id: int) -> None:
        """Reserva a linha antes de tentar publicar."""

        self.db.execute(
            text("""
                INSERT INTO linkedin_shares (artigo_id, status)
                VALUES (:artigo_id, 'pendente')
                ON CONFLICT (artigo_id) DO NOTHING
            """),
            {"artigo_id": artigo_id},
        )
        self.db.commit()

    def marcar_publicado(self, artigo_id: int, post_id: str) -> None:
        self.db.execute(
            text("""
                UPDATE linkedin_shares
                SET status = 'publicado',
                    post_id = :post_id,
                    publicado_em = NOW(),
                    atualizado_em = NOW()
                WHERE artigo_id = :artigo_id
            """),
            {
                "post_id": post_id,
                "artigo_id": artigo_id,
            },
        )
        self.db.commit()

    def marcar_erro(self, artigo_id: int, mensagem: str) -> None:
        self.db.execute(
            text("""
                UPDATE linkedin_shares
                SET status = 'erro',
                    tentativas = tentativas + 1,
                    mensagem_erro = :mensagem,
                    atualizado_em = NOW()
                WHERE artigo_id = :artigo_id
            """),
            {
                "mensagem": mensagem,
                "artigo_id": artigo_id,
            },
        )
        self.db.commit()
