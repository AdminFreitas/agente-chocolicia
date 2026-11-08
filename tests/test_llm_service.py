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
