"""Fixtures das imagens. Tudo sintético: nenhuma rede, nenhuma imagem real."""
import io

from PIL import Image

from services.image_providers import ImageProvider, ImagemBaixada, ResultadoVisao, StandardImageResult

HOST_OK = "images.pexels.com"


def png_bytes(largura=1400, altura=900, cor=(120, 70, 40)):
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(buf, "PNG")
    return buf.getvalue()


def candidata(id_="1", provider="pexels", licenca="Pexels License", largura=1600, altura=900, autor="Maria",
              host=HOST_OK, url=None, pagina="https://www.pexels.com/photo/1/", atribuicao=None):
    return StandardImageResult(
        provider=provider, provider_image_id=id_, title="brigadeiro",
        original_image_url=url or f"https://{host}/photos/{id_}.jpeg", original_page_url=pagina,
        photographer=autor, photographer_url=None, license=licenca, license_url=None,
        attribution_text=f"Foto por {autor} no Pexels" if atribuicao is None else atribuicao,
        width=largura, height=altura,
    )


class ProvedorFalso(ImageProvider):
    """Devolve candidatas pré-definidas por consulta (ou a lista padrão) e registra as buscas."""

    def __init__(self, nome="pexels", por_consulta=None, padrao=(), disponivel=True, hosts=(HOST_OK,), erro=False):
        super().__init__(name=nome)
        self.por_consulta, self.padrao, self.disp, self.erro = por_consulta or {}, list(padrao), disponivel, erro
        self.IMAGE_HOSTS = tuple(hosts)
        self.consultas = []

    def is_available(self):
        return self.disp

    def search(self, query, limit=10, min_width=1280, lang="pt", **kw):
        self.consultas.append((query, lang))
        if self.erro:
            raise RuntimeError("falha do provedor")
        return list(self.por_consulta.get(query, self.padrao))


class VisaoFalsa:
    def __init__(self, *resultados):
        self.resultados, self.chamadas = list(resultados), []

    def verificar(self, imagem, mime, esperado):
        self.chamadas.append((len(imagem), mime, esperado))
        r = self.resultados.pop(0) if self.resultados else VISAO_OK
        if isinstance(r, Exception):
            raise r
        return r


VISAO_OK = ResultadoVisao(True, True, True, True, "ok")


def baixador(largura=1400, altura=900, por_url=None, erros=None):
    """Substitui baixar_imagem_em_memoria. Cada URL pode ter largura própria, ou erro."""
    chamadas = []

    def baixar(url, hosts_permitidos=None, **kw):
        chamadas.append(url)
        if erros and url in erros:
            raise erros[url]
        w = (por_url or {}).get(url, largura)
        dados = png_bytes(w, altura, cor=(w % 255, 40, 40))
        import hashlib
        return ImagemBaixada(dados, "image/png", "PNG", w, altura, hashlib.sha256(dados).hexdigest(), url)

    baixar.chamadas = chamadas
    return baixar
