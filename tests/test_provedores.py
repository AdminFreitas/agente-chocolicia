import logging

import pytest

from services.image_providers import (
    OpenverseProvider, PexelsProvider, PixabayProvider, WikimediaProvider, classificar_licenca, user_agent,
)


class Resp:
    def __init__(self, dados, status=200):
        self._d, self.status_code, self.text = dados, status, ""

    def json(self):
        return self._d


def usar(monkeypatch, modulo, dados=None, status=200, erro=None):
    chamadas = []

    def fake(url, **kw):
        chamadas.append((url, kw))
        if erro:
            raise erro
        return Resp(dados, status)

    monkeypatch.setattr(f"services.image_providers.{modulo}.httpx.get", fake)
    return chamadas


def test_user_agent_usa_site_base_url_sem_dominio_fixo(monkeypatch):
    monkeypatch.delenv("SITE_BASE_URL", raising=False)
    assert user_agent() == "ChocoliciaAgent/1.0"
    monkeypatch.setenv("SITE_BASE_URL", "https://exemplo.test")
    assert user_agent() == "ChocoliciaAgent/1.0 (+https://exemplo.test)"


def test_openverse_so_aceita_cc0_pdm_e_by(monkeypatch):
    itens = [{"id": str(i), "license": lic, "license_version": "4.0", "url": f"https://img.test/{i}.jpg", "width": 1600, "height": 900,
              "creator": "Ana", "title": "t", "foreign_landing_url": "https://img.test/p"}
             for i, lic in enumerate(["cc0", "pdm", "by", "by-sa", "by-nc", "by-nd", "by-nc-sa", ""])]
    itens.append({"id": "pequena", "license": "by", "url": "https://img.test/p.jpg", "width": 800, "height": 600})
    usar(monkeypatch, "openverse", {"results": itens})
    r = OpenverseProvider().search("brigadeiro", min_width=1280)
    assert [x.license for x in r] == ["CC0 4.0", "PDM 4.0", "CC BY 4.0"]
    assert {classificar_licenca("openverse", x.license).codigo for x in r} == {"cc0", "pdm", "cc-by"}
    assert "by-sa" not in OpenverseProvider.LICENCAS_ACEITAS and OpenverseProvider.IMAGE_HOSTS == ()
    assert r[2].attribution_text == '"t" por Ana sob CC BY 4.0'


def test_openverse_sem_criador_nao_inventa_autor(monkeypatch):
    usar(monkeypatch, "openverse", {"results": [{"id": "1", "license": "by", "url": "https://img.test/1.jpg", "width": 1600, "height": 900}]})
    r = OpenverseProvider().search("x")
    assert r[0].photographer == "" and r[0].attribution_text == ""


def test_wikimedia_nao_assume_licenca_e_deixa_a_decisao_para_a_politica(monkeypatch):
    def pagina(lic, autor="<b>Bia</b>"):
        ext = {"Artist": {"value": autor}}
        if lic is not None:
            ext["LicenseShortName"] = {"value": lic}
        return {"title": "File:A.jpg", "imageinfo": [{"url": "https://upload.wikimedia.org/a.jpg", "width": 2000, "height": 1200,
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:A.jpg", "extmetadata": ext}]}
    usar(monkeypatch, "wikimedia", {"query": {"pages": {"1": pagina("CC BY 4.0"), "2": pagina(None), "3": pagina("CC BY-SA 4.0"), "4": pagina("CC BY-NC 2.0")}}})
    r = {x.provider_image_id: x for x in WikimediaProvider().search("bolo")}
    assert r["1"].photographer == "Bia" and r["1"].attribution_text.startswith("Foto: Bia")
    assert r["2"].license == "" and r["2"].attribution_text == ""   # antes virava "CC-BY-SA"
    assert [classificar_licenca("wikimedia", r[k].license).aceita for k in "1234"] == [True, False, False, False]
    assert WikimediaProvider.IMAGE_HOSTS == ("upload.wikimedia.org",)


def test_pexels_e_pixabay_basico(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "chave-pexels"); monkeypatch.setenv("PIXABAY_API_KEY", "chave-pixabay")
    usar(monkeypatch, "pexels", {"photos": [
        {"id": 1, "width": 2000, "height": 1200, "photographer": "Caio", "url": "https://www.pexels.com/photo/1/",
         "src": {"large2x": "https://images.pexels.com/1.jpeg"}},
        {"id": 2, "width": 800, "height": 500, "photographer": "Duda", "src": {"large2x": "https://images.pexels.com/2.jpeg"}}]})
    px = PexelsProvider().search("brigadeiro")
    assert [x.provider_image_id for x in px] == ["1"] and px[0].license == "Pexels License" and px[0].attribution_text == "Foto por Caio no Pexels"
    usar(monkeypatch, "pixabay", {"hits": [{"id": 9, "largeImageURL": "https://pixabay.com/get/x.jpg", "pageURL": "https://pixabay.com/photos/x-9/",
                                            "user": "Eva", "user_id": 5, "imageWidth": 1920, "imageHeight": 1280, "tags": "cake, chocolate"}]})
    pb = PixabayProvider().search("bolo")[0]
    assert pb.license == "Pixabay Content License" and pb.photographer == "Eva" and pb.tags == ["cake", "chocolate"]


def test_provedor_sem_chave_fica_indisponivel(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False); monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    assert not PexelsProvider().is_available() and not PixabayProvider().is_available()
    assert PexelsProvider().search("x") == [] and OpenverseProvider().is_available() and WikimediaProvider().is_available()


def test_erro_nao_vaza_a_chave_no_log(monkeypatch, caplog):
    monkeypatch.setenv("PIXABAY_API_KEY", "SEGREDO-123")
    usar(monkeypatch, "pixabay", erro=RuntimeError("falha em https://pixabay.com/api/?key=SEGREDO-123"))
    with caplog.at_level(logging.DEBUG):
        assert PixabayProvider().search("bolo") == []
    assert "SEGREDO-123" not in caplog.text and "RuntimeError" in caplog.text


def test_http_de_erro_devolve_lista_vazia(monkeypatch):
    for modulo, cls in (("openverse", OpenverseProvider), ("wikimedia", WikimediaProvider)):
        usar(monkeypatch, modulo, {}, status=500)
        assert cls().search("x") == []
