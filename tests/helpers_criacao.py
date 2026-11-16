"""Fixtures da criação. Valores ILUSTRATIVOS, não são dados reais de fonte alguma."""
import copy
import json

from helpers_pesquisa import PAUTA, analista_ok, fichas_aprovaveis
from services.llm_cliente import RespostaLLM

PAUTA_RECEITA = dict(copy.deepcopy(PAUTA), tipo_conteudo="receita")


def ficha_aprovada():
    f = analista_ok().consolidar(copy.deepcopy(PAUTA), fichas_aprovaveis())
    assert f["status"] == "aprovada_para_criacao"
    return f


def receita_valida(**mudancas):
    d = {
        "titulo": "Brigadeiro de colher cremoso com chocolate",
        "descricao_curta": "Brigadeiro de colher macio e brilhante, feito com leite condensado e chocolate em pó, com ponto fácil.",
        "introducao": "O brigadeiro de colher combina leite condensado e chocolate em uma textura cremosa.",
        "subcategoria": "brigadeiros-e-docinhos",
        "tempo_preparo_min": 10, "tempo_cozimento_min": 15, "tempo_descanso_min": None,
        "rendimento_porcoes": 8, "rendimento_texto": "8 porções",
        "ingredientes": [{"nome": "Brigadeiro", "itens": [
            {"nome": "leite condensado", "quantidade": 395, "unidade": "g", "observacao": "1 lata"},
            {"nome": "chocolate em pó", "quantidade": "42", "unidade": "g"},
            {"nome": "manteiga", "quantidade": "15", "unidade": "g"}]}],
        "modo_preparo": [
            {"titulo": "Misturar", "instrucao": "Misture o leite condensado, o chocolate e a manteiga em uma panela."},
            {"titulo": "Cozinhar", "instrucao": "Leve ao fogo baixo e mexa sem parar até soltar do fundo, por cerca de 15 minutos."},
            {"titulo": "Esfriar", "instrucao": "Transfira para um recipiente e deixe amornar."},
            {"titulo": "Servir", "instrucao": "Sirva em copinhos."}],
        "dica_extra": "", "perguntas_frequentes": [], "tags": ["chocolate", "brigadeiro", "festa", "doce de colher"],
        "termos_busca_imagem": ["brigadeiro bowl", "chocolate pudding spoon", "chocolate dessert"],
        "prompt_imagem": "Brigadeiro de colher cremoso em uma tigela de cerâmica, vista de cima, luz suave",
        "texto_alt_imagem": "Tigela com brigadeiro de colher cremoso e brilhante",
        "temas_relacionados": ["ponto do brigadeiro", "brigadeiro branco"], "alertas_internos": [],
    }
    d.update(copy.deepcopy(mudancas))
    return d


def js(d):
    return json.dumps(d, ensure_ascii=False)


class GerarFalso:
    """
    Dublê de llm compatível com GerarFn. Registra (tarefa, prompt, familia_excluida).

    Cada item da fila `respostas` pode ser:
      - str            -> vira RespostaLLM (use texto inválido para simular JSON inválido,
                          e um segundo item válido para simular o reparo);
      - RespostaLLM    -> devolvida como está;
      - Exception      -> instância ou classe: levantada (falha simulada);
      - BaseException que não seja Exception (KeyboardInterrupt, SystemExit...) -> também
        levantada, e propaga sem ser engolida: o dublê não captura nada.
    """

    def __init__(self, respostas, familia="familia-a", provedor="p", modelo="m"):
        self.respostas = list(respostas)
        self.chamadas = []
        self.familia, self.provedor, self.modelo = familia, provedor, modelo

    def __call__(self, tarefa, prompt, *, familia_excluida=None):
        self.chamadas.append((tarefa, prompt, familia_excluida))
        if not self.respostas:
            raise AssertionError(
                f"GerarFalso sem respostas restantes (chamada nº {len(self.chamadas)}, tarefa={tarefa!r})"
            )
        item = self.respostas.pop(0)
        if isinstance(item, BaseException) or (isinstance(item, type) and issubclass(item, BaseException)):
            raise item
        if isinstance(item, RespostaLLM):
            return item
        return RespostaLLM(item, self.provedor, self.modelo, self.familia)
