"""
tests/test_pixabay_service.py — Teste unitário para a integração do Pixabay no agente.
"""

import sys
import os

# Adiciona o diretório raiz ao PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from services.pixabay_service import buscar_pixabay, buscar_imagem_receita


def test_busca_direta_pixabay():
    print("\n--- Teste 1: Busca direta na API do Pixabay ---")
    hits = buscar_pixabay("bolo de chocolate", lang="pt", categoria="food")
    assert hits is not None, "Falha: hits retornou None"
    assert len(hits) > 0, "Falha: nenhum resultado retornado"
    print(f"Sucesso! Retornados {len(hits)} hits para 'bolo de chocolate'.")
    primeiro = hits[0]
    print(f"ID: {primeiro.get('id')} | Autor: {primeiro.get('user')} | Dimensões: {primeiro.get('imageWidth')}x{primeiro.get('imageHeight')}")
    print(f"Page URL: {primeiro.get('pageURL')}")
    print(f"Large URL: {primeiro.get('largeImageURL')}")


def test_busca_imagem_receita():
    print("\n--- Teste 2: Formatação de contrato para receita ---")
    receitas_teste = [
        ("Bolo Fofinho de Cenoura com Cobertura de Chocolate", "Bolos", "Bolo Caseiro"),
        ("Brigadeiro Gourmet Tradicional com Granulado Belga", "Docinhos", "Brigadeiros"),
        ("Torta Holandesa Cremosa", "Tortas", "Tortas Doces"),
    ]

    for titulo, cat, subcat in receitas_teste:
        res = buscar_imagem_receita(titulo, categoria=cat, subcategoria=subcat)
        assert res is not None, f"Falha ao buscar imagem para {titulo}"
        assert res["mode"] == "stock"
        assert res["provider"] == "pixabay"
        assert res["sourceImageUrl"].startswith("http")
        assert res["sourcePageUrl"].startswith("http")
        assert "Pixabay" in res["attributionText"]
        assert len(res["coverImageAlt"]) >= 8
        print(f"OK: '{titulo}' -> Imagem por '{res['author']}' | Alt: '{res['coverImageAlt']}' | URL: {res['sourceImageUrl'][:60]}...")


if __name__ == "__main__":
    test_busca_direta_pixabay()
    test_busca_imagem_receita()
    print("\nTodos os testes do Pixabay passaram com sucesso!")

