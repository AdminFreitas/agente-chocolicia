import pytest

from services.image_providers import classificar_licenca


@pytest.mark.parametrize("provedor,nome,codigo,atrib", [
    ("openverse", "CC0 1.0", "cc0", False), ("wikimedia", "CC0", "cc0", False), ("openverse", "CC PDM 1.0", "pdm", False),
    ("wikimedia", "Public domain", "pdm", False), ("openverse", "CC BY 4.0", "cc-by", True), ("wikimedia", "CC BY 3.0", "cc-by", True),
    ("wikimedia", "CC-BY-4.0", "cc-by", True), ("pixabay", "Pixabay Content License", "propria", False),
    ("pixabay", "Pixabay License", "propria", False), ("pexels", "Pexels License", "propria", False),
])
def test_licencas_aceitas(provedor, nome, codigo, atrib):
    r = classificar_licenca(provedor, nome)
    assert r.aceita and r.codigo == codigo and r.exige_atribuicao is atrib


@pytest.mark.parametrize("provedor,nome", [
    ("wikimedia", "CC BY-SA 4.0"), ("openverse", "CC BY-SA 2.0"), ("openverse", "CC BY-NC 4.0"), ("openverse", "CC BY-ND 4.0"),
    ("wikimedia", "CC BY-NC-SA 3.0"), ("wikimedia", "CC-BY-SA-4.0"), ("openverse", "CC BY-NC-ND 2.0"),
    ("wikimedia", "All rights reserved"), ("wikimedia", "Todos os direitos reservados"), ("wikimedia", "Copyrighted free use"),
    ("pixabay", "Pexels License"),  # licença própria só vale para o provedor dono
    ("pexels", "Pixabay Content License"), ("wikimedia", "GFDL"), ("wikimedia", "Attribution"), ("wikimedia", ""), ("wikimedia", None),
    ("openverse", "licença qualquer"),
])
def test_licencas_recusadas(provedor, nome):
    r = classificar_licenca(provedor, nome)
    assert not r.aceita and r.codigo == "recusada" and r.motivo
