"""Fixtures da integração com o site. Valores ILUSTRATIVOS."""
import json

import httpx

from agents.analista import CatalogoMemoria
from agents.editor import RespostaReceita
from helpers_criacao import PAUTA_RECEITA, ficha_aprovada, receita_valida
from helpers_pesquisa import CATALOGO
from integration.adaptador_receita import montar_payload_receita
from integration.cliente_site import ClienteSite

COVER_GERAR = {"mode": "generate", "imagePrompt": "Brigadeiro de colher cremoso em tigela, vista de cima"}
COVER_STOCK = {"mode": "stock", "provider": "pexels", "sourceImageUrl": "https://images.pexels.com/photos/7.jpeg",
               "sourcePageUrl": "https://www.pexels.com/photo/7/", "author": "Maria", "license": "Pexels License",
               "attributionText": "Foto por Maria no Pexels"}
PAUTA = dict(PAUTA_RECEITA, topic_slug="brigadeiro-de-colher-cremoso", ocasiao=["festas"])


def conteudo_editor(**mudancas):
    """Saída do editor (já validada e normalizada), como o adaptador a recebe."""
    return RespostaReceita.model_validate(receita_valida(**mudancas)).model_dump()


def payload(fase=1, status="draft", run_id="run-1", cover=None, **kw):
    args = dict(conteudo=conteudo_editor(), pauta=PAUTA, ficha=ficha_aprovada(), cover=cover or COVER_GERAR, run_id=run_id,
                fase=fase, modelo={"provedor": "p", "modelo": "m", "familia": "f"}, prompt_version="base@1.0.0+receita@1.1.0",
                catalogo=CatalogoMemoria(CATALOGO), status=status)
    args.update(kw)
    conteudo = args.pop("conteudo")
    return montar_payload_receita(conteudo, **args)


class Site:
    """Transporte falso: grava requisições e responde em sequência (ou por função)."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.requisicoes = []

    def __call__(self, req: httpx.Request):
        self.requisicoes.append(req)
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(r, Exception):
            raise r
        return r

    def posts(self):
        return [r for r in self.requisicoes if r.method == "POST"]


def resp(status=201, corpo=None, **cab):
    return httpx.Response(status, json=corpo if corpo is not None else {}, headers=cab)


OK_201 = {"id": 123, "slug": "brigadeiro-de-colher-cremoso-com-chocolate", "status": "draft", "url": "https://site.test/receitas/x"}


def cliente(site, fase=1, **kw):
    esperas = []
    ids = iter(f"rid{i}" for i in range(1, 100))
    c = ClienteSite("https://site.test", token_draft="TOKEN-DRAFT-XYZ", token_publish="TOKEN-PUBLISH-XYZ", fase=fase,
                    cliente=httpx.Client(transport=httpx.MockTransport(site)), espera=esperas.append,
                    gerar_id=lambda: next(ids), **kw)
    c.esperas = esperas
    return c


def corpo(req):
    return json.loads(req.content.decode("utf-8"))
