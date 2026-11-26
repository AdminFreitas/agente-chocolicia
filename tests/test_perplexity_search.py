from unittest.mock import MagicMock
import pytest

from services.busca_service import (
    BuscadorPerplexity,
    ResultadoBusca,
    criar_buscador,
    buscar_com_tentativas,
    Orcamento,
)


class MockItem:
    def __init__(self, title, url, snippet="texto", date=None, last_updated=None):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.date = date
        self.last_updated = last_updated


class MockResponse:
    def __init__(self, results):
        self.results = results


def test_resultado_busca_campos():
    r = ResultadoBusca(
        url="https://panelinha.com.br/receita/bolo",
        titulo="Bolo de Cenoura",
        snippet="Receita deliciosa...",
        date="2026-01-01",
        last_updated="2026-05-01",
    )
    assert r.dominio == "panelinha.com.br"
    assert r.snippet == "Receita deliciosa..."
    assert r.date == "2026-01-01"
    assert r.last_updated == "2026-05-01"


def test_buscador_perplexity_exige_chave(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="PERPLEXITY_API_KEY não configurada"):
        BuscadorPerplexity()


def test_buscador_perplexity_busca_simples():
    mock_client = MagicMock()
    mock_client.search.create.return_value = MockResponse(
        [
            MockItem(
                title="Bolo de Chocolate",
                url="https://panelinha.com.br/bolo-chocolate",
                snippet="Bolo fofinho de chocolate",
                date="2026-02-10",
                last_updated="2026-02-15",
            )
        ]
    )

    buscador = BuscadorPerplexity(cliente=mock_client, country="BR")
    resultados = buscador.buscar("bolo de chocolate", dominios=["panelinha.com.br"], max_resultados=5)

    assert len(resultados) == 1
    res = resultados[0]
    assert res.titulo == "Bolo de Chocolate"
    assert res.url == "https://panelinha.com.br/bolo-chocolate"
    assert res.dominio == "panelinha.com.br"
    assert res.snippet == "Bolo fofinho de chocolate"
    assert res.date == "2026-02-10"
    assert res.last_updated == "2026-02-15"

    mock_client.search.create.assert_called_once_with(
        query="bolo de chocolate",
        max_results=5,
        search_domain_filter=["panelinha.com.br"],
        country="BR",
    )


def test_buscador_perplexity_multi_query_e_dedup():
    mock_client = MagicMock()
    # Simula retorno com URLs repetidas entre queries
    mock_client.search.create.return_value = MockResponse(
        [
            MockItem(title="Receita 1", url="https://panelinha.com.br/r1"),
            MockItem(title="Receita 2", url="https://panelinha.com.br/r2"),
            MockItem(title="Receita 1 Duplicada", url="https://panelinha.com.br/r1"),
            MockItem(title="Receita 3", url="https://panelinha.com.br/r3"),
        ]
    )

    buscador = BuscadorPerplexity(cliente=mock_client)
    queries = ["bolo de brigadeiro", "torta de chocolate"]
    resultados = buscador.buscar(queries, dominios=["panelinha.com.br"])

    assert len(resultados) == 3
    urls = [r.url for r in resultados]
    assert urls == [
        "https://panelinha.com.br/r1",
        "https://panelinha.com.br/r2",
        "https://panelinha.com.br/r3",
    ]
    # Confere que as queries foram passadas como lista
    call_args = mock_client.search.create.call_args[1]
    assert call_args["query"] == ["bolo de brigadeiro", "torta de chocolate"]


def test_buscador_perplexity_divisao_mais_que_5_queries():
    mock_client = MagicMock()
    mock_client.search.create.side_effect = [
        MockResponse([MockItem(title=f"R{i}", url=f"https://site.com/r{i}") for i in range(1, 6)]),
        MockResponse([MockItem(title="R6", url="https://site.com/r6")]),
    ]

    buscador = BuscadorPerplexity(cliente=mock_client)
    queries = [f"q{i}" for i in range(1, 7)]  # 6 queries
    resultados = buscador.buscar(queries)

    assert len(resultados) == 6
    assert mock_client.search.create.call_count == 2


def test_buscador_perplexity_filtro_dominios_defesa():
    mock_client = MagicMock()
    # API hipoteticamente retornou um resultado de domínio não permitido
    mock_client.search.create.return_value = MockResponse(
        [
            MockItem(title="Aprovado", url="https://panelinha.com.br/aprovado"),
            MockItem(title="Spam", url="https://site-malicioso.com/spam"),
        ]
    )

    buscador = BuscadorPerplexity(cliente=mock_client)
    resultados = buscador.buscar("chocolate", dominios=["panelinha.com.br"])

    assert len(resultados) == 1
    assert resultados[0].url == "https://panelinha.com.br/aprovado"


def test_buscador_perplexity_parametros_avancados():
    mock_client = MagicMock()
    mock_client.search.create.return_value = MockResponse([])

    buscador = BuscadorPerplexity(cliente=mock_client, country="BR")
    buscador.buscar(
        "consulta",
        max_resultados=50,  # Clampar em 20
        search_context_size="high",
        search_language_filter=["pt"],
        search_recency_filter="month",
    )

    kwargs = mock_client.search.create.call_args[1]
    assert kwargs["max_results"] == 20
    assert kwargs["search_context_size"] == "high"
    assert kwargs["search_language_filter"] == ["pt"]
    assert kwargs["search_recency_filter"] == "month"


def test_buscador_perplexity_erro_autenticacao_401():
    from perplexity import AuthenticationError

    mock_client = MagicMock()
    response_mock = MagicMock()
    response_mock.status_code = 401
    mock_client.search.create.side_effect = AuthenticationError(
        "Invalid API Key", response=response_mock, body=None
    )

    buscador = BuscadorPerplexity(cliente=mock_client)
    with pytest.raises(RuntimeError, match="Falha de autenticação na API Perplexity \\(401\\)"):
        buscador.buscar("chocolate")


def test_buscador_perplexity_erro_rate_limit_429():
    from perplexity import RateLimitError

    mock_client = MagicMock()
    response_mock = MagicMock()
    response_mock.status_code = 429
    response_mock.headers = {"retry-after": "10"}
    mock_client.search.create.side_effect = RateLimitError(
        "Rate limit exceeded", response=response_mock, body=None
    )

    buscador = BuscadorPerplexity(cliente=mock_client)
    with pytest.raises(RuntimeError, match=r"Limite de requisições excedido.*Retry-After: 10"):
        buscador.buscar("chocolate")


def test_criar_buscador_perplexity():
    mock_client = MagicMock()
    b = criar_buscador("perplexity", cliente=mock_client)
    assert b.nome == "perplexity"
    assert isinstance(b, BuscadorPerplexity)

    b2 = criar_buscador("perplexityai", cliente=mock_client)
    assert b2.nome == "perplexity"


def test_buscar_com_tentativas_integracao():
    mock_client = MagicMock()
    mock_client.search.create.return_value = MockResponse(
        [MockItem(title="Torta", url="https://panelinha.com.br/torta")]
    )

    buscador = BuscadorPerplexity(cliente=mock_client)
    resultados = buscar_com_tentativas(
        buscadores=[buscador],
        consulta="torta",
        dominios=["panelinha.com.br"],
        max_resultados=5,
        orcamento=Orcamento(),
    )

    assert len(resultados) == 1
    assert resultados[0].url == "https://panelinha.com.br/torta"
