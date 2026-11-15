import pytest

from services.image_providers import (
    ImageSelector, ImagensUsadasMemoria, ResultadoVisao, SemVisao, VisaoIndisponivel,
)
from services.image_providers import selector as SEL
from helpers_imagens import HOST_OK, VISAO_OK, ProvedorFalso, VisaoFalsa, baixador, candidata

TERMOS = ["brigadeiro bowl", "chocolate pudding spoon", "chocolate dessert"]


def sel(*provs, **kw):
    return ImageSelector(list(provs), **kw)


def rodar(seletor, visao=None, baixar=None, usadas=None, termos=TERMOS, **kw):
    return seletor.selecionar(termos=termos, esperado="Brigadeiro de colher (doces)", prompt_imagem="prato pronto, vista de cima",
                              usadas=usadas or ImagensUsadasMemoria(), visao=visao or VisaoFalsa(), baixar=baixar or baixador(), **kw)


def codigos(r):
    return [x["codigo"] for x in r.rejeitadas]


def test_caminho_feliz_cover_exatamente_como_a_doc_e_sem_bytes():
    r = rodar(sel(ProvedorFalso(padrao=[candidata("7")])))
    assert r.status == "stock" and r.buscas == 1 and r.downloads == 1 and r.verificacoes_visao == 1
    assert r.cover == {"mode": "stock", "provider": "pexels", "sourceImageUrl": f"https://{HOST_OK}/photos/7.jpeg",
                       "sourcePageUrl": "https://www.pexels.com/photo/1/", "author": "Maria", "license": "Pexels License",
                       "attributionText": "Foto por Maria no Pexels"}
    assert set(r.meta) >= {"provider_image_id", "width", "height", "sha256", "mime"} and len(r.meta["sha256"]) == 64
    assert not any(isinstance(v, (bytes, bytearray)) for v in r.meta.values())


def test_termos_do_mais_especifico_ao_geral_e_provedores_em_ordem():
    a, b = ProvedorFalso("pixabay", hosts=("pixabay.com",)), ProvedorFalso("pexels")
    r = rodar(sel(a, b))
    assert [q for q, _ in a.consultas] == TERMOS == [q for q, _ in b.consultas]
    assert r.buscas == 6 and r.status == "generate" and a.consultas[0][1] == "en"


def test_para_na_primeira_candidata_boa_sem_buscar_mais():
    a = ProvedorFalso("pixabay", por_consulta={TERMOS[0]: [candidata("1", provider="pixabay", licenca="Pixabay Content License", host="pixabay.com")]}, hosts=("pixabay.com",))
    b = ProvedorFalso("pexels", padrao=[candidata("2")])
    r = rodar(sel(a, b))
    assert r.cover["provider"] == "pixabay" and b.consultas == []


@pytest.mark.parametrize("licenca", ["CC BY-NC 4.0", "CC BY-ND 4.0", "CC BY-SA 4.0", "All rights reserved", "", "GFDL"])
def test_licenca_recusada_img_01_e_nunca_cai_para_candidata_recusada(licenca):
    r = rodar(sel(ProvedorFalso(padrao=[candidata("1", licenca=licenca)])))
    assert r.status == "generate" and set(codigos(r)) == {"IMG-01"} and r.downloads == 0
    assert r.cover == {"mode": "generate", "imagePrompt": "prato pronto, vista de cima"}


def test_largura_orientacao_host_e_https():
    cs = [candidata("a", largura=1279), candidata("b", largura=0), candidata("c", largura=1500, altura=2000),
          candidata("d", host="evil.example.com"), candidata("e", url="http://images.pexels.com/e.jpeg")]
    r = rodar(sel(ProvedorFalso(padrao=cs)), termos=["x"])
    assert codigos(r) == ["IMG-02", "IMG-02", "IMG-02", "IMG-03", "IMG-03"] and r.downloads == 0


def test_largura_real_do_arquivo_img_02():
    r = rodar(sel(ProvedorFalso(padrao=[candidata("1", largura=1600)])), baixar=baixador(largura=900), termos=["x"])
    assert r.status == "generate" and codigos(r) == ["IMG-02"] and "real 900" in r.rejeitadas[0]["motivo"] and r.verificacoes_visao == 0


def test_proveniencia_incompleta_img_06():
    cs = [candidata("a", autor=""), candidata("b", autor="Autor desconhecido"), candidata("c", atribuicao=" "),
          candidata("d", pagina="")]
    r = rodar(sel(ProvedorFalso(padrao=cs)), termos=["x"])
    assert codigos(r) == ["IMG-06"] * 4 and r.status == "generate"


def test_cc0_dispensa_autor_e_atribuicao():
    c = candidata("1", provider="wikimedia", licenca="CC0", autor="", atribuicao="", host="upload.wikimedia.org")
    r = rodar(sel(ProvedorFalso("wikimedia", padrao=[c], hosts=("upload.wikimedia.org",))), termos=["x"])
    assert r.status == "stock" and r.cover["author"] == "" and r.cover["license"] == "CC0"


def test_cc_by_exige_autor_e_atribuicao():
    bom = candidata("1", provider="openverse", licenca="CC BY 4.0", autor="Ana", atribuicao='"t" por Ana sob CC BY 4.0')
    ruim = candidata("2", provider="openverse", licenca="CC BY 4.0", autor="", atribuicao="")
    r = rodar(sel(ProvedorFalso("openverse", padrao=[ruim, bom])), termos=["x"])
    assert r.status == "stock" and r.cover["sourcePageUrl"] and codigos(r) == ["IMG-06"]


def test_openverse_so_serve_se_o_host_estiver_na_lista():
    c = candidata("1", provider="openverse", licenca="CC BY 4.0", host="live.staticflickr.com", autor="Ana")
    r = rodar(sel(ProvedorFalso("openverse", padrao=[c], hosts=())), termos=["x"])
    assert codigos(r) == ["IMG-03"] and r.status == "generate"
    r2 = rodar(ImageSelector([ProvedorFalso("openverse", padrao=[c], hosts=())], hosts_permitidos=["live.staticflickr.com"]), termos=["x"])
    assert r2.status == "stock"


def test_dedupe_por_url_id_e_hash_img_05():
    u = ImagensUsadasMemoria()
    u.registrar(f"https://{HOST_OK}/photos/1.jpeg", "h", "pexels", "x")
    u.registrar("https://outra/url", "h2", "pexels", "2")
    cs = [candidata("1"), candidata("2", url=f"https://{HOST_OK}/novo.jpeg"), candidata("3")]
    b = baixador()
    img = b(f"https://{HOST_OK}/photos/3.jpeg"); u.registrar("https://z", img.sha256, "pexels", "outro")
    r = rodar(sel(ProvedorFalso(padrao=cs)), usadas=u, termos=["x"], baixar=b)
    assert codigos(r) == ["IMG-05", "IMG-05", "IMG-05"] and r.status == "generate"
    assert "hash" in r.rejeitadas[2]["motivo"] and r.verificacoes_visao == 0


def test_mesma_candidata_em_varias_buscas_so_e_avaliada_uma_vez():
    prov = ProvedorFalso(padrao=[candidata("1", licenca="CC BY-NC 4.0")])
    r = rodar(sel(prov))
    assert len(r.rejeitadas) == 1 and r.buscas == 3


def test_visao_reprovada_tenta_a_proxima():
    v = VisaoFalsa(ResultadoVisao(True, False, True, True, ""), ResultadoVisao(False, True, True, True), VISAO_OK)
    r = rodar(sel(ProvedorFalso(padrao=[candidata("1"), candidata("2"), candidata("3")])), visao=v, termos=["x"])
    assert r.status == "stock" and r.cover["sourceImageUrl"].endswith("/3.jpeg") and r.verificacoes_visao == 3
    assert [x["motivo"] for x in r.rejeitadas] == ["reprovada: sem_pessoas", "reprovada: prato_correto"]
    assert v.chamadas[0][1] == "image/png" and v.chamadas[0][2] == "Brigadeiro de colher (doces)"


def test_visao_none_e_falha_fechada():
    v = VisaoFalsa(ResultadoVisao(True, True, None, True))
    r = rodar(sel(ProvedorFalso(padrao=[candidata("1")])), visao=v, termos=["x"])
    assert r.status == "generate" and "sem_texto_ou_marca" in r.rejeitadas[0]["motivo"]


def test_visao_indisponivel_gera_pendencia_e_cai_em_generate():
    r = rodar(sel(ProvedorFalso(padrao=[candidata("1"), candidata("2")])), visao=SemVisao())
    assert r.status == "generate" and r.downloads == 1 and r.buscas == 1  # não gasta mais buscas
    assert r.pendencias == ["IMG-04: PENDENTE: verificação por visão (o llm_service não suporta imagem)"]


def test_erro_do_verificador_rejeita_so_a_candidata():
    v = VisaoFalsa(RuntimeError("timeout"), VISAO_OK)
    r = rodar(sel(ProvedorFalso(padrao=[candidata("1"), candidata("2")])), visao=v, termos=["x"])
    assert r.status == "stock" and r.rejeitadas[0]["codigo"] == "IMG-04" and "RuntimeError" in r.rejeitadas[0]["motivo"]


def test_falha_de_download_e_de_provedor_nao_derrubam():
    url1 = f"https://{HOST_OK}/photos/1.jpeg"
    b = baixador(erros={url1: PermissionError("ip interno")})
    quebrado = ProvedorFalso("pixabay", erro=True, hosts=("pixabay.com",))
    r = rodar(sel(quebrado, ProvedorFalso(padrao=[candidata("1"), candidata("2")])), baixar=b, termos=["x"])
    assert r.status == "stock" and r.cover["sourceImageUrl"].endswith("/2.jpeg")
    assert r.rejeitadas[0]["motivo"] == "download recusado: PermissionError"


def test_sem_provedores_disponiveis_gera_com_pendencia():
    r = rodar(sel(ProvedorFalso(disponivel=False)))
    assert r.status == "generate" and r.buscas == 0 and "nenhum provedor" in r.pendencias[0]


def test_geracao_so_com_teto_disponivel_img_07():
    r = rodar(sel(ProvedorFalso()), geracao_permitida=False)
    assert r.status == "sem_imagem" and r.cover is None and any("IMG-07" in p for p in r.pendencias)


def test_limites_de_download_e_visao(monkeypatch):
    monkeypatch.setattr(SEL, "MAX_VERIFICACOES_VISAO", 2)
    v = VisaoFalsa(*[ResultadoVisao(False, True, True, True)] * 9)
    cs = [candidata(str(i)) for i in range(5)]
    r = rodar(sel(ProvedorFalso(padrao=cs)), visao=v, termos=["x"])
    assert r.status == "generate" and r.verificacoes_visao == 2 and any("limite" in p for p in r.pendencias)


def test_termos_vazios_e_espacos_sao_ignorados():
    prov = ProvedorFalso()
    rodar(sel(prov), termos=["  ", "", " bolo "])
    assert [q for q, _ in prov.consultas] == ["bolo"]


def test_hosts_padrao_vem_dos_provedores():
    s = sel(ProvedorFalso("a", hosts=("a.test",)), ProvedorFalso("b", hosts=("b.test",)))
    assert s.hosts == ["a.test", "b.test"]
    from services.image_providers import OpenverseProvider
    padrao = ImageSelector()
    assert "upload.wikimedia.org" in padrao.hosts and "images.pexels.com" in padrao.hosts and OpenverseProvider.IMAGE_HOSTS == ()
