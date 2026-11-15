import os

import httpx
import pytest

from services.image_providers import storage as S
from helpers_imagens import png_bytes

PUBLICO = [(2, 1, 6, "", ("93.184.216.34", 0))]


@pytest.fixture(autouse=True)
def dns_publico(monkeypatch):
    mapa = {"cdn.exemplo.com": PUBLICO, "images.pexels.com": PUBLICO, "evil.exemplo.com": PUBLICO,
            "interno.exemplo.com": [(2, 1, 6, "", ("10.0.0.5", 0))], "cgnat.exemplo.com": [(2, 1, 6, "", ("100.64.0.1", 0))],
            "v6.exemplo.com": [(10, 1, 6, "", ("::1", 0, 0, 0))]}
    def fake(host, port, *a, **k):
        if host not in mapa:
            import socket
            raise socket.gaierror("sem DNS")
        return mapa[host]
    monkeypatch.setattr(S.socket, "getaddrinfo", fake)


def cliente(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def baixar(url, handler, **kw):
    return S.baixar_imagem_em_memoria(url, cliente=cliente(handler), hosts_permitidos=kw.pop("hosts", ["cdn.exemplo.com"]), **kw)


def ok(png=None):
    return lambda req: httpx.Response(200, content=png or png_bytes(1400, 900))


def test_baixa_valida_e_calcula_hash_sem_gravar_em_disco(tmp_path):
    try:
        antes = os.getcwd()
    except FileNotFoundError:  # outro teste pode ter deixado o cwd apagado
        antes = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(tmp_path)
    try:
        img = baixar("https://cdn.exemplo.com/a.png", ok())
    finally:
        os.chdir(antes)
    assert (img.largura, img.altura, img.formato, img.mime) == (1400, 900, "PNG", "image/png")
    assert len(img.sha256) == 64 and img.conteudo[:4] == b"\x89PNG" and "conteudo" not in repr(img)
    assert os.listdir(tmp_path) == []
    assert not hasattr(S, "baixar_e_processar_imagem") and not hasattr(S, "DEFAULT_STORAGE_DIR")


def test_hash_estavel_para_o_mesmo_conteudo():
    a = baixar("https://cdn.exemplo.com/a.png", ok(png_bytes(1300, 800)))
    b = baixar("https://cdn.exemplo.com/b.png", ok(png_bytes(1300, 800)))
    assert a.sha256 == b.sha256


@pytest.mark.parametrize("url,esperado", [
    ("http://cdn.exemplo.com/a.png", "HTTPS"), ("ftp://cdn.exemplo.com/a.png", "HTTPS"),
    ("https://outro.exemplo.net/a.png", "fora da lista"),
])
def test_esquema_e_host_recusados(url, esperado):
    with pytest.raises(S.DownloadRecusado, match=esperado):
        baixar(url, ok())


@pytest.mark.parametrize("host", ["interno.exemplo.com", "cgnat.exemplo.com", "v6.exemplo.com", "localhost"])
def test_ssrf_bloqueia_ip_nao_publico(host):
    with pytest.raises((PermissionError, S.DownloadRecusado)):
        baixar(f"https://{host}/a.png", ok(), hosts=[host])


def test_host_que_nao_resolve():
    with pytest.raises(ValueError, match="resolver"):
        baixar("https://naoexiste.exemplo.com/a.png", ok(), hosts=["naoexiste.exemplo.com"])


def test_redirect_permitido_e_revalidado():
    def handler(req):
        if req.url.host == "cdn.exemplo.com":
            return httpx.Response(302, headers={"location": "https://images.pexels.com/x.png"})
        return httpx.Response(200, content=png_bytes())
    img = baixar("https://cdn.exemplo.com/a.png", handler, hosts=["cdn.exemplo.com", "images.pexels.com"])
    assert img.url_final == "https://images.pexels.com/x.png"


@pytest.mark.parametrize("destino,esperado", [
    ("https://evil.exemplo.com/x.png", "fora da lista"),      # host não permitido
    ("http://cdn.exemplo.com/x.png", "HTTPS"),                # rebaixa para http
    ("https://interno.exemplo.com/x.png", "fora da lista"),   # host interno fora da lista
])
def test_redirect_para_fora_e_bloqueado(destino, esperado):
    handler = lambda req: httpx.Response(302, headers={"location": destino})
    with pytest.raises(S.DownloadRecusado, match=esperado):
        baixar("https://cdn.exemplo.com/a.png", handler)


def test_redirect_para_ip_interno_mesmo_na_lista_e_bloqueado():
    handler = lambda req: httpx.Response(302, headers={"location": "https://interno.exemplo.com/x.png"})
    with pytest.raises(PermissionError):
        baixar("https://cdn.exemplo.com/a.png", handler, hosts=["cdn.exemplo.com", "interno.exemplo.com"])


def test_redirect_em_laco_e_sem_destino():
    laco = lambda req: httpx.Response(302, headers={"location": "https://cdn.exemplo.com/outra"})
    with pytest.raises(S.DownloadRecusado, match="demais"):
        baixar("https://cdn.exemplo.com/a.png", laco)
    with pytest.raises(S.DownloadRecusado, match="sem destino"):
        baixar("https://cdn.exemplo.com/a.png", lambda req: httpx.Response(302))


def test_limites_e_formatos():
    with pytest.raises(S.DownloadRecusado, match="HTTP 404"):
        baixar("https://cdn.exemplo.com/a.png", lambda r: httpx.Response(404))
    with pytest.raises(S.DownloadRecusado, match="limite"):
        baixar("https://cdn.exemplo.com/a.png", ok(b"x" * 5000), max_bytes=1000)
    with pytest.raises(S.DownloadRecusado, match="limite"):
        baixar("https://cdn.exemplo.com/a.png", lambda r: httpx.Response(200, headers={"content-length": "999999"}, content=b"x"), max_bytes=1000)
    with pytest.raises(S.DownloadRecusado, match="não é uma imagem"):
        baixar("https://cdn.exemplo.com/a.png", ok(b"isto nao e imagem"))
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (50, 50)).save(buf, "GIF")
    with pytest.raises(S.DownloadRecusado, match="formato"):
        baixar("https://cdn.exemplo.com/a.png", ok(buf.getvalue()))
    with pytest.raises(S.DownloadRecusado, match="pixels"):
        monkey = S.MAX_PIXELS
        try:
            S.MAX_PIXELS = 100
            baixar("https://cdn.exemplo.com/a.png", ok(png_bytes(50, 50)))
        finally:
            S.MAX_PIXELS = monkey


def test_imagem_truncada_e_recusada():
    truncada = png_bytes(1400, 900)[:-200]
    with pytest.raises(S.DownloadRecusado):
        baixar("https://cdn.exemplo.com/a.png", ok(truncada))
