"""
tests/test_image_providers_real.py — Testes reais de integração dos quatro bancos de imagens.
Executa buscas, valida metadados, baixa, processa e armazena imagens de teste reais.
"""

import os
import sys
from pathlib import Path

# Adiciona o diretório raiz ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from services.image_providers.pixabay import PixabayProvider
from services.image_providers.pexels import PexelsProvider
from services.image_providers.openverse import OpenverseProvider
from services.image_providers.wikimedia import WikimediaProvider
from services.image_providers.storage import baixar_e_processar_imagem
from services.image_providers.database import registrar_imagem, listar_imagens_registradas
from services.image_providers.selector import ImageSelector


TERMOS_TESTE = [
    ("Bolo de cenoura com chocolate", "Bolos"),
    ("Brigadeiro", "Docinhos"),
    ("Torta de limão", "Tortas"),
    ("Bolo de aniversário", "Bolos"),
    ("Trufa de chocolate", "Chocolates"),
]


def testar_provedor_individual(provider, termo="Bolo de cenoura com chocolate"):
    print(f"\n==========================================")
    print(f"Testando Provedor: {provider.name.upper()}")
    print(f"==========================================")
    
    # 1. Configuração e disponibilidade
    disponivel = provider.is_available()
    print(f"1. Configuração/Disponibilidade: {'Ativo e configurado' if disponivel else 'Não disponível'}")
    if not disponivel:
        return "IMPLEMENTADO, MAS NÃO CONFIGURADO", None

    # 2 e 3. Comunicação com a API e Pesquisa por uma receita real
    print(f"2 e 3. Pesquisando '{termo}' na API...")
    try:
        resultados = provider.search(query=termo, limit=5, min_width=1280)
    except Exception as e:
        print(f"Erro na comunicação com a API: {e}")
        return "CONFIGURADO, MAS COM FALHA", None

    print(f"4. Resultados encontrados: {len(resultados)}")
    if not resultados:
        # Tenta em inglês como fallback
        print("Tentando fallback de termo em inglês...")
        resultados = provider.search(query="chocolate cake", limit=5, min_width=1280)
        print(f"Resultados com fallback: {len(resultados)}")
        if not resultados:
            return "CONECTADO, MAS SEM IMAGEM VÁLIDA NO TESTE", None

    primeiro = resultados[0]
    
    # 5. Validação dos metadados
    print(f"5. Metadados: ID={primeiro.provider_image_id} | Fotógrafo={primeiro.photographer} | Dimensões={primeiro.width}x{primeiro.height}")
    assert primeiro.original_image_url, "URL da imagem original vazia"
    assert primeiro.photographer, "Fotógrafo não identificado"

    # 6. Identificação de licença
    print(f"6. Licença: {primeiro.license} | Atribuição: {primeiro.attribution_text}")
    assert primeiro.license, "Licença não informada"

    # 7, 8 e 9. Download, processamento e armazenamento
    print(f"7, 8 e 9. Baixando e processando 1 imagem real...")
    try:
        dir_teste = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output", "imagens", "testes"))
        slug_teste = f"teste-{provider.name}"
        proc = baixar_e_processar_imagem(primeiro.original_image_url, slug=slug_teste, diretorio_destino=dir_teste)
        print(f"Download e processamento OK: {proc['filename']} ({proc['width']}x{proc['height']}, {proc['size_bytes']} bytes, formato {proc['format']})")
        assert os.path.exists(proc["stored_path"]), "Arquivo não encontrado no disco"

        # Registra no banco
        reg_id = registrar_imagem(
            provider=primeiro.provider,
            provider_image_id=primeiro.provider_image_id,
            original_image_url=primeiro.original_image_url,
            original_page_url=primeiro.original_page_url,
            stored_image_url=proc["stored_url"],
            stored_path=proc["stored_path"],
            photographer=primeiro.photographer,
            license=primeiro.license,
            license_url=primeiro.license_url,
            attribution_text=primeiro.attribution_text,
            search_query=termo,
            width=proc["width"],
            height=proc["height"],
            image_status="test_validated",
        )
        print(f"Registro no banco efetuado com ID: {reg_id}")

        # 10. Recuperação da imagem armazenada
        assert os.path.getsize(proc["stored_path"]) > 1000, "Arquivo gerado vazio ou corrompido"
        print(f"10. Recuperação confirmada com sucesso ({os.path.getsize(proc['stored_path'])} bytes lidos).")

        return "FUNCIONANDO E VALIDADO", {
            "termo": termo,
            "total_hits": len(resultados),
            "id": primeiro.provider_image_id,
            "fotografo": primeiro.photographer,
            "licenca": primeiro.license,
            "dimensoes": f"{proc['width']}x{proc['height']}",
            "arquivo": proc["filename"],
            "url_armazenada": proc["stored_url"],
        }

    except Exception as e:
        print(f"Falha no download/processamento: {e}")
        return "CONFIGURADO, MAS COM FALHA", None


def main():
    print("Iniciando testes reais dos bancos de imagens...\n")
    
    provedores = [
        PixabayProvider(),
        PexelsProvider(),
        OpenverseProvider(),
        WikimediaProvider(),
    ]

    status_final = {}
    detalhes_testes = {}

    termos_map = {
        "pixabay": "Bolo de cenoura com chocolate",
        "pexels": "Brigadeiro",
        "openverse": "Torta de limão",
        "wikimedia": "Trufa de chocolate",
    }

    for p in provedores:
        termo = termos_map.get(p.name, "Bolo de chocolate")
        resultado, dados = testar_provedor_individual(p, termo=termo)
        status_final[p.name] = resultado
        detalhes_testes[p.name] = dados

    print("\n\n==========================================")
    print("RESUMO DA VALIDAÇÃO DOS BANCOS DE IMAGENS")
    print("==========================================")
    for prov_name, st in status_final.items():
        print(f" - {prov_name.capitalize():<12}: {st}")

    print("\nTestando o Seletor Integrado (ImageSelector) em cascata...")
    selector = ImageSelector()
    res_seletor = selector.buscar_e_armazenar_imagem("Bolo de Aniversário Festivo", categoria="Bolos")
    assert res_seletor is not None, "Falha no seletor integrado"
    print(f"Seletor integrado OK: Imagem selecionada do provedor '{res_seletor['provider']}' por '{res_seletor['author']}'")
    print(f"Arquivo armazenado: {res_seletor.get('stored_path')}")

    print("\nTodos os testes foram executados!")
    return status_final, detalhes_testes


if __name__ == "__main__":
    main()

