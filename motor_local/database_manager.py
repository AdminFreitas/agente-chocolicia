"""Persistência do motor local no banco do agente.

O site Chocolícia continua dono da tabela `recipes`. Este módulo grava em
`agent_recipe_drafts` (ver db/schema_rascunhos_receita.sql). O padrão é
`draft` quando a geração passou e `failed` quando não passou. `published`
só é gravado depois que a API do site confirma a publicação.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from psycopg2.extras import Json

ConnectFn = Callable[[str], Any]


class RecipeDatabaseManager:
    def __init__(self, conn_url: str | None = None, conectar: ConnectFn | None = None):
        self.conn_url = conn_url or os.getenv("DATABASE_URL_AGENTE") or os.getenv("DATABASE_URL")
        self._conectar = conectar

    def save_recipe_to_db(
        self,
        recipe_result: dict,
        *,
        topic: str | None = None,
        persistir_como: str | None = None,
    ) -> int:
        status = recipe_result.get("status")
        if status not in {"success", "failed"}:
            raise ValueError("status da geração deve ser 'success' ou 'failed'")
        if persistir_como is not None and persistir_como not in {"draft", "published", "failed"}:
            raise ValueError("status persistido deve ser draft, published ou failed")
        if not self.conn_url and self._conectar is None:
            raise RuntimeError("DATABASE_URL_AGENTE não configurada")

        db_status = persistir_como or ("draft" if status == "success" else "failed")
        if db_status == "published" and status != "success":
            raise ValueError("só uma geração bem-sucedida pode ser marcada como published")
        conn = self._abrir()
        try:
            cursor = conn.cursor()
            try:
                if db_status in {"draft", "published"}:
                    data = recipe_result["data"]
                    cursor.execute(
                        """
                        INSERT INTO agent_recipe_drafts (
                            title, slug, description, prep_time, cook_time, servings,
                            difficulty, ingredients, steps, tips, meta_description,
                            schema_org, status, topic, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        RETURNING id;
                        """,
                        (
                            data["title"],
                            data["slug"],
                            data["description"],
                            data["prep_time"],
                            data["cook_time"],
                            data["servings"],
                            data["difficulty"],
                            Json(data["ingredients"]),
                            Json(data["steps"]),
                            Json(data.get("tips") or []),
                            data["meta_description"],
                            Json(data["schema_org"]),
                            db_status,
                            topic,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO agent_recipe_drafts (status, error_log, topic, created_at)
                        VALUES (%s, %s, %s, NOW())
                        RETURNING id;
                        """,
                        (db_status, recipe_result.get("error"), topic),
                    )
                recipe_id = cursor.fetchone()[0]
            finally:
                cursor.close()
            conn.commit()
            return int(recipe_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _abrir(self):
        if self._conectar is not None:
            return self._conectar(self.conn_url or "")
        import psycopg2

        return psycopg2.connect(self.conn_url)
