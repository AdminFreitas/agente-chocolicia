"""Hardening tests for the current API-only agent architecture."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_has_no_direct_site_database_setup():
    assert not (ROOT / "config" / "database.py").exists()
    assert not (ROOT / "scripts" / "setup_db.py").exists()
    assert importlib.util.find_spec("config.database") is None


def test_active_entrypoints_do_not_import_site_database():
    import rodar_conteudo  # noqa: F401
    import pipeline.gerar_dica  # noqa: F401

    assert "config.database" not in sys.modules
