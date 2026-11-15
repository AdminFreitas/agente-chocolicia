import pytest

from services.prompt_loader import MontadorPrompt, PromptInvalidoError


def test_monta_prompt_com_base_e_modulo_e_marca_dados_como_dado():
    montador = MontadorPrompt()
    saida = montador.montar(
        tipo="receita",
        pauta={"tema": "Brigadeiro de colher", "subcategoria": "brigadeiros-e-docinhos"},
        ficha={"ingredientes_consenso": [{"nome": "leite condensado"}]},
        categorias_validas=["brigadeiros-e-docinhos", "trufas-e-bombons"],
        contrato_saida="{...}",
    )
    assert "Chef IA" in saida.sistema  # veio de base.md
    assert "Dica extra" in saida.sistema  # veio de receita.md
    assert "<dados_pesquisa>" in saida.usuario
    assert "leite condensado" in saida.usuario
    assert saida.versao_base == "1.0.0"
    assert saida.versao_modulo == "1.1.0"


def test_mensagens_tem_sistema_e_usuario():
    montador = MontadorPrompt()
    saida = montador.montar(
        tipo="receita",
        pauta={},
        ficha={},
        categorias_validas=[],
        contrato_saida="{}",
    )
    mensagens = saida.como_mensagens()
    assert [m["role"] for m in mensagens] == ["system", "user"]


def test_prompt_inexistente_lanca_erro_claro():
    montador = MontadorPrompt()
    with pytest.raises(PromptInvalidoError):
        montador.montar(
            tipo="tipo-que-nao-existe",
            pauta={},
            ficha={},
            categorias_validas=[],
            contrato_saida="{}",
        )


def test_montar_reparo_preenche_placeholders():
    montador = MontadorPrompt()
    reparo = montador.montar_reparo(
        motivos=["SCH-02: titulo: muito curto"],
        resposta_anterior='{"titulo": "x"}',
    )
    assert "SCH-02: titulo: muito curto" in reparo.texto
    assert '{"titulo": "x"}' in reparo.texto
    assert "{lista de erros do validador}" not in reparo.texto
    assert "{JSON anterior}" not in reparo.texto
