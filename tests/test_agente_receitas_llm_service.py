from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from threading import Lock

import pytest

import agente_receitas.services.llm_service as llm


class FakeGeminiClient:
    def __init__(self, prompt_calls, lock, fail=False):
        self.prompt_calls = prompt_calls
        self.lock = lock
        self.fail = fail
        self.closed = False
        self.entered = False
        self.models = self
        self.observed_open = False

    def __enter__(self):
        assert not self.closed
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def generate_content(self, *, model, contents):
        assert self.entered
        assert not self.closed
        self.observed_open = True
        with self.lock:
            self.prompt_calls.append((model, contents, self))
        if self.fail:
            raise RuntimeError("erro controlado")
        return SimpleNamespace(text=f"resposta:{contents}")


@pytest.fixture
def fake_clients(monkeypatch):
    created = []
    calls = []
    lock = Lock()
    fail_next = {"value": False}

    def factory():
        client = FakeGeminiClient(calls, lock, fail=fail_next["value"])
        created.append(client)
        return client

    monkeypatch.setattr(llm, "_novo_cliente_gemini", factory)
    return created, calls, fail_next


def test_cliente_fica_aberto_durante_a_requisicao_e_fecha_depois(fake_clients):
    created, calls, _ = fake_clients

    resposta = llm._chamar_gemini("prompt", "gemini-test")

    assert resposta == "resposta:prompt"
    assert len(created) == 1
    assert created[0].observed_open is True
    assert created[0].closed is True
    assert calls[0][:2] == ("gemini-test", "prompt")


def test_excecao_fecha_o_cliente(fake_clients):
    created, _, fail_next = fake_clients
    fail_next["value"] = True

    with pytest.raises(RuntimeError, match="erro controlado"):
        llm._chamar_gemini("prompt", "gemini-test")

    assert len(created) == 1
    assert created[0].closed is True


def test_duas_chamadas_sequenciais_nao_reutilizam_cliente_fechado(fake_clients):
    created, _, _ = fake_clients

    assert llm._chamar_gemini("um", "gemini-test") == "resposta:um"
    assert llm._chamar_gemini("dois", "gemini-test") == "resposta:dois"

    assert len(created) == 2
    assert all(client.closed for client in created)
    assert created[0] is not created[1]


def test_regressao_gerar_texto_com_metadados_cria_novo_cliente(fake_clients, monkeypatch):
    created, _, _ = fake_clients
    item = {"provedor": "gemini", "modelo": "gemini-test", "familia": "google-gemini"}
    monkeypatch.setattr(llm, "_modelos_aprovados", lambda tarefa: [item])
    monkeypatch.setattr(llm, "_chave_provedor", lambda provedor: "configured")

    first = llm.gerar_texto_com_metadados("criacao", "primeiro")
    second = llm.gerar_texto_com_metadados("criacao", "segundo")

    assert first["texto"] == "resposta:primeiro"
    assert second["texto"] == "resposta:segundo"
    assert len(created) == 2
    assert all(client.closed for client in created)


def test_execucoes_concorrentes_usam_clientes_independentes(fake_clients):
    created, _, _ = fake_clients

    with ThreadPoolExecutor(max_workers=4) as executor:
        respostas = list(executor.map(
            lambda indice: llm._chamar_gemini(f"prompt-{indice}", "gemini-test"),
            range(4),
        ))

    assert respostas == [f"resposta:prompt-{indice}" for indice in range(4)]
    assert len(created) == 4
    assert len({id(client) for client in created}) == 4
    assert all(client.closed for client in created)
