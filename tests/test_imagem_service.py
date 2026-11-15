import pytest

from services import imagem_service as IS
from services.image_providers import ImageSelector, ImagensUsadasMemoria, SemVisao
from helpers_criacao import receita_valida
from helpers_imagens import ProvedorFalso, VisaoFalsa, baixador, candidata


def test_escolhe_capa_a_partir_do_conteudo():
    prov = ProvedorFalso(por_consulta={"brigadeiro bowl": [candidata("5")]})
    vis = VisaoFalsa()
    r = IS.escolher_capa(receita_valida(), selector=ImageSelector([prov]), visao=vis, baixar=baixador())
    assert r.status == "stock" and r.cover["mode"] == "stock"
    assert "Brigadeiro de colher cremoso" in vis.chamadas[0][2] and "brigadeiros-e-docinhos" in vis.chamadas[0][2]


def test_sem_visao_configurada_cai_em_generate_com_o_prompt_da_receita():
    r = IS.escolher_capa(receita_valida(), selector=ImageSelector([ProvedorFalso(padrao=[candidata("1")])]), baixar=baixador())
    assert r.status == "generate" and r.cover == {"mode": "generate", "imagePrompt": receita_valida()["prompt_imagem"]}
    assert any("IMG-04" in p for p in r.pendencias)


def test_exige_termos_e_prompt():
    for faltando in ("termos_busca_imagem", "prompt_imagem"):
        c = receita_valida(); c[faltando] = [] if faltando.startswith("termos") else ""
        with pytest.raises(ValueError):
            IS.escolher_capa(c, selector=ImageSelector([ProvedorFalso()]))


def test_modulo_nao_tem_mais_armazenamento_local_nem_sqlite():
    import importlib, services.image_providers as P
    for nome in ("buscar_imagem_capa", "buscar_imagem_noticia", "buscar_imagem_receita"):
        assert not hasattr(IS, nome)
    for nome in ("registrar_imagem", "listar_imagens_registradas", "baixar_e_processar_imagem", "DEFAULT_STORAGE_DIR"):
        assert not hasattr(P, nome)
    with pytest.raises(ImportError):
        importlib.import_module("services.image_providers.database")
    with pytest.raises(ImportError):
        importlib.import_module("services.pixabay_service")
