"""
services/image_providers/storage.py — Download seguro com proteção SSRF,
validação de tipo e processamento com Pillow para o Chocolícia.
"""

import io
import ipaddress
import os
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import uuid
import httpx
from PIL import Image

# Configurações de armazenamento e segurança
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
DOWNLOAD_TIMEOUT = 15

# Diretório padrão onde as imagens tratadas serão salvas no agente
DEFAULT_STORAGE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "output", "imagens", "receitas")
)


def _verificar_ssrf(url: str) -> None:
    """
    Protege contra ataques de SSRF (Server-Side Request Forgery).
    Bloqueia URLs não-HTTPS, IPs privados, locais, loopback e reservados.
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
        # Resolve todos os IPs associados ao hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                raise PermissionError(f"Acesso bloqueado a IP privado/reservado ({ip_str}) para o host {hostname}")
    except socket.gaierror as e:
        raise ValueError(f"Não foi possível resolver o hostname {hostname}: {e}")


def baixar_e_processar_imagem(
    url: str,
    slug: str = "receita",
    diretorio_destino: Optional[str] = None,
    largura_maxima: int = 1920,
    qualidade_webp: int = 88,
) -> Dict[str, Any]:
    """
    Baixa uma imagem de forma segura, valida o formato com Pillow,
    redimensiona de forma proporcional se exceder largura_maxima,
    converte para WebP e armazena no diretório de destino.

    Retorna um dicionário com:
    - stored_path: caminho absoluto no disco
    - stored_url: URL relativa para referência
    - width: largura final
    - height: altura final
    - size_bytes: tamanho final em bytes
    - format: formato gerado ("WEBP")
    """
    _verificar_ssrf(url)

    diretorio = diretorio_destino or os.getenv("IMAGE_STORAGE_DIR") or DEFAULT_STORAGE_DIR
    os.makedirs(diretorio, exist_ok=True)

    headers = {
        "User-Agent": "ChocoliciaAgent/1.0 (+https://chocolicia.com)",
        "Accept": "image/webp,image/jpeg,image/png,image/*",
    }

    # Download em streaming com controle de tamanho máximo
    # Timeout explícito para connect + read + write para evitar travamentos
    _timeout = httpx.Timeout(connect=10.0, read=DOWNLOAD_TIMEOUT, write=10.0, pool=5.0)
    buffer = bytearray()
    with httpx.stream("GET", url, headers=headers, timeout=_timeout, follow_redirects=True) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"Erro ao baixar imagem: HTTP {resp.status_code}")

        for chunk in resp.iter_bytes(chunk_size=65536):
            buffer.extend(chunk)
            if len(buffer) > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"Imagem excede o limite máximo permitido de {MAX_DOWNLOAD_BYTES // (1024*1024)} MB")

    # Validação e processamento com Pillow
    try:
        img_bytes = bytes(buffer)
        image = Image.open(io.BytesIO(img_bytes))
        formato_original = image.format
        if formato_original not in ALLOWED_FORMATS:
            raise ValueError(f"Formato de imagem não suportado: {formato_original}. Permitidos: {ALLOWED_FORMATS}")

        # Converte para RGB se necessário (ex: PNG com RGBA ou paletizado)
        if image.mode in ("RGBA", "LA", "P"):
            fundo_branco = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            fundo_branco.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = fundo_branco
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Redimensionamento proporcional se necessário
        largura_atual, altura_atual = image.size
        if largura_atual > largura_maxima:
            nova_altura = int(altura_atual * (largura_maxima / largura_atual))
            image = image.resize((largura_maxima, nova_altura), Image.Resampling.LANCZOS)
            largura_atual, altura_atual = image.size

        # Nome seguro baseado em slug e hash
        nome_arquivo = f"{slug[:40]}_{uuid.uuid4().hex[:10]}.webp"
        caminho_final = os.path.join(diretorio, nome_arquivo)

        # Salva em WebP otimizado
        image.save(caminho_final, "WEBP", quality=qualidade_webp, method=6)
        tamanho_final = os.path.getsize(caminho_final)

        stored_rel_url = f"/imagens/receitas/{nome_arquivo}"

        return {
            "stored_path": caminho_final,
            "stored_url": stored_rel_url,
            "filename": nome_arquivo,
            "width": largura_atual,
            "height": altura_atual,
            "size_bytes": tamanho_final,
            "format": "WEBP",
            "original_format": formato_original,
        }

    except Exception as e:
        raise RuntimeError(f"Falha ao validar ou processar imagem: {e}")
