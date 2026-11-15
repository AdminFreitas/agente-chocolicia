"""
tests/test_image_providers_real.py — Testes de integração com os bancos de imagens REAIS.

Ficam FORA da execução padrão (marcador `real`). Para rodar:
    RUN_REAL_IMAGE_TESTS=1 python -m pytest tests/test_image_providers_real.py -v
Só buscam e conferem metadados. Não baixam, não gravam em disco e não usam banco
(o armazenamento local e o SQLite foram removidos). Provedores sem chave são pulados.
"""

import pytest

from services.image_providers import (
    OpenverseProvider, PexelsProvider, PixabayProvider, WikimediaProvider, classificar_licenca,
)

pytestmark = pytest.mark.real

TERMOS = ["chocolate truffles plate", "brigadeiro bowl", "chocolate cake slice"]


@pytest.mark.parametrize("cls", [PixabayProvider, PexelsProvider, OpenverseProvider, WikimediaProvider])
def test_busca_real_devolve_metadados_basicos(cls):
    prov = cls()
    if not prov.is_available():
        pytest.skip(f"{prov.name} não configurado")
    candidatas = []
    for termo in TERMOS:
        candidatas = prov.search(query=termo, limit=5, min_width=1280, lang="en")
        if candidatas:
            break
    if not candidatas:
        pytest.skip(f"{prov.name} sem resultado para os termos de teste")
    c = candidatas[0]
    assert c.original_image_url.startswith("https://") and c.provider == prov.name
    assert c.width >= 1280 or c.width == 0
    # a decisão de licença é central: o resultado deve ser classificável
    assert classificar_licenca(c.provider, c.license, c.license_url).codigo
