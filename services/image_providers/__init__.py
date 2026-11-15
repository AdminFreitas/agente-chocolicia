"""
services/image_providers/__init__.py — Bancos de imagens do Chocolícia (Pixabay,
Pexels, Openverse e Wikimedia) e a seleção da capa. O agente só busca e verifica
(em memória); não armazena imagem nem registra proveniência localmente.
"""

from services.image_providers.base import ImageProvider, StandardImageResult, user_agent
from services.image_providers.licencas import Licenca, classificar_licenca
from services.image_providers.openverse import OpenverseProvider
from services.image_providers.pexels import PexelsProvider
from services.image_providers.pixabay import PixabayProvider
from services.image_providers.selector import (
    ImagensUsadas,
    ImagensUsadasMemoria,
    ImageSelector,
    ResultadoImagem,
    ResultadoVisao,
    SemVisao,
    VerificadorVisao,
    VisaoIndisponivel,
)
from services.image_providers.storage import DownloadRecusado, ImagemBaixada, baixar_imagem_em_memoria
from services.image_providers.wikimedia import WikimediaProvider

__all__ = [
    "ImageProvider", "StandardImageResult", "user_agent",
    "Licenca", "classificar_licenca",
    "PixabayProvider", "PexelsProvider", "OpenverseProvider", "WikimediaProvider",
    "ImageSelector", "ResultadoImagem", "ResultadoVisao", "VerificadorVisao", "SemVisao", "VisaoIndisponivel",
    "ImagensUsadas", "ImagensUsadasMemoria",
    "baixar_imagem_em_memoria", "ImagemBaixada", "DownloadRecusado",
]
