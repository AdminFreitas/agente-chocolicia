"""Põe a raiz do projeto no sys.path e mantém os testes de rede real fora da execução padrão."""
import os
import socket
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


@pytest.fixture(autouse=True)
def bloquear_rede_externa(monkeypatch):
    """Impede chamadas externas durante testes; permite apenas loopback."""
    connect_original = socket.socket.connect
    create_connection_original = socket.create_connection

    def permitido(endereco) -> bool:
        host = endereco[0] if isinstance(endereco, tuple) and endereco else endereco
        return host in {"localhost", "127.0.0.1", "::1"}

    def connect_guard(self, endereco):
        if permitido(endereco):
            return connect_original(self, endereco)
        raise RuntimeError(f"rede externa bloqueada pelo teste: {endereco!r}")

    def create_connection_guard(address, *args, **kwargs):
        if permitido(address):
            return create_connection_original(address, *args, **kwargs)
        raise RuntimeError(f"rede externa bloqueada pelo teste: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", connect_guard)
    monkeypatch.setattr(socket, "create_connection", create_connection_guard)
