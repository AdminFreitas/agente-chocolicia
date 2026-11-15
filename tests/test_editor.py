import json

from agents.editor import criar_receita
from tests.fakes_llm import GeradorFalso

PAUTA = {
    "tema": "Brigadeiro de colher cremoso",
    "categoria": "doces-e-sobremesas",
    "subcategoria": "brigadeiros-e-docinhos",
}

FICHA = {
    "ingrediente_base": "leite condensado",
    "ingredientes_consenso": [
        {"nome": "leite condensado", "quantidade_g": 395, "critico": True},
        {"nome": "chocolate em pó", "quantidade_g": 40, "critico": True},
    ],
    "tecnica_consenso": ["cozinhar mexendo sem parar"],
    "tempos": {"preparo_min": 10, "cozimento_min": 15},
    "diferencial_sugerido": None,
    "perguntas_comuns": [],
}

RECEITA_VALIDA = {
    "titulo": "Brigadeiro de colher cremoso com chocolate meio amargo",
    "descricao_curta": "Brigadeiro de colher macio e brilhante, com chocolate meio amargo e ponto fácil de acertar na panela.",
    "subcategoria": "brigadeiros-e-docinhos",
    "tempo_preparo_min": 10,
    "tempo_cozimento_min": 15,
    "rendimento_porcoes": 8,
    "ingredientes": [
        {
            "nome": "Brigadeiro",
            "itens": [
                {"nome": "leite condensado", "quantidade": "395", "unidade": "g"},
                {"nome": "chocolate em pó", "quantidade": "40", "unidade": "g"},
            ],
        }
    ],
    "modo_preparo": [
        {"titulo": "Cozinhar", "instrucao": "Leve ao fogo baixo e mexa sem parar até soltar do fundo da panela."},
        {"titulo": "Descansar", "instrucao": "Transfira para um recipiente e deixe amornar."},
        {"titulo": "Servir", "instrucao": "Sirva em copinhos ou taças."},
        {"titulo": "Finalizar", "instrucao": "Decore a gosto com chocolate granulado."},
    ],
    "termos_busca_imagem": ["brigadeiro bowl", "chocolate pudding spoon", "chocolate dessert"],
    "prompt_imagem": "Brigadeiro de colher cremoso em tigela de cerâmica, vista de cima.",
    "texto_alt_imagem": "Tigela com brigadeiro de colher cremoso e brilhante",
    "temas_relacionados": ["ponto do brigadeiro", "brigadeiro branco"],
    "alertas_internos": [],
}


def test_criar_receita_aprova_na_primeira_tentativa():
    gerador = GeradorFalso(respostas=[json.dumps(RECEITA_VALIDA)])
    resultado = criar_receita(
        ficha=FICHA, pauta=PAUTA, categorias_validas=["brigadeiros-e-docinhos"], gerador=gerador
    )
    assert resultado.aprovado is True
    assert resultado.receita is not None
    assert resultado.receita.titulo == RECEITA_VALIDA["titulo"]
    assert resultado.tentativas == 1
    assert len(gerador.chamadas) == 1


def test_criar_receita_json_invalido_depois_repara_e_aprova():
    gerador = GeradorFalso(respostas=["isto não é json", json.dumps(RECEITA_VALIDA)])
    resultado = criar_receita(
        ficha=FICHA, pauta=PAUTA, categorias_validas=["brigadeiros-e-docinhos"], gerador=gerador
    )
    assert resultado.aprovado is True
    assert resultado.tentativas == 2
    # a segunda chamada usou o prompt de reparo (motivos SCH-01 no conteúdo)
    segunda_chamada_usuario = gerador.chamadas[1][1][-1]["content"]
    assert "SCH-01" in segunda_chamada_usuario


def test_criar_receita_rejeita_apos_esgotar_reparos():
    invalida = {**RECEITA_VALIDA, "titulo": "oi"}  # menor que 5 chars não, mas vamos usar campo faltante
    del invalida["modo_preparo"]  # falta campo obrigatório -> sempre inválido
    gerador = GeradorFalso(respostas=[json.dumps(invalida)] * 3)
    resultado = criar_receita(
        ficha=FICHA, pauta=PAUTA, categorias_validas=["brigadeiros-e-docinhos"], gerador=gerador
    )
    assert resultado.aprovado is False
    assert resultado.rejection_code == "SCH-02"
    assert resultado.tentativas == 3
    assert len(gerador.chamadas) == 3


def test_modelo_nao_decide_campos_que_sao_do_sistema():
    """O contrato (ReceitaSaida) não tem dificuldade, dieta, status, slug etc.
    — docs/03 §6.2. Um campo extra enviado pelo modelo é simplesmente
    ignorado pelo Pydantic (model_config padrão), nunca persistido."""
    gerador = GeradorFalso(
        respostas=[json.dumps({**RECEITA_VALIDA, "dificuldade": "Difícil", "status": "published"})]
    )
    resultado = criar_receita(
        ficha=FICHA, pauta=PAUTA, categorias_validas=["brigadeiros-e-docinhos"], gerador=gerador
    )
    assert resultado.aprovado is True
    assert not hasattr(resultado.receita, "dificuldade")
    assert not hasattr(resultado.receita, "status")
