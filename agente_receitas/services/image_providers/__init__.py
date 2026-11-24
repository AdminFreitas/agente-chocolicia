"""
services/image_providers/__init__.py — Bancos de imagens do Chocolícia (Pixabay,
Pexels, Openverse e Wikimedia) e a seleção da capa. O agente só busca e verifica
(em memória); não armazena imagem nem registra proveniência localmente.
"""

from agente_receitas.services.image_providers.base import ImageProvider, StandardImageResult, user_agent
from agente_receitas.services.image_providers.licencas import Licenca, classificar_licenca
from agente_receitas.services.image_providers.openverse import OpenverseProvider
from agente_receitas.services.image_providers.pexels import PexelsProvider
from agente_receitas.services.image_providers.pixabay import PixabayProvider
from agente_receitas.services.image_providers.selector import (
    ImagensUsadas,
    ImagensUsadasMemoria,
    ImageSelector,
    ResultadoImagem,
    ResultadoVisao,
    SemVisao,
    VerificadorVisao,
    VisaoIndisponivel,
)
from agente_receitas.services.image_providers.storage import DownloadRecusado, ImagemBaixada, baixar_imagem_em_memoria
from agente_receitas.services.image_providers.wikimedia import WikimediaProvider

__all__ = [
    "ImageProvider", "StandardImageResult", "user_agent",
    "Licenca", "classificar_licenca",
    "PixabayProvider", "PexelsProvider", "OpenverseProvider", "WikimediaProvider",
    "ImageSelector", "ResultadoImagem", "ResultadoVisao", "VerificadorVisao", "SemVisao", "VisaoIndisponivel",
    "ImagensUsadas", "ImagensUsadasMemoria",
    "baixar_imagem_em_memoria", "ImagemBaixada", "DownloadRecusado",
]
