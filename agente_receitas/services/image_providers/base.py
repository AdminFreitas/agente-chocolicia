"""
services/image_providers/base.py — Interface base e modelo de dados padronizado
dos provedores de imagens (docs/01 §8.2; docs/08 §4.9).

Regras desta camada:
- O agente NÃO armazena imagem (nem em disco, nem em banco): só busca e verifica.
  O site baixa, trata e armazena (docs/06 §7.1).
- `IMAGE_HOSTS` lista os hosts de IMAGEM de cada provedor, para o filtro IMG-03.
  PENDENTE (docs/06 §18): conferir com os termos de cada provedor e manter igual
  à lista do servidor do site. Os valores abaixo NÃO foram verificados.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def user_agent() -> str:
    """User-Agent honesto do Chocolícia (docs/02 §11). Usa SITE_BASE_URL, sem domínio fixo no código."""
    site = os.getenv("SITE_BASE_URL", "").strip()
    return f"ChocoliciaAgent/1.0 (+{site})" if site else "ChocoliciaAgent/1.0"


@dataclass
class StandardImageResult:
    """Modelo de dados canônico para resultados de imagens de qualquer provedor."""
    provider: str                      # "pixabay" | "openverse" | "pexels" | "wikimedia"
    provider_image_id: str             # ID único no provedor
    title: str                         # Título ou descrição da imagem
    original_image_url: str            # URL direta da imagem
    original_page_url: str             # Página de origem no banco de imagens
    photographer: str                  # Autor
    photographer_url: Optional[str]    # Perfil do autor
    license: str                       # Nome da licença como veio do provedor
    license_url: Optional[str]         # Link oficial da licença
    attribution_text: str              # Texto de atribuição (ex.: "Foto: Fulano via Pexels")
    width: int                         # Largura em pixels (0 = desconhecida)
    height: int                        # Altura em pixels (0 = desconhecida)
    aspect_ratio: float = 0.0
    is_horizontal: bool = True
    # Informativo. A decisão de licença é de services/image_providers/licencas.py.
    is_commercial_friendly: bool = True
    tags: List[str] = field(default_factory=list)
    search_query: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if self.height > 0:
            self.aspect_ratio = round(self.width / self.height, 2)
            self.is_horizontal = self.width >= self.height


class ImageProvider(ABC):
    """Classe base abstrata dos adaptadores de bancos de imagens."""

    # Hosts de imagem do provedor (IMG-03). Vazio = o provedor não contribui com hosts.
    IMAGE_HOSTS: Tuple[str, ...] = ()

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se o provedor está configurado e disponível."""

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 10,
        min_width: int = 1280,
        lang: str = "pt",
        **kwargs,
    ) -> List[StandardImageResult]:
        """Busca imagens. Devolve candidatas; quem decide é o seletor (licença, largura, host)."""
