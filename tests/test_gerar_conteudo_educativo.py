import json

import httpx
import pytest

from agents.planejador import AssuntoDica, ItemFila
from helpers_dica import Roteador, TEMA, ValidadorOk, corpo_dica, dica_valida, ficha_dica, js, montar, seo_dica
from helpers_imagens import VisaoFalsa, candidata
from helpers_integracao import OK_201, Site, corpo, resp
from integration import cliente_site as CS
from pipeline import gerar_conteudo_educativo as G
from pipeline.gerar_conteudo_educativo import gerar_dica
from agents.seo import ResultadoSEO


def rodar(deps, fase=1, **kw):
    args = dict(fase=fase, run_id="run-1", publicadas_na_semana=0)
    args.update(kw)
    return gerar_dica(deps, **args)


def publicavel(**kw):
    kw.setdefault("validador", ValidadorOk({"HON-07", "HON-08"}))
    return montar(**kw)


# ---- caminho feliz --------------------------------------------------------------------------

def test_fase_0_envia_rascunho_validado_e_registra_a_imagem():
    d = montar(fase=0)
    r = gerar_dica(d, fase=0, run_id="run-1")
    assert (r.estado, r.etapa, r.status_enviado) == ("sent", "envio", "draft") and r.envio.situacao == "criado"
    post = d.site.posts()[0]
    assert post.url.path == "/api/tips" and post.headers["authorization"] == "Bearer TOKEN-DRAFT-XYZ"
    b = corpo(post)
    assert b["type"] == "dica" and b["tipTopic"] == "preparo" and b["status"] == "draft"
    assert b["title"] == "Ganache talhou? Veja como recuperar" and b["coverImageAlt"] == seo_dica()["texto_alt_imagem"]  # título e alt do SEO
    assert b["cover"]["mode"] == "stock" and b["generationMeta"]["topic_slug"] == "ganache-talhou-como-recuperar" and b["generationMeta"]["phase"] == 0
    assert r.pendencias == []
    assert d.usadas_ref.usada_url(b["cover"]["sourceImageUrl"])  # só depois do sucesso do envio
    assert r.pauta["assunto"] == "preparo" and r.criacao.status == "aprovado" and r.revisao.aprovado and r.seo.aplicado


def test_dry_run_nao_envia_nem_registra_imagem():
    d = montar(fase=0, dry_run=True)
    r = gerar_dica(d, fase=0, run_id="run-1")
    assert (r.estado, r.etapa, r.envio.situacao) == ("generated", "dry_run", "dry_run") and d.site.requisicoes == []
    assert r.payload["tipTopic"] == "preparo" and not d.usadas_ref.usada_url(r.payload["cover"]["sourceImageUrl"])


def test_publica_somente_sem_nenhuma_pendencia():
    d = publicavel()
    r = rodar(d, publicar=True)
    assert r.estado == "sent" and r.status_enviado == "published" and r.pendencias == []
    assert d.site.posts()[0].headers["authorization"] == "Bearer TOKEN-PUBLISH-XYZ"
    assert r.criacao.status == "aprovado" and corpo(d.site.posts()[0])["status"] == "published"


@pytest.mark.parametrize("mudanca", [
    dict(publicar=False),                                   # não pediu
    dict(publicadas_na_semana=None),                        # cadência não verificada
])
def test_publicar_exige_pedido_e_cadencia_verificada(mudanca):
    d = publicavel()
    r = rodar(d, **{"publicar": True, **mudanca})
    assert r.estado == "sent" and r.status_enviado == "draft"


@pytest.mark.parametrize("kw", [dict(validador=None), dict(completo=False), dict(visao=None)])
def test_qualquer_pendencia_deixa_em_rascunho(kw):
    d = publicavel(**kw) if "validador" not in kw else montar(**kw)
    r = rodar(d, publicar=True)
    if kw.get("validador", "configured") is None:
        assert r.estado == "rejected" and r.etapa == "validacao" and d.site.requisicoes == []
        return
    assert r.estado == "sent" and r.status_enviado == "draft" and r.pendencias


def test_fase_0_nunca_publica():
    d = publicavel(fase=0)
    r = gerar_dica(d, fase=0, run_id="r", publicar=True)
    assert r.status_enviado == "draft"


def test_revisor_dispensado_deixa_rascunho_e_pendente():
    d = publicavel()
    r = rodar(d, publicar=True, revisor_obrigatorio=False)
    assert r.status_enviado == "draft" and r.revisao is None and any("revisão por IA ignorada" in p for p in r.pendencias)
    assert "revisao" not in [c[0] for c in d.gerar.chamadas]


# ---- assuntos com exigência de HON-07/08 ------------------------------------------------------------------

@pytest.mark.parametrize("assunto,exigido,cobre,esperado", [
    ("negocios", "HON-07", {"HON-08"}, "draft"), ("negocios", "HON-07", {"HON-07"}, "published"),
    ("equipamentos-compra", "HON-08", set(), "draft"), ("equipamentos-compra", "HON-08", {"HON-08"}, "published"),
    ("preparo", None, set(), "published"),
])
def test_hon_07_e_08_pendentes_forcam_rascunho(assunto, exigido, cobre, esperado):
    llm = Roteador({"criacao": [js(dica_valida(assunto=assunto))]})
    d = montar(fase=2, itens=[ItemFila(TEMA, subcategoria="doces-de-colher", assunto=assunto)], llm=llm, validador=ValidadorOk(cobre))
    r = rodar(d, fase=2, publicar=True)
    assert r.estado == "sent" and r.status_enviado == esperado
    if esperado == "draft":
        assert f"PENDENTE: validators {exigido} (assunto {assunto})" in r.pendencias
    assert G.EXIGENCIAS_POR_ASSUNTO == {"equipamentos-compra": "HON-08", "negocios": "HON-07"}


# ---- pauta, cadência e pesquisa ------------------------------------------------------------------------

def test_sem_pauta_e_assunto_fora_da_fase():
    assert rodar(montar(itens=[])).estado == "sem_pauta"
    r = rodar(montar(itens=[ItemFila("t", assunto="negocios")]), fase=1)
    assert r.estado == "sem_pauta" and r.motivos == ["TAX-02: t"]


def test_cadencia_semanal_adia_antes_de_reservar():
    d = montar()
    r = rodar(d, publicadas_na_semana=2)
    assert (r.estado, r.codigo) == ("adiada_cadencia", "CADENCIA") and not d.historico.ja_existe("tip", "ganache-talhou-como-recuperar")
    assert rodar(montar(), publicadas_na_semana=1).estado == "sent"
    assert rodar(montar(fase=0), fase=0, publicadas_na_semana=99).estado == "sent"  # artigos só a partir da Fase 1


def test_pesquisa_pendente_ou_com_erro():
    r = rodar(montar(pesquisar=None))
    assert (r.estado, r.etapa, r.codigo) == ("error", "pesquisa", "PESQUISA-PENDENTE") and "PENDENTE" in r.motivos[0]
    def quebra(p): raise TimeoutError("x")
    r = rodar(montar(pesquisar=quebra))
    assert (r.estado, r.codigo, r.motivos) == ("error", "PESQUISA-ERRO", ["TimeoutError"])


@pytest.mark.parametrize("ficha,codigo", [
    (ficha_dica(fontes_consultadas=1), "GATE-DICA-01"),
    (ficha_dica(envolve_seguranca=True, fontes_tecnicas=0), "GATE-DICA-02"),
    (ficha_dica(status="rejeitada", motivos=["GATE-01: poucas fontes"]), "PESQUISA-GATE"),
])
def test_gate_da_pesquisa_de_dica(ficha, codigo):
    d = montar(ficha=ficha)
    r = rodar(d)
    assert (r.estado, r.etapa, r.codigo) == ("rejected", "pesquisa", codigo) and d.site.requisicoes == []
    assert G.verificar_minimos_dica(ficha_dica(envolve_seguranca=True, fontes_tecnicas=1)) == []


# ---- criação, revisão, SEO e imagem -----------------------------------------------------------------------

def test_criacao_rejeitada_depois_de_2_reparos():
    llm = Roteador({"criacao": ["x"], "reparo": ["y", "z"]})
    d = montar(llm=llm)
    r = rodar(d)
    assert (r.estado, r.etapa, r.codigo) == ("rejected", "criacao", "SCH-01") and r.criacao.tentativas == 3 and d.site.requisicoes == []


def test_erro_do_llm_aborta_sem_enviar():
    class Quebrado:
        def __call__(self, t, p, *, familia_excluida=None): raise RuntimeError("modelo não aprovado")
    d = montar(llm=Quebrado())
    r = rodar(d)
    assert (r.estado, r.etapa, r.codigo, r.motivos) == ("error", "criacao", "CRIACAO-ERRO", ["RuntimeError"]) and d.site.requisicoes == []


def test_revisor_reprova_ou_nao_garante_familia():
    ruim = js({"aprovado": True, "problemas": [{"campo": "corpo", "descricao": "afirmação sem apoio", "gravidade": "alta"}]})
    r = rodar(montar(llm=Roteador({"revisao": [ruim]})))
    assert (r.estado, r.etapa, r.codigo) == ("rejected", "revisao", "REV") and "alta: afirmação sem apoio" in r.motivos
    r = rodar(montar(llm=Roteador(familias={"revisao": ""})))
    assert (r.estado, r.codigo) == ("error", "REV-FAMILIA")
    r = rodar(montar(llm=Roteador(familias={"revisao": "familia-a"})))
    assert (r.estado, r.codigo) == ("error", "REV-FAMILIA")


def test_seo_obrigatorio_porque_ele_escreve_o_alt():
    for resposta in ("lixo", js(seo_dica(titulo="Ganache pronta em 99 minutos"))):
        d = montar(llm=Roteador({"seo": [resposta]}))
        r = rodar(d)
        assert (r.estado, r.etapa, r.codigo) == ("rejected", "seo", "IMG-08") and d.site.requisicoes == []


def test_validador_roda_de_novo_depois_do_seo():
    class V(ValidadorOk):
        def validar(self, c, ctx):
            self.chamadas += 1
            return [__import__("agents.editor", fromlist=["Falha"]).Falha("HON-03", "promessa", campo="titulo")] if "texto_alt_imagem" in c else []
    v = V({"HON-07", "HON-08"})
    r = rodar(montar(validador=v), publicar=True)
    assert (r.estado, r.etapa, r.codigo) == ("rejected", "seo", "HON-03") and v.chamadas == 2


def test_sem_visao_cai_em_generate_como_rascunho():
    r = rodar(montar(visao=None))
    assert r.estado == "sent" and r.status_enviado == "draft" and r.imagem.status == "generate"
    assert any("IMG-04" in p for p in r.pendencias) and r.payload["cover"] == {"mode": "generate", "imagePrompt": dica_valida()["prompt_imagem"]}


def test_sem_imagem_e_sem_teto_de_ia_rejeita():
    d = montar(candidatas=[])
    r = rodar(d, geracao_imagem_permitida=False)
    assert (r.estado, r.etapa, r.codigo) == ("rejected", "imagem", "IMG-07") and d.site.requisicoes == []


def test_imagem_so_vira_usada_depois_do_envio():
    d = montar(site=Site(resp(422, {"error": {"code": "image_host_not_allowed", "message": "m"}})))
    r = rodar(d)
    assert (r.estado, r.etapa, r.codigo) == ("error", "envio", "image_host_not_allowed")
    assert not d.usadas_ref.usada_url(r.payload["cover"]["sourceImageUrl"])


# ---- envio -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("site,estado,codigo", [
    (Site(resp(429, {"error": {"code": "daily_cap_reached", "message": "m"}})), "error", "daily_cap_reached"),
    (Site(resp(403, {"error": {"code": "publishing_disabled", "message": "m"}})), "error", "publishing_disabled"),
    (Site(resp(401, {"error": {"code": "unauthorized", "message": "m"}})), "error", "unauthorized"),
    (Site(resp(400, {"error": "Receita inválida."})), "error", "legacy_http_400"),
])
def test_erros_do_site_viram_erro_com_o_codigo(site, estado, codigo):
    r = rodar(montar(site=site))
    assert (r.estado, r.etapa, r.codigo) == (estado, "envio", codigo) and r.envio is None


def test_409_duplicada_e_confirmada():
    s = Site(resp(409, {"error": {"code": "topic_exists", "message": "m"}}), resp(200, {"items": [{"id": 1, "slug": "x", "generation_meta": {"run_id": "outra"}}]}))
    r = rodar(montar(site=s))
    assert (r.estado, r.codigo) == ("rejected", "DUPLICADA") and len(s.posts()) == 1
    s2 = Site(resp(409, {}), resp(200, {"items": [{"id": 1, "slug": "x", "status": "draft", "generation_meta": {"run_id": "run-1"}}]}))
    d2 = montar(site=s2)
    r2 = rodar(d2)
    assert r2.estado == "sent" and r2.envio.situacao == "confirmado_apos_409" and d2.usadas_ref.usada_url(r2.payload["cover"]["sourceImageUrl"])


def test_tecnica_e_materia_continuam_pendentes():
    from agents import planejador
    with pytest.raises(NotImplementedError):
        planejador.escolher_pauta(None, None, None, None, tipo_conteudo="materia")


def test_token_nao_vaza_no_resultado():
    r = rodar(montar(site=Site(resp(401, {"error": {"code": "unauthorized", "message": "m"}}))))
    assert "TOKEN-" not in repr(r) and "TOKEN-" not in " ".join(r.motivos)
