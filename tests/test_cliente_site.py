import hashlib
import json
import logging

import httpx
import pytest

from integration import cliente_site as CS
from integration.adaptador_receita import reduzir_opcionais
from helpers_integracao import COVER_GERAR, OK_201, Site, cliente, corpo, payload, resp

SEGREDOS = ("TOKEN-DRAFT-XYZ", "TOKEN-PUBLISH-XYZ")
CHAVE = hashlib.sha256(b"recipe|brigadeiro-de-colher-cremoso|run-1").hexdigest()


def lookup(*itens):
    return resp(200, {"items": list(itens)})


def sem_segredo(texto):
    return not any(s in texto for s in SEGREDOS)


# ---- criação ---------------------------------------------------------------------------

def test_cabecalhos_e_corpo_de_um_rascunho():
    s = Site(resp(201, OK_201)); c = cliente(s)
    r = c.criar_receita(payload(), run_id="run-1")
    req = s.posts()[0]
    assert (req.url.path, req.headers["authorization"]) == ("/api/recipes", "Bearer TOKEN-DRAFT-XYZ")
    assert req.headers["content-type"] == "application/json" and req.headers["x-contract-version"] == "1"
    assert req.headers["idempotency-key"] == CHAVE == CS.chave_idempotencia("recipe", "brigadeiro-de-colher-cremoso", "run-1")
    assert req.headers["x-request-id"] == "rid1"
    b = corpo(req)
    assert b["status"] == "draft" and None not in b.values() and b["generationMeta"]["run_id"] == "run-1"
    assert (r.situacao, r.http_status, r.id, r.slug, r.status, r.tentativas, r.request_ids) == ("criado", 201, 123, OK_201["slug"], "draft", 1, ["rid1"])


def test_publicar_usa_o_token_de_escopo_publish():
    s = Site(resp(201, {**OK_201, "status": "published"})); c = cliente(s, fase=1)
    assert c.criar_receita(payload(status="published"), run_id="run-1").status == "published"
    assert s.posts()[0].headers["authorization"] == "Bearer TOKEN-PUBLISH-XYZ"


def test_escopo_e_fase_sao_checados_antes_de_qualquer_rede():
    s = Site(resp(201, OK_201))
    with pytest.raises(CS.EscopoLocalInsuficiente, match="Fase 0"):
        cliente(s, fase=0).criar_receita(payload(fase=0, status="published"), run_id="r")
    sem_publish = CS.ClienteSite("https://site.test", token_draft="TOKEN-DRAFT-XYZ", fase=1, cliente=httpx.Client(transport=httpx.MockTransport(s)))
    with pytest.raises(CS.EscopoLocalInsuficiente, match="publish"):
        sem_publish.criar_receita(payload(status="published"), run_id="r")
    sem_token = CS.ClienteSite("https://site.test", fase=0, cliente=httpx.Client(transport=httpx.MockTransport(s)))
    with pytest.raises(CS.EscopoLocalInsuficiente):
        sem_token.criar_receita(payload(), run_id="r")
    assert s.requisicoes == []


def test_https_obrigatorio_e_fase_valida():
    for url in ("http://site.test", "site.test", "ftp://site.test", ""):
        with pytest.raises(CS.ConfiguracaoInvalida):
            CS.ClienteSite(url, token_draft="x")
    with pytest.raises(CS.ConfiguracaoInvalida):
        CS.ClienteSite("https://site.test", token_draft="x", fase=7)


def test_replay_da_mesma_chave():
    s = Site(resp(201, OK_201, **{"Idempotent-Replay": "true"}))
    assert cliente(s).criar_receita(payload(), run_id="run-1").situacao == "repetido"


def test_payload_invalido_nao_chega_ao_site():
    s = Site(resp(201, OK_201)); c = cliente(s)
    ruim = payload().model_dump(mode="json"); ruim["steps"] = ruim["steps"][:2]
    with pytest.raises(CS.ContratoInvalido) as e:
        c.criar_receita(ruim, run_id="r")
    assert "steps" in str(e.value) and s.requisicoes == []
    with pytest.raises(CS.ContratoInvalido):
        cliente(s, dry_run=True).criar_receita(ruim, run_id="r")


def test_corpo_vai_em_utf_8_sem_escapar_acentos():
    s = Site(resp(201, OK_201)); cliente(s).criar_receita(payload(), run_id="run-1")
    bruto = s.posts()[0].content
    assert "chocolate em pó".encode("utf-8") in bruto and b"\\u00f3" not in bruto
    assert json.loads(bruto.decode("utf-8"))["ingredients"][0]["items"][1]["name"] == "chocolate em pó"


# ---- erros 4xx ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,corpo_erro,exc,codigo", [
    (400, {"error": {"code": "validation_failed", "message": "inválido", "details": [{"field": "excerpt", "issue": "max_160"}]}}, CS.RejeitadoPeloSite, "validation_failed"),
    (400, {"error": "Receita inválida.", "details": {"x": 1}}, CS.RejeitadoPeloSite, "legacy_http_400"),  # formato do site hoje
    (401, {"error": {"code": "unauthorized", "message": "não"}}, CS.SemAutorizacao, "unauthorized"),
    (403, {"error": {"code": "scope_insufficient", "message": "m"}}, CS.EscopoInsuficiente, "scope_insufficient"),
    (403, {"error": {"code": "publishing_disabled", "message": "m"}}, CS.PublicacaoBloqueada, "publishing_disabled"),
    (403, {"error": {"code": "phase_not_allowed", "message": "m"}}, CS.PublicacaoBloqueada, "phase_not_allowed"),
    (422, {"error": {"code": "diet_mismatch", "message": "m"}}, CS.RejeitadoPeloSite, "diet_mismatch"),
    (422, {"error": {"code": "image_host_not_allowed", "message": "m"}}, CS.RejeitadoPeloSite, "image_host_not_allowed"),
    (422, {"error": {"code": "subcategory_not_enabled", "message": "m"}}, CS.RejeitadoPeloSite, "subcategory_not_enabled"),
    (404, {}, CS.ErroSite, ""),
])
def test_erros_nao_sao_reenviados(status, corpo_erro, exc, codigo, caplog):
    s = Site(resp(status, corpo_erro)); c = cliente(s)
    with caplog.at_level(logging.DEBUG), pytest.raises(exc) as e:
        c.criar_receita(payload(), run_id="run-1")
    assert len(s.posts()) == 1 and c.esperas == [] and e.value.http_status == status and e.value.codigo == codigo
    assert e.value.request_id == "rid1" and sem_segredo(str(e.value)) and sem_segredo(caplog.text)


def test_detalhes_do_erro_chegam_a_quem_chamou():
    s = Site(resp(400, {"error": {"code": "validation_failed", "message": "m", "details": [{"field": "excerpt", "issue": "max_160"}]}}))
    with pytest.raises(CS.RejeitadoPeloSite) as e:
        cliente(s).criar_receita(payload(), run_id="r")
    assert e.value.detalhes == [{"field": "excerpt", "issue": "max_160"}]


# ---- 429 e 5xx -----------------------------------------------------------------------------

def test_429_respeita_retry_after_e_tenta_de_novo():
    s = Site(resp(429, {"error": {"code": "rate_limited", "message": "m"}}, **{"Retry-After": "3"}), resp(201, OK_201)); c = cliente(s)
    r = c.criar_receita(payload(), run_id="run-1")
    assert r.situacao == "criado" and c.esperas == [3.0] and r.tentativas == 2
    assert len({q.headers["idempotency-key"] for q in s.posts()}) == 1 and [q.headers["x-request-id"] for q in s.posts()] == ["rid1", "rid2"]


def test_429_com_espera_limitada_e_sem_cabecalho():
    s = Site(resp(429, {"error": {"code": "rate_limited"}}, **{"Retry-After": "99999"}), resp(429, {"error": {"code": "rate_limited"}}), resp(201, OK_201))
    c = cliente(s); c.criar_receita(payload(), run_id="r")
    assert c.esperas == [CS.MAX_ESPERA_429, 1.0]


def test_429_daily_cap_encerra_sem_tentar_de_novo():
    s = Site(resp(429, {"error": {"code": "daily_cap_reached", "message": "limite"}}, **{"Retry-After": "40000"})); c = cliente(s)
    with pytest.raises(CS.LimiteDiarioAtingido):
        c.criar_receita(payload(), run_id="r")
    assert len(s.posts()) == 1 and c.esperas == []


def test_429_persistente_vira_limite_de_requisicoes():
    s = Site(resp(429, {"error": {"code": "rate_limited"}}, **{"Retry-After": "1"})); c = cliente(s)
    with pytest.raises(CS.LimiteDeRequisicoes):
        c.criar_receita(payload(), run_id="r")
    assert len(s.posts()) == 3


def test_5xx_ate_3_tentativas_com_espera_crescente_e_mesma_chave():
    s = Site(resp(503, {"error": "indisponível"})); c = cliente(s)
    with pytest.raises(CS.ErroServidor) as e:
        c.criar_receita(payload(), run_id="run-1")
    assert len(s.posts()) == 3 and c.esperas == [1.0, 2.0] and e.value.http_status == 503
    assert {q.headers["idempotency-key"] for q in s.posts()} == {CHAVE} and len({q.headers["x-request-id"] for q in s.posts()}) == 3


def test_5xx_depois_ok():
    s = Site(resp(502), resp(201, OK_201)); c = cliente(s)
    assert c.criar_receita(payload(), run_id="r").situacao == "criado" and c.esperas == [1.0]


def test_timeout_reenvia_com_a_mesma_chave():
    s = Site(httpx.ReadTimeout("lento"), resp(201, OK_201)); c = cliente(s)
    r = c.criar_receita(payload(), run_id="run-1")
    assert r.situacao == "criado" and r.tentativas == 2 and c.esperas == [1.0]
    assert [q.headers["idempotency-key"] for q in s.posts()] == [CHAVE, CHAVE]


def test_timeout_persistente():
    s = Site(httpx.ConnectTimeout("x")); c = cliente(s)
    with pytest.raises(CS.ErroDeRede):
        c.criar_receita(payload(), run_id="r")
    assert len(s.posts()) == 3


# ---- 409 e confirmação ---------------------------------------------------------------------

def rota(post, get):
    def h(req):
        return post if req.method == "POST" else get
    return h


def test_timeout_depois_409_com_mesma_run_confirma_sem_reenviar():
    s = Site(httpx.ReadTimeout("x"), resp(409, {"error": {"code": "slug_conflict", "message": "m"}}), lookup({"id": 9, "slug": "s", "status": "published", "url": "u", "generation_meta": {"run_id": "run-1"}}))
    c = cliente(s)
    r = c.criar_receita(payload(), run_id="run-1")
    assert (r.situacao, r.id, r.slug, r.status) == ("confirmado_apos_409", 9, "s", "published") and len(s.posts()) == 2
    gets = [q for q in s.requisicoes if q.method == "GET"]
    assert gets[0].url.path == "/api/content/lookup" and dict(gets[0].url.params) == {"topic_slug": "brigadeiro-de-colher-cremoso"}
    assert "idempotency-key" not in gets[0].headers


def test_409_com_run_diferente_e_duplicada_e_nao_reenvia():
    s = Site(resp(409, {"error": {"code": "topic_exists", "message": "m"}}), lookup({"id": 1, "slug": "outra", "generation_meta": {"run_id": "outra-run"}}))
    r = cliente(s).criar_receita(payload(), run_id="run-1")
    assert r.situacao == "duplicada" and r.slug == "outra" and len(s.posts()) == 1


def test_409_sem_conteudo_da_pauta_e_conflito_de_slug():
    s = Site(resp(409, {"error": "Já existe uma receita com este slug."}), lookup())
    with pytest.raises(CS.ConflitoDeSlug) as e:
        cliente(s).criar_receita(payload(), run_id="run-1")
    assert e.value.http_status == 409 and e.value.codigo == "legacy_http_409"


def test_lookup_aceita_lista_pura_e_camel_case():
    s = Site(resp(409, {}), resp(200, [{"id": 5, "slug": "x", "generationMeta": {"run_id": "run-1"}}, "lixo"]))
    assert cliente(s).criar_receita(payload(), run_id="run-1").situacao == "confirmado_apos_409"


# ---- 413 -------------------------------------------------------------------------------------

def test_413_reduz_e_reenvia_uma_vez():
    s = Site(resp(413, {"error": {"code": "payload_too_large", "message": "m"}}), resp(201, OK_201)); c = cliente(s)
    p = payload(conteudo=__import__("helpers_integracao").conteudo_editor(dica_extra="dica", perguntas_frequentes=[{"pergunta": "a?", "resposta": "b"}]))
    r = c.criar_receita(p, run_id="run-1", reduzir=reduzir_opcionais)
    a, b = [corpo(q) for q in s.posts()]
    assert r.situacao == "criado" and "faq" in a and "faq" not in b and len(s.posts()) == 2


def test_413_sem_redutor_ou_depois_da_segunda_vez_levanta():
    s = Site(resp(413, {"error": {"code": "payload_too_large", "message": "m"}}))
    with pytest.raises(CS.ConteudoGrande):
        cliente(s).criar_receita(payload(), run_id="r")
    s2 = Site(resp(413, {"error": {"code": "payload_too_large", "message": "m"}})); c = cliente(s2)
    with pytest.raises(CS.ConteudoGrande):
        c.criar_receita(payload(), run_id="r", reduzir=reduzir_opcionais)
    assert len(s2.posts()) == 2


# ---- dry-run e segredos ----------------------------------------------------------------------

def test_dry_run_nao_usa_rede_e_mascara_o_token():
    s = Site(resp(201, OK_201)); c = cliente(s, dry_run=True)
    r = c.criar_receita(payload(), run_id="run-1")
    assert r.situacao == "dry_run" and s.requisicoes == [] and r.payload["title"] and r.cabecalhos["Authorization"] == "Bearer ***"
    assert r.cabecalhos["Idempotency-Key"] == CHAVE and r.cabecalhos["alvo"] == "POST /api/recipes"
    texto = CS.formatar_dry_run(r)
    assert sem_segredo(texto) and '"title"' in texto and "Bearer ***" in texto


def test_dry_run_exige_escopo_igual_ao_envio_real():
    with pytest.raises(CS.EscopoLocalInsuficiente):
        cliente(Site(resp(201)), fase=0, dry_run=True).criar_receita(payload(fase=0, status="published"), run_id="r")


def test_token_nunca_vaza(caplog):
    s = Site(resp(503, {"error": "x"})); c = cliente(s)
    assert sem_segredo(repr(c)) and "site.test" in repr(c)
    with caplog.at_level(logging.DEBUG), pytest.raises(CS.ErroServidor) as e:
        c.criar_receita(payload(), run_id="r")
    assert sem_segredo(caplog.text) and sem_segredo(str(e.value)) and sem_segredo(repr(e.value))


# ---- leitura ----------------------------------------------------------------------------------

def test_endpoints_de_leitura():
    s = Site(resp(200, {"categories": []})); c = cliente(s)
    for chamar, caminho in ((c.taxonomia, "/api/taxonomy"), (c.catalogo_ingredientes, "/api/catalog/ingredients"), (c.cobertura, "/api/coverage")):
        assert chamar() == {"categories": []} and s.requisicoes[-1].url.path == caminho
        assert s.requisicoes[-1].headers["authorization"] == "Bearer TOKEN-DRAFT-XYZ" and s.requisicoes[-1].method == "GET"
    assert c.lookup(slug="a", title="b") is not None and dict(s.requisicoes[-1].url.params) == {"slug": "a", "title": "b"}
    with pytest.raises(ValueError):
        c.lookup()


def test_leitura_tenta_de_novo_em_5xx_e_levanta_em_4xx():
    s = Site(resp(500), resp(200, {"ok": 1})); c = cliente(s)
    assert c.cobertura() == {"ok": 1} and c.esperas == [1.0]
    with pytest.raises(CS.SemAutorizacao):
        cliente(Site(resp(401, {"error": "x"}))).taxonomia()


def test_aguardar_estado_ate_sair_de_processing():
    s = Site(resp(200, {"status": "processing"}), resp(200, {"status": "processing"}), resp(200, {"status": "published", "image_state": "ready"})); c = cliente(s)
    assert c.aguardar_estado("minha-receita", tentativas=5, intervalo=2.0) == {"status": "published", "image_state": "ready"}
    assert c.esperas == [2.0, 2.0] and s.requisicoes[0].url.path == "/api/recipes/minha-receita/status"
    eterno = Site(resp(200, {"status": "processing"})); c2 = cliente(eterno)
    assert c2.aguardar_estado("x", tentativas=3)["status"] == "processing" and len(eterno.requisicoes) == 3


# ---- artigos -------------------------------------------------------------------------------------

def artigo():
    from test_contratos import artigo as a
    return a()


def test_criar_artigo():
    s = Site(resp(201, {"id": 1, "slug": "ganache", "status": "draft", "url": "u"})); c = cliente(s)
    r = c.criar_artigo(artigo(), run_id="run-9")
    req = s.posts()[0]
    assert r.situacao == "criado" and req.url.path == "/api/articles"
    assert req.headers["idempotency-key"] == CS.chave_idempotencia("tip", "brigadeiro-de-colher-cremoso", "run-9")
    with pytest.raises(CS.ContratoInvalido):
        c.criar_artigo({**artigo(), "type": "noticia"}, run_id="r")
    with pytest.raises(CS.ContratoInvalido):
        c.criar_artigo({"title": "sem tipo"}, run_id="r")
