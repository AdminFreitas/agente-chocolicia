"""
services/image_providers/storage.py — Download SEGURO e SÓ EM MEMÓRIA.

Mudanças em relação à versão anterior (docs/01 §12, PLANO Passo 8):
- Não grava nada em disco: devolve os bytes em memória (para a verificação por
  visão, IMG-04) e o hash SHA-256 (IMG-05). Quem armazena a imagem é o site.
- Redirecionamentos tratados à mão: cada salto exige HTTPS, host da lista
  permitida (IMG-03) e passa por _verificar_ssrf (antes, follow_redirects=True
  deixava um redirecionamento escapar das verificações).
- Limites: tamanho (10 MB), tempo, formato real (JPEG, PNG ou WebP) e pixels.

PENDENTE: o DNS é resolvido em _verificar_ssrf e de novo pelo httpx (janela de
DNS rebinding). Mitigação atual: só hosts da lista permitida. Fixar o IP na
conexão exige mudança maior (ver "Lacunas").
"""

import hashlib
import io
import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Optional, Sequence
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

from services.busca_service import dominio_permitido
from services.image_providers.base import user_agent

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB (docs/06 §7.1)
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
DOWNLOAD_TIMEOUT = 15
MAX_REDIRECTS = 3
MAX_PIXELS = 40_000_000  # parâmetro de implementação: evita imagem-bomba
_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_REDIRECTS = {301, 302, 303, 307, 308}


class DownloadRecusado(Exception):
    """A imagem não passou nas verificações de segurança."""


@dataclass
class ImagemBaixada:
    conteudo: bytes = field(repr=False)
    mime: str
    formato: str
    largura: int
    altura: int
    sha256: str
    url_final: str


def _verificar_ssrf(url: str) -> None:
    """
    Protege contra SSRF. Bloqueia esquemas inseguros, hosts locais e qualquer IP
    que não seja público (privado, loopback, link-local, reservado, CGNAT etc.).
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Esquema de URL inválido ou inseguro: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL sem hostname válido: {url}")

    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        raise PermissionError(f"Acesso bloqueado a host local/privado: {hostname}")

    try:
        for entry in socket.getaddrinfo(hostname, None):
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if not ip_obj.is_global:
                raise PermissionError(f"Acesso bloqueado a IP não público ({ip_str}) para o host {hostname}")
    except socket.gaierror as e:
        raise ValueError(f"Não foi possível resolver o hostname {hostname}: {e}")


def _validar_salto(url: str, hosts_permitidos: Optional[Sequence[str]]) -> None:
    p = urlparse(url)
    if p.scheme.lower() != "https":
        raise DownloadRecusado(f"somente HTTPS é aceito: {p.scheme or 'sem esquema'}")
    if hosts_permitidos is not None and not dominio_permitido(p.hostname or "", hosts_permitidos):
        raise DownloadRecusado(f"host fora da lista permitida: {p.hostname}")
    _verificar_ssrf(url)


def baixar_imagem_em_memoria(
    url: str,
    *,
    hosts_permitidos: Optional[Sequence[str]] = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    cliente: Optional[httpx.Client] = None,
) -> ImagemBaixada:
    """
    Baixa e valida uma imagem. Nada é gravado em disco.
    `hosts_permitidos=None` desliga só o filtro de host (as demais proteções continuam).
    """
    proprio = cliente is None
    cli = cliente or httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=DOWNLOAD_TIMEOUT, write=10.0, pool=5.0),
        headers={"User-Agent": user_agent(), "Accept": "image/webp,image/jpeg,image/png"},
    )
    try:
        atual = url
        buffer = bytearray()
        for _ in range(MAX_REDIRECTS + 1):
            _validar_salto(atual, hosts_permitidos)
            with cli.stream("GET", atual, follow_redirects=False) as resp:
                if resp.status_code in _REDIRECTS:
                    destino = resp.headers.get("location")
                    if not destino:
                        raise DownloadRecusado("redirecionamento sem destino")
                    atual = urljoin(atual, destino)
                    continue
                if resp.status_code != 200:
                    raise DownloadRecusado(f"HTTP {resp.status_code}")
                declarado = resp.headers.get("content-length")
                if declarado and declarado.isdigit() and int(declarado) > max_bytes:
                    raise DownloadRecusado("imagem acima do limite de tamanho")
                for chunk in resp.iter_bytes(chunk_size=65536):
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise DownloadRecusado(f"imagem acima do limite de {max_bytes // (1024 * 1024)} MB")
                break
        else:
            raise DownloadRecusado("redirecionamentos demais")
    finally:
        if proprio:
            cli.close()

    dados = bytes(buffer)
    try:
        img = Image.open(io.BytesIO(dados))
        formato = img.format
        largura, altura = img.size
        if formato not in ALLOWED_FORMATS:
            raise DownloadRecusado(f"formato não suportado: {formato}")
        if largura * altura > MAX_PIXELS:
            raise DownloadRecusado("imagem com pixels demais")
        img.verify()
    except DownloadRecusado:
        raise
    except Exception as exc:
        raise DownloadRecusado(f"arquivo não é uma imagem válida ({type(exc).__name__})") from exc

    return ImagemBaixada(
        conteudo=dados,
        mime=_MIME[formato],
        formato=formato,
        largura=largura,
        altura=altura,
        sha256=hashlib.sha256(dados).hexdigest(),
        url_final=atual,
    )
