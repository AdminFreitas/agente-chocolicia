"""
services/image_providers/base.py — Interface base e modelo de dados padronizado
para provedores de imagens externas no projeto Chocolícia.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class StandardImageResult:
    """Modelo de dados canônico para resultados de imagens de qualquer provedor."""
    provider: str                      # "pixabay" | "openverse" | "pexels" | "wikimedia"
    provider_image_id: str             # ID único no provedor
    title: str                         # Título ou descrição da imagem
    original_image_url: str            # URL direta para download da imagem
    original_page_url: str             # Página de origem no banco de imagens
    photographer: str                  # Nome do autor/fotógrafo
    photographer_url: Optional[str]    # Perfil do fotógrafo
    license: str                       # Nome da licença (ex: CC0, Pixabay License, Pexels License)
    license_url: Optional[str]         # Link oficial da licença
    attribution_text: str              # Texto de atribuição recomendado (ex: "Foto: Fulano via Pexels")
    width: int                         # Largura em pixels
    height: int                        # Altura em pixels
    aspect_ratio: float = 0.0          # Proporção width / height
    is_horizontal: bool = True         # Se a imagem é horizontal/paisagem
    is_commercial_friendly: bool = True # Se a licença permite uso comercial
    tags: List[str] = field(default_factory=list)
    search_query: str = ""             # Termo que encontrou a imagem
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.height > 0:
            self.aspect_ratio = round(self.width / self.height, 2)
            self.is_horizontal = self.width >= self.height


class ImageProvider(ABC):
    """Classe base abstrata para todos os adaptadores de bancos de imagens."""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se o provedor está configurado e disponível para uso."""
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 10,
        min_width: int = 1280,
        lang: str = "pt",
        **kwargs
    ) -> List[StandardImageResult]:
        """
        Executa a busca de imagens culinárias no provedor.
        Retorna lista de StandardImageResult ordenados por relevância/qualidade.
        """
        pass

