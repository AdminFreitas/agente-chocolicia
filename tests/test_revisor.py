import json

import pytest

from agents.editor import ReceitaSaida
from agents.revisor import FamiliaModeloInvalidaError, revisar
from tests.fakes_llm import GeradorFalso
from tests.test_editor import FICHA, RECEITA_VALIDA

RECEITA = ReceitaSaida.model_validate(RECEITA_VALIDA)


def test_revisor_recusa_mesma_familia_do_gerador():
    gerador = GeradorFalso(respostas=[json.dumps({"aprovado": True, "problemas": []})])
    with pytest.raises(FamiliaModeloInvalidaError):
        revisar(
            receita=RECEITA,
            ficha=FICHA,
            gerador=gerador,
            familia_gerador="openai-gpt",
            familia_revisor="openai-gpt",
        )


def test_revisor_aprova_sem_problemas():
    gerador = GeradorFalso(respostas=[json.dumps({"aprovado": True, "problemas": []})])
    resultado = revisar(
        receita=RECEITA,
        ficha=FICHA,
        gerador=gerador,
        familia_gerador="openai-gpt",
        familia_revisor="anthropic-claude",
    )
    assert resultado.aprovado is True
    assert resultado.problemas == []


def test_revisor_reprova_com_gravidade_alta_mesmo_se_aprovado_true():
    payload = {
        "aprovado": True,  # o próprio modelo erra; o código corrige
        "problemas": [
            {"campo": "modo_preparo", "descricao": "afirma teste pessoal", "gravidade": "alta"}
        ],
    }
    gerador = GeradorFalso(respostas=[json.dumps(payload)])
    resultado = revisar(
        receita=RECEITA,
        ficha=FICHA,
        gerador=gerador,
        familia_gerador="openai-gpt",
        familia_revisor="anthropic-claude",
    )
    assert resultado.aprovado is False
    assert resultado.problemas[0].gravidade == "alta"


def test_revisor_reprova_saida_mal_formada():
    gerador = GeradorFalso(respostas=["não é json"])
    resultado = revisar(
        receita=RECEITA,
        ficha=FICHA,
        gerador=gerador,
        familia_gerador="openai-gpt",
        familia_revisor="anthropic-claude",
    )
    assert resultado.aprovado is False
    assert resultado.erro is not None
