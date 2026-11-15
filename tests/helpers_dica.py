"""Fixtures das dicas. Valores ILUSTRATIVOS."""
import json

from agents.planejador import (
    AssuntoDica, AssuntosDicaMemoria, BloqueiosMemoria, ConteudoExistenteMemoria, CoberturaMock, FilaMemoria, HistoricoMemoria,
    ItemFila, Subcategoria, TaxonomiaMemoria,
)
from helpers_imagens import ProvedorFalso, VisaoFalsa, baixador, candidata
from helpers_integracao import OK_201, Site, cliente, resp
from pipeline.gerar_conteudo_educativo import DependenciasDica
from services.image_providers import ImageSelector, ImagensUsadasMemoria
from services.llm_cliente import RespostaLLM

TEMA = "Ganache talhou? Como recuperar"


def corpo_dica(n=200):
    palavras = ["Misture", "o", "creme", "morno", "aos", "poucos"] * 100
    return "## Resposta direta\n\n" + " ".join(palavras[: n - 3])  # o cabeçalho tem 3 palavras: o total é exatamente n


def dica_valida(**ch):
    d = {
        "titulo": "Ganache talhou? Como recuperar",
        "descricao_curta": "Veja por que a ganache talha e como recuperar o ponto cremoso com poucos passos simples.",
        "assunto": "preparo",
        "resposta_direta": "Junte um pouco de creme morno e mexa do centro para fora até a mistura voltar a ficar lisa.",
        "corpo": corpo_dica(),
        "tags": ["ganache", "chocolate", "dica de preparo"],
        "temas_relacionados": ["ponto da ganache", "trufa de chocolate"],
        "subcategoria": "doces-de-colher",
        "termos_busca_imagem": ["ganache bowl", "chocolate cream", "chocolate dessert"],
        "prompt_imagem": "Ganache de chocolate lisa e brilhante em uma tigela, vista de cima",
        "alertas_internos": [],
    }
    d.update(ch)
    return d


def ficha_dica(**ch):
    f = {"status": "aprovada_para_criacao", "pauta": {"tema": TEMA}, "fontes_consultadas": 3, "envolve_seguranca": False,
         "fontes_tecnicas": 0, "consenso": {"causa": "calor demais"}, "pontos_unicos": [],
         "referencias_registro": [{"dominio": "panelinha.com.br", "url": "https://panelinha.com.br/x", "acessado_em": "2026-11-12"}]}
    f.update(ch)
    return f


def seo_dica(**ch):
    d = {"titulo": "Ganache talhou? Veja como recuperar", "descricao_curta": "Entenda por que a ganache talha e recupere o ponto cremoso com poucos passos simples e seguros.",
         "palavra_chave_principal": "ganache talhou", "palavras_secundarias": ["recuperar ganache"],
         "texto_alt_imagem": "Ganache de chocolate lisa e brilhante em uma tigela", "tags": ["ganache", "chocolate", "preparo", "dica"],
         "temas_relacionados": ["ponto da ganache", "trufa de chocolate"]}
    d.update(ch)
    return d


def js(d):
    return json.dumps(d, ensure_ascii=False)


class Roteador:
    """LLM falso por tarefa. `respostas`: tarefa -> lista; `familias`: tarefa -> família."""

    def __init__(self, respostas=None, familias=None):
        base = {"criacao": [js(dica_valida())], "revisao": [js({"aprovado": True, "problemas": []})], "seo": [js(seo_dica())]}
        base.update(respostas or {})
        self.respostas = {k: list(v) for k, v in base.items()}
        self.familias = {"criacao": "familia-a", "reparo": "familia-a", "revisao": "familia-b", "seo": "familia-c"}
        self.familias.update(familias or {})
        self.chamadas = []

    def __call__(self, tarefa, prompt, *, familia_excluida=None):
        self.chamadas.append((tarefa, prompt, familia_excluida))
        fila = self.respostas[tarefa]
        texto = fila.pop(0) if len(fila) > 1 else fila[0]
        return RespostaLLM(texto, "p", "m", self.familias[tarefa])


class ValidadorOk:
    def __init__(self, ids=()):
        self.ids_cobertos = set(ids)
        self.chamadas = 0

    def validar(self, conteudo, contexto):
        self.chamadas += 1
        return []


def montar(*, itens=None, assuntos=None, site=None, fase=1, ficha=None, pesquisar="padrao", llm=None, validador=None,
           visao="ok", candidatas=None, completo=True, **kw):
    """Dependências prontas. `completo=True` fornece bloqueios e lookup (senão o planejador registra pendências)."""
    itens = itens if itens is not None else [ItemFila(TEMA, subcategoria="doces-de-colher", assunto="preparo")]
    assuntos = assuntos if assuntos is not None else [AssuntoDica("preparo", "low", True), AssuntoDica("ornamentacao", "low", True),
                                                      AssuntoDica("negocios", "medium", True), AssuntoDica("equipamentos-compra", "medium", True)]
    site = site or Site(resp(201, OK_201))
    f = ficha if ficha is not None else ficha_dica()
    usadas = ImagensUsadasMemoria()
    selector = ImageSelector([ProvedorFalso(padrao=candidatas if candidatas is not None else [candidata("1")])])
    deps = DependenciasDica(
        fila=FilaMemoria(itens),
        taxonomia=TaxonomiaMemoria([Subcategoria("doces-de-colher", "doces-e-sobremesas", "low", True)]),
        assuntos=AssuntosDicaMemoria(assuntos), cobertura=CoberturaMock(), historico=HistoricoMemoria(),
        cliente=cliente(site, fase=fase, **kw), pesquisar=(lambda pauta: f) if pesquisar == "padrao" else pesquisar,
        gerar=llm or Roteador(), validador=validador, visao=VisaoFalsa() if visao == "ok" else visao, selector=selector,
        usadas=usadas, baixar=baixador(),
        conteudo_existente=ConteudoExistenteMemoria() if completo else None, bloqueios=BloqueiosMemoria() if completo else None,
    )
    deps.site, deps.usadas_ref = site, usadas
    return deps
