"""Põe a raiz do projeto no sys.path e mantém os testes de rede real fora da execução padrão."""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
for p in (RAIZ, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def pytest_configure(config):
    config.addinivalue_line("markers", "real: usa a rede e provedores externos; só roda com RUN_REAL_IMAGE_TESTS=1")


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_REAL_IMAGE_TESTS") == "1":
        return
    pular = pytest.mark.skip(reason="usa rede real; defina RUN_REAL_IMAGE_TESTS=1 para executar")
    for item in items:
        if "real" in item.keywords:
            item.add_marker(pular)
