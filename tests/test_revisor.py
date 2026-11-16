import json

import pytest

from agents.revisor import FamiliaNaoGarantida, revisar_conteudo
from helpers_criacao import GerarFalso, receita_valida, ficha_aprovada
from tests.test_editor import FICHA, RECEITA_VALIDA

RECEITA = receita_valida()
FICHA = ficha_aprovada()


def test_revisor_recusa_mesma_familia_do_gerador():
    gerador = GerarFalso([json.dumps({"aprovado": True, "problemas": []})], familia="familia-a")
    with pytest.raises(FamiliaNaoGarantida):
        revisar_conteudo(RECEITA, FICHA, "familia-a", gerar=gerador)


def test_revisor_aprova_sem_problemas():
    gerador = GerarFalso([json.dumps({"aprovado": True, "problemas": []})], familia="familia-b")
    resultado = revisar_conteudo(RECEITA, FICHA, "familia-a", gerar=gerador)
    assert resultado.aprovado is True
    assert resultado.problemas == []


def test_revisor_reprova_com_gravidade_alta_mesmo_se_aprovado_true():
    payload = {
        "aprovado": True,  # o próprio modelo erra; o código corrige
        "problemas": [
            {"campo": "modo_preparo", "descricao": "afirma teste pessoal", "gravidade": "alta"}
        ],
    }
    gerador = GerarFalso([json.dumps(payload)], familia="familia-b")
    resultado = revisar_conteudo(RECEITA, FICHA, "familia-a", gerar=gerador)
    assert resultado.aprovado is False
    assert resultado.problemas[0].gravidade == "alta"


def test_revisor_reprova_saida_mal_formada():
    gerador = GerarFalso(["não é json"], familia="familia-b")
    resultado = revisar_conteudo(RECEITA, FICHA, "familia-a", gerar=gerador)
    assert resultado.aprovado is False
    assert resultado.erro is not None
