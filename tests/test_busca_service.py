import pytest

from services.busca_service import (
    BuscaIndisponivel, BuscadorMock, LeitorMock, Orcamento, OrcamentoEsgotado, ProvedorNaoDefinido,
    ResultadoBusca, LeitorHTTP, buscar_com_tentativas, criar_buscador, dominio_de, dominio_permitido,
)

OK = ResultadoBusca("https://www.panelinha.com.br/x", "A")
FORA = ResultadoBusca("https://evil.example.com/x", "B")


def test_dominio_de_e_permitido():
    assert dominio_de("https://www.Panelinha.com.br/a") == "panelinha.com.br"
    assert dominio_permitido("blog.panelinha.com.br", ["panelinha.com.br"])
    assert not dominio_permitido("panelinha.com.br.evil.com", ["panelinha.com.br"])


def test_filtra_dominios_mesmo_se_provedor_ignorar():
    class Ruim(BuscadorMock):
        def buscar(self, c, d, m):
            return [OK, FORA]
    r = buscar_com_tentativas([Ruim()], "q", ["panelinha.com.br"], 10, Orcamento())
    assert r == [OK]


def test_tentativas_e_troca_de_provedor():
    quebrado = BuscadorMock(falhas=99, nome="a")
    bom = BuscadorMock(respostas={"*": [OK]}, nome="b")
    r = buscar_com_tentativas([quebrado, bom], "q", ["panelinha.com.br"], 10, Orcamento(), tentativas=2, espera=lambda s: None)
    assert r == [OK] and len(quebrado.chamadas) == 2


def test_retentativa_no_mesmo_provedor():
    b = BuscadorMock(respostas={"*": [OK]}, falhas=1)
    assert buscar_com_tentativas([b], "q", ["panelinha.com.br"], 10, Orcamento(), espera=lambda s: None) == [OK]


def test_todos_falham():
    with pytest.raises(BuscaIndisponivel):
        buscar_com_tentativas([BuscadorMock(falhas=99)], "q", [], 10, Orcamento(), espera=lambda s: None)


def test_orcamento_de_buscas_e_paginas():
    o = Orcamento(max_buscas=1, max_paginas=1)
    o.consumir_busca(); o.consumir_pagina()
    with pytest.raises(OrcamentoEsgotado):
        o.consumir_busca()
    with pytest.raises(OrcamentoEsgotado):
        o.consumir_pagina()


def test_orcamento_de_tempo():
    t = [0.0]
    o = Orcamento(timeout_min=10, relogio=lambda: t[0])
    o.iniciar(); t[0] = 601
    with pytest.raises(OrcamentoEsgotado):
        o.consumir_busca()


def test_fabrica_e_leitor_mock():
    assert criar_buscador("mock").nome == "mock"
    with pytest.raises(ProvedorNaoDefinido):
        criar_buscador("google")
    l = LeitorMock({"u": "texto", "v": RuntimeError("bloqueado")})
    assert l.ler("u") == "texto"
    with pytest.raises(RuntimeError):
        l.ler("v")


def test_leitor_http_exige_aprovacao_de_termos_antes_de_acessar_rede():
    reader = LeitorHTTP(fontes=[{
        "id": "panelinha", "dominio": "panelinha.com.br", "ativa": True,
    }])
    with pytest.raises(PermissionError, match="termos de uso"):
        reader.ler("https://panelinha.com.br/receita")


def test_leitor_http_recusa_host_privado():
    reader = LeitorHTTP(fontes=[{
        "id": "local", "dominio": "127.0.0.1", "ativa": True, "termos_aprovados": True,
    }])
    with pytest.raises(PermissionError, match="host de fonte não é público"):
        reader.ler("https://127.0.0.1/receita")
