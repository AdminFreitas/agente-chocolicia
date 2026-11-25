import pytest

import services.llm_service as llm


def test_modelo_nao_aprovado(monkeypatch):
    monkeypatch.setattr(llm, "_modelos_aprovados", lambda tarefa: [])

    with pytest.raises(llm.ModeloNaoAprovado):
        llm.gerar_texto("criacao", "teste")


def test_provedor_simulado_e_contadores(monkeypatch):
    item = {"provedor": "gemini", "modelo": "modelo-teste", "familia": "teste"}
    monkeypatch.setattr(llm, "_modelos_aprovados", lambda tarefa: [item])
    monkeypatch.setattr(llm, "_chave_provedor", lambda provedor: "chave-teste")
    monkeypatch.setattr(llm, "_chamar_provedor", lambda modelo, prompt: "resposta simulada")
    llm.CONTADORES.update(requisicoes=0, tokens=0)

    resultado = llm.gerar_texto("criacao", "prompt teste")

    assert resultado == "resposta simulada"
    assert llm.CONTADORES["requisicoes"] == 1
    assert llm.CONTADORES["tokens"] > 0


class ProvedorHttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_fallback_transitorio_informa_provedor_que_respondeu(monkeypatch):
    aprovados = [
        {"provedor": "gemini", "modelo": "gemini-primary"},
        {"provedor": "groq", "modelo": "groq-fallback"},
    ]
    monkeypatch.setattr(llm, "_modelos_aprovados", lambda tarefa: aprovados)
    monkeypatch.setattr(llm, "_ordenar_modelos_por_fallback", lambda modelos: modelos)
    monkeypatch.setattr(llm, "_chave_provedor", lambda provedor: "chave-teste")
    monkeypatch.setattr(
        llm,
        "_chamar_provedor",
        lambda item, prompt: (_ for _ in ()).throw(ProvedorHttpError(503))
        if item["provedor"] == "gemini"
        else "resposta do fallback",
    )
    resultado = llm.gerar_texto_com_metadados("criacao", "prompt")

    assert resultado["texto"] == "resposta do fallback"
    assert resultado["provedor"] == "groq"
    assert resultado["modelo"] == "groq-fallback"


def test_erro_de_autenticacao_tenta_proximo_provedor(monkeypatch):
    aprovados = [
        {"provedor": "gemini", "modelo": "gemini-primary"},
        {"provedor": "groq", "modelo": "groq-fallback"},
    ]
    monkeypatch.setattr(llm, "_modelos_aprovados", lambda tarefa: aprovados)
    monkeypatch.setattr(llm, "_ordenar_modelos_por_fallback", lambda modelos: modelos)
    monkeypatch.setattr(llm, "_chave_provedor", lambda provedor: "chave-teste")

    def chamar(item, prompt):
        if item["provedor"] == "gemini":
            raise ProvedorHttpError(401)
        return "resposta do Groq"

    monkeypatch.setattr(llm, "_chamar_provedor", chamar)
    resultado = llm.gerar_texto_com_metadados("criacao", "prompt")

    assert resultado["texto"] == "resposta do Groq"
    assert resultado["provedor"] == "groq"


def test_chave_ausente_do_primario_usa_proximo_provedor(monkeypatch):
    aprovados = [
        {"provedor": "gemini", "modelo": "gemini-primary"},
        {"provedor": "groq", "modelo": "groq-fallback"},
    ]
    monkeypatch.setattr(llm, "_modelos_aprovados", lambda tarefa: aprovados)
    monkeypatch.setattr(llm, "_ordenar_modelos_por_fallback", lambda modelos: modelos)
    monkeypatch.setattr(
        llm, "_chave_provedor", lambda provedor: "" if provedor == "gemini" else "groq-key"
    )
    monkeypatch.setattr(llm, "_chamar_provedor", lambda item, prompt: "resposta do Groq")

    resultado = llm.gerar_texto_com_metadados("criacao", "prompt")

    assert resultado["texto"] == "resposta do Groq"
    assert resultado["provedor"] == "groq"
