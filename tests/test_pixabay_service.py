"""Testes unitários do Pixabay: respostas HTTP simuladas, sem rede ou chave real."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from services import pixabay_service


HIT = {
    "id": 12345,
    "user": "Autor de teste",
    "user_id": 678,
    "imageWidth": 1920,
    "imageHeight": 1280,
    "webformatWidth": 1280,
    "largeImageURL": "https://pixabay.example/image-large.jpg",
    "fullHDURL": "https://pixabay.example/image-fullhd.jpg",
    "webformatURL": "https://pixabay.example/image-web.jpg",
    "pageURL": "https://pixabay.example/page",
    "downloads": 300,
    "likes": 50,
    "tags": "bolo, chocolate, sobremesa",
}


def response(hits: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"total": len(hits), "hits": hits},
        request=httpx.Request("GET", pixabay_service.PIXABAY_ENDPOINT),
    )


def setup_pixabay(monkeypatch):
    monkeypatch.setattr(pixabay_service, "PIXABAY_API_KEY", "test-api-key")
    pixabay_service._query_cache.clear()


def test_busca_direta_pixabay_usa_parametros_e_retorna_hits(monkeypatch):
    setup_pixabay(monkeypatch)
    with patch.object(pixabay_service.httpx, "get", return_value=response([HIT])) as get:
        hits = pixabay_service.buscar_pixabay("bolo de chocolate", lang="pt", categoria="food")

    assert hits == [HIT]
    _, kwargs = get.call_args
    assert kwargs["params"]["q"] == "bolo de chocolate"
    assert kwargs["params"]["lang"] == "pt"
    assert kwargs["params"]["category"] == "food"
    assert kwargs["params"]["min_width"] == 1280
    assert kwargs["params"]["key"] == "test-api-key"


def test_busca_imagem_receita_formata_proveniencia(monkeypatch):
    setup_pixabay(monkeypatch)
    with patch.object(pixabay_service.httpx, "get", return_value=response([HIT])) as get:
        result = pixabay_service.buscar_imagem_receita(
            "Bolo Fofinho de Cenoura com Cobertura de Chocolate",
            categoria="Bolos",
            subcategoria="Bolo Caseiro",
        )

    assert result is not None
    assert result["mode"] == "stock"
    assert result["provider"] == "pixabay"
    assert result["sourceImageUrl"] == HIT["largeImageURL"]
    assert result["sourcePageUrl"] == HIT["pageURL"]
    assert result["author"] == HIT["user"]
    assert "Pixabay" in result["attributionText"]
    assert len(result["coverImageAlt"]) >= 8
    assert get.call_count == 1


def test_busca_pixabay_usa_cache_sem_repetir_requisicao(monkeypatch):
    setup_pixabay(monkeypatch)
    with patch.object(pixabay_service.httpx, "get", return_value=response([HIT])) as get:
        first = pixabay_service.buscar_pixabay("ganache")
        second = pixabay_service.buscar_pixabay("ganache")

    assert first == second == [HIT]
    assert get.call_count == 1


def test_busca_sem_chave_nao_chama_api(monkeypatch):
    monkeypatch.setattr(pixabay_service, "PIXABAY_API_KEY", "")
    pixabay_service._query_cache.clear()
    with patch.object(pixabay_service.httpx, "get") as get:
        assert pixabay_service.buscar_pixabay("bolo") is None
    get.assert_not_called()
