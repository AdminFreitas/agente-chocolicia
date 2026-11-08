"""
services/image_providers/database.py — Registro e persistência de metadados de imagens.
Salva proveniência, fotógrafo, licença, URLs e status em tabela dedicada.
"""

from datetime import datetime
import os
import sqlite3
from typing import Any, Dict, Optional

# Caminho padrão do banco local do agente para persistência garantida
DB_SQLITE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "agente_digital.db")
)


def _init_sqlite_table(conn: sqlite3.Connection) -> None:
    """Cria a tabela imagens_banco caso ainda não exista."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imagens_banco (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            provider_image_id TEXT NOT NULL,
            original_page_url TEXT,
            original_image_url TEXT NOT NULL,
            stored_image_url TEXT,
            stored_path TEXT,
            photographer TEXT,
            license TEXT,
            license_url TEXT,
            attribution_text TEXT,
            search_query TEXT,
            width INTEGER,
            height INTEGER,
            downloaded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_status TEXT DEFAULT 'stored'
        );
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_imagens_banco_provider_id 
        ON imagens_banco(provider, provider_image_id);
    """)
    conn.commit()


def registrar_imagem(
    provider: str,
    provider_image_id: str,
    original_image_url: str,
    original_page_url: str,
    stored_image_url: Optional[str] = None,
    stored_path: Optional[str] = None,
    photographer: Optional[str] = None,
    license: Optional[str] = None,
    license_url: Optional[str] = None,
    attribution_text: Optional[str] = None,
    search_query: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    image_status: str = "stored",
) -> int:
    """
    Grava os metadados de uma imagem obtida e armazenada.
    Retorna o ID do registro gerado.
    """
    conn = sqlite3.connect(DB_SQLITE_PATH)
    try:
        _init_sqlite_table(conn)
        cursor = conn.cursor()
        agora = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO imagens_banco (
                provider, provider_image_id, original_page_url, original_image_url,
                stored_image_url, stored_path, photographer, license, license_url,
                attribution_text, search_query, width, height, downloaded_at, image_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            provider,
            provider_image_id,
            original_page_url,
            original_image_url,
            stored_image_url,
            stored_path,
            photographer,
            license,
            license_url,
            attribution_text,
            search_query,
            width,
            height,
            agora,
            image_status,
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def listar_imagens_registradas(limite: int = 20) -> list[Dict[str, Any]]:
    """Lista as últimas imagens armazenadas com metadados completos."""
    conn = sqlite3.connect(DB_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _init_sqlite_table(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM imagens_banco ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

