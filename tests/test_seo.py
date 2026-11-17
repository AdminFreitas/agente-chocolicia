import json

from agents.editor import ReceitaSaida
from agents.seo import ajustar_seo
from helpers_criacao import GerarFalso, receita_valida
from tests.test_editor import RECEITA_VALIDA

RECEITA = ReceitaSaida.model_validate(receita_valida())

SEO_VALIDA = {
    "titulo": "Brigadeiro de colher cremoso de chocolate meio amargo",
    "descricao_curta": "Brigadeiro de colher macio, brilhante, com chocolate meio amargo e ponto fácil de acertar direto na panela, sem gelatina.",
    "palavra_chave_principal": "brigadeiro de colher",
    "palavras_secundarias": ["brigadeiro cremoso", "doce de colher"],
    "texto_alt_imagem": "Tigela com brigadeiro de colher cremoso e brilhante",
    "tags": ["chocolate", "brigadeiro", "doce de colher", "festa"],
    "temas_relacionados": ["ponto do brigadeiro", "brigadeiro branco"],
}


def test_ajustar_seo_aprova_com_saida_valida():
    gerador = GerarFalso([json.dumps(SEO_VALIDA)])
    resultado = ajustar_seo(receita=RECEITA, tags_existentes=["chocolate"], gerador=gerador)
    assert resultado.aprovado is True
    assert resultado.saida.palavra_chave_principal == "brigadeiro de colher"


def test_ajustar_seo_ignora_campo_fora_do_permitido():
    """Mesmo que o modelo tente devolver 'ingredientes' ou 'modo_preparo',
    o módulo de SEO nunca repassa isso para o resultado (docs/05 §13)."""
    payload = {**SEO_VALIDA, "ingredientes": [{"nome": "açúcar"}], "modo_preparo": ["faça diferente"]}
    gerador = GerarFalso([json.dumps(payload)])
    resultado = ajustar_seo(receita=RECEITA, tags_existentes=[], gerador=gerador)
    assert resultado.aprovado is True
    assert not hasattr(resultado.saida, "ingredientes")
    assert not hasattr(resultado.saida, "modo_preparo")


def test_ajustar_seo_reprova_saida_fora_dos_limites():
    invalida = {**SEO_VALIDA, "titulo": "curto"}  # menor que 35 caracteres
    gerador = GerarFalso([json.dumps(invalida)])
    resultado = ajustar_seo(receita=RECEITA, tags_existentes=[], gerador=gerador)
    assert resultado.aprovado is False
    assert resultado.erro is not None


def test_ajustar_seo_reprova_descricao_curta_com_menos_de_120_caracteres():
    invalida = {**SEO_VALIDA, "descricao_curta": "Descrição curta demais."}
    gerador = GerarFalso([json.dumps(invalida)])
    resultado = ajustar_seo(receita=RECEITA, tags_existentes=[], gerador=gerador)
    assert resultado.aprovado is False
    assert resultado.erro is not None and "descricao_curta" in resultado.erro
