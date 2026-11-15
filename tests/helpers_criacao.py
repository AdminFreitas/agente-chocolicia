"""Fixtures compartilhadas para criação e integração de receitas."""

from __future__ import annotations

import copy
import json
from typing import Any

from services.llm_cliente import RespostaLLM


PAUTA_RECEITA = {
    "tema": "Brigadeiro de colher cremoso",
    "categoria": "doces-e-sobremesas",
    "subcategoria": "brigadeiros-e-docinhos",
    "topic_slug": "brigadeiro-de-colher-cremoso",
    "ocasiao": ["festas"],
}


def ficha_aprovada(**mudancas: Any) -> dict:
    ficha = {
        "status": "aprovada_para_criacao",
        "pauta": {"tema": PAUTA_RECEITA["tema"], "subcategoria": PAUTA_RECEITA["subcategoria"]},
        "fontes_consultadas": 3,
        "fontes_tecnicas": 0,
        "envolve_seguranca": False,
        "etiquetas_dieta": [],
        "tecnica_flags": [],
        "referencias_registro": [
            {"dominio": "panelinha.com.br", "url": "https://panelinha.com.br/x", "acessado_em": "2026-11-12"},
            {"dominio": "receitas.globo.com", "url": "https://receitas.globo.com/x", "acessado_em": "2026-11-12"},
            {"dominio": "tudogostoso.com.br", "url": "https://tudogostoso.com.br/x", "acessado_em": "2026-11-12"},
        ],
    }
    ficha.update(mudancas)
    return copy.deepcopy(ficha)


def receita_valida(**mudancas: Any) -> dict:
    receita = {
        "titulo": "Brigadeiro de colher cremoso",
        "descricao_curta": "Um brigadeiro cremoso, simples e feito para comer de colher.",
        "introducao": "",
        "subcategoria": "brigadeiros-e-docinhos",
        "tempo_preparo_min": 5,
        "tempo_cozimento_min": 15,
        "tempo_descanso_min": None,
        "rendimento_porcoes": 6,
        "rendimento_texto": "6 porções",
        "ingredientes": [
            {
                "nome": "leite condensado",
                "quantidade": 395,
                "unidade": "g",
                "observacao": None,
            },
            {
                "nome": "chocolate em pó",
                "quantidade": "42",
                "unidade": "g",
                "observacao": None,
            },
        ],
        "modo_preparo": [
            {"titulo": "Misture", "instrucao": "Coloque os ingredientes em uma panela e misture antes de aquecer."},
            {"titulo": "Cozinhe", "instrucao": "Cozinhe em fogo baixo, mexendo sempre, por cerca de 15 minutos."},
            {"titulo": "Desligue", "instrucao": "Desligue quando a mistura estiver cremosa e começar a soltar do fundo."},
            {"titulo": "Sirva", "instrucao": "Transfira para potes e sirva morno ou frio."},
        ],
        "dica_extra": "",
        "perguntas_frequentes": [],
        "tags": ["brigadeiro", "chocolate", "sobremesa"],
        "termos_busca_imagem": ["brigadeiro bowl", "chocolate dessert", "brigadeiro spoon"],
        "prompt_imagem": "Brigadeiro de colher cremoso em uma tigela, fotografia culinária",
        "texto_alt_imagem": "Brigadeiro de colher cremoso servido em uma tigela",
        "temas_relacionados": ["doces de festa", "sobremesas de chocolate"],
        "alertas_internos": [],
    }
    receita.update(mudancas)
    return copy.deepcopy(receita)


class GerarFalso:
    def __init__(self, respostas, *, familia="familia-a"):
        self.respostas = list(respostas)
        self.familia = familia
        self.chamadas = []

    def __call__(self, tarefa, prompt, *, familia_excluida=None):
        self.chamadas.append((tarefa, prompt, familia_excluida))
        if not self.respostas:
            raise RuntimeError("GerarFalso sem respostas restantes")
        resposta = self.respostas.pop(0)
        if isinstance(resposta, BaseException):
            raise resposta
        if isinstance(resposta, RespostaLLM):
            return resposta
        return RespostaLLM(str(resposta), "p", "m", self.familia)


def js(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False)
