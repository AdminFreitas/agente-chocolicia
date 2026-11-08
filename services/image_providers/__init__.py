"""
services/image_providers/__init__.py — Ponto de entrada unificado para os quatro
bancos de imagens integrados no Chocolícia: Pixabay, Pexels, Openverse e Wikimedia.
"""

from services.image_providers.base import ImageProvider, StandardImageResult
from services.image_providers.pixabay import PixabayProvider
from services.image_providers.pexels import PexelsProvider
from services.image_providers.openverse import OpenverseProvider
from services.image_providers.wikimedia import WikimediaProvider
from services.image_providers.storage import baixar_e_processar_imagem
from services.image_providers.database import registrar_imagem, listar_imagens_registradas
from services.image_providers.selector import ImageSelector

_default_selector = ImageSelector()


def buscar_e_armazenar_imagem(
    titulo: str,
    categoria: str = "",
    subcategoria: str = "",
    ingredientes: list = None,
    min_width: int = 1280,
    baixar: bool = True,
):
    """Atalho de alto nível para buscar, selecionar e armazenar imagem com metadados."""
    return _default_selector.buscar_e_armazenar_imagem(
        titulo=titulo,
        categoria=categoria,
        subcategoria=subcategoria,
        ingredientes=ingredientes,
        min_width=min_width,
        baixar=baixar,
    )


__all__ = [
    "ImageProvider",
    "StandardImageResult",
    "PixabayProvider",
    "PexelsProvider",
    "OpenverseProvider",
    "WikimediaProvider",
    "ImageSelector",
    "baixar_e_processar_imagem",
    "registrar_imagem",
    "listar_imagens_registradas",
    "buscar_e_armazenar_imagem",
]

