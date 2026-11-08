"""
scripts/run_tests_completo.py — Executa a bateria completa de testes dos bancos de imagens
e verifica regressão da compatibilidade do pipeline existente.
"""
import os
import sys
import traceback
from pathlib import Path

# Raiz do projeto
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("FASE 0 — VERIFICAÇÃO DE IMPORTS E DEPENDÊNCIAS")
print("=" * 60)

try:
    import httpx; print(f"  httpx {httpx.__version__} OK")
except ImportError as e:
    print(f"  ERRO: httpx não instalado: {e}"); sys.exit(1)

try:
    from PIL import Image; print(f"  Pillow OK")
except ImportError as e:
    print(f"  ERRO: Pillow não instalado: {e}"); sys.exit(1)

try:
    from services.image_providers.base import ImageProvider, StandardImageResult
    from services.image_providers.pixabay import PixabayProvider
    from services.image_providers.pexels import PexelsProvider
    from services.image_providers.openverse import OpenverseProvider
    from services.image_providers.wikimedia import WikimediaProvider
    from services.image_providers.storage import baixar_e_processar_imagem
    from services.image_providers.database import registrar_imagem, listar_imagens_registradas
    from services.image_providers.selector import ImageSelector
    from services.image_providers import buscar_e_armazenar_imagem
    print("  Todos os módulos de image_providers importados OK")
except Exception as e:
    print(f"  ERRO nos imports: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from services.imagem_service import buscar_imagem_capa, buscar_imagem_noticia, buscar_imagem_receita
    print("  imagem_service importado OK (compatibilidade legada)")
except Exception as e:
    print(f"  ERRO ao importar imagem_service: {e}")
    traceback.print_exc()
    sys.exit(1)


print("\n" + "=" * 60)
print("FASE 1 — TESTES INDIVIDUAIS POR PROVEDOR")
print("=" * 60)

DIR_TESTES = str(ROOT / "output" / "imagens" / "testes")
os.makedirs(DIR_TESTES, exist_ok=True)

resultados = {}

def testar_provedor(provider, termo_pt, termo_en):
    nome = provider.name.upper()
    print(f"\n--- {nome} ---")

    # 1. Disponibilidade
    disponivel = provider.is_available()
    print(f"  [1] Disponível: {disponivel}")
    if not disponivel:
        print(f"  → Status: IMPLEMENTADO, MAS NÃO CONFIGURADO")
        return "IMPLEMENTADO, MAS NÃO CONFIGURADO", None

    # 2. Busca com termo em PT
    print(f"  [2] Buscando: '{termo_pt}'")
    try:
        resultados_pt = provider.search(query=termo_pt, limit=5, min_width=1280)
        print(f"  [3] Resultados PT: {len(resultados_pt)}")
    except Exception as e:
        print(f"  [3] Falha na busca PT: {e}")
        resultados_pt = []

    # 3. Fallback em EN se necessário
    candidatos = resultados_pt
    if not candidatos:
        print(f"  [4] Tentando fallback EN: '{termo_en}'")
        try:
            candidatos = provider.search(query=termo_en, limit=5, min_width=1280)
            print(f"  [4] Resultados EN: {len(candidatos)}")
        except Exception as e:
            print(f"  [4] Falha no fallback EN: {e}")
            candidatos = []

    if not candidatos:
        print(f"  → Status: CONECTADO, MAS SEM IMAGEM VÁLIDA NO TESTE")
        return "CONECTADO, MAS SEM IMAGEM VÁLIDA NO TESTE", None

    # 4. Validação de metadados
    img = candidatos[0]
    print(f"  [5] Metadados: ID={img.provider_image_id} | {img.width}x{img.height}")
    print(f"  [6] Licença: {img.license}")
    print(f"      Atribuição: {img.attribution_text[:80]}")
    assert img.original_image_url, "URL vazia"
    assert img.license, "Licença ausente"

    # 5. Download + processamento + armazenamento
    print(f"  [7-9] Baixando imagem real...")
    try:
        proc = baixar_e_processar_imagem(
            url=img.original_image_url,
            slug=f"teste-{provider.name}",
            diretorio_destino=DIR_TESTES,
        )
        tamanho_kb = proc["size_bytes"] // 1024
        print(f"  [7-9] OK: {proc['filename']} | {proc['width']}x{proc['height']} | {tamanho_kb} KB | {proc['format']}")

        # 6. Verifica existência física
        assert os.path.exists(proc["stored_path"]), "Arquivo não encontrado no disco"
        assert os.path.getsize(proc["stored_path"]) > 1000, "Arquivo vazio"
        print(f"  [10] Recuperação do arquivo confirmada ({tamanho_kb} KB)")

        # 7. Registro no banco
        reg_id = registrar_imagem(
            provider=img.provider,
            provider_image_id=img.provider_image_id,
            original_image_url=img.original_image_url,
            original_page_url=img.original_page_url,
            stored_image_url=proc["stored_url"],
            stored_path=proc["stored_path"],
            photographer=img.photographer,
            license=img.license,
            license_url=img.license_url,
            attribution_text=img.attribution_text,
            search_query=termo_pt,
            width=proc["width"],
            height=proc["height"],
            image_status="test_validated",
        )
        print(f"  [11] Registro SQLite ID={reg_id}")

        dados = {
            "termo": termo_pt,
            "hits_pt": len(resultados_pt),
            "hits_fallback": len(candidatos) if not resultados_pt else 0,
            "id": img.provider_image_id,
            "fotografo": img.photographer,
            "licenca": img.license,
            "dimensoes_original": f"{img.width}x{img.height}",
            "dimensoes_final": f"{proc['width']}x{proc['height']}",
            "tamanho_kb": tamanho_kb,
            "formato": proc["format"],
            "arquivo": proc["filename"],
            "url_armazenada": proc["stored_url"],
            "url_pagina": img.original_page_url,
            "atribuicao": img.attribution_text,
            "db_id": reg_id,
        }
        print(f"  → Status: FUNCIONANDO E VALIDADO")
        return "FUNCIONANDO E VALIDADO", dados

    except Exception as e:
        print(f"  Falha no download/processamento: {e}")
        traceback.print_exc()
        return "CONFIGURADO, MAS COM FALHA NO DOWNLOAD", None


# Configurações por provedor
config_provedores = [
    (PixabayProvider(),   "Bolo de cenoura com chocolate", "carrot cake chocolate"),
    (PexelsProvider(),    "Brigadeiro gourmet",            "chocolate brigadeiro"),
    (OpenverseProvider(), "Torta de limão merengue",       "lemon meringue pie"),
    (WikimediaProvider(), "Trufa de chocolate",            "chocolate truffle"),
]

status_final = {}
detalhes_testes = {}

for provider, termo_pt, termo_en in config_provedores:
    try:
        status, dados = testar_provedor(provider, termo_pt, termo_en)
        status_final[provider.name] = status
        detalhes_testes[provider.name] = dados
    except Exception as e:
        print(f"  ERRO INESPERADO em {provider.name}: {e}")
        traceback.print_exc()
        status_final[provider.name] = f"ERRO: {e}"
        detalhes_testes[provider.name] = None


print("\n" + "=" * 60)
print("FASE 2 — TESTE DO SELETOR INTEGRADO (ImageSelector)")
print("=" * 60)

try:
    selector = ImageSelector()
    res = selector.buscar_e_armazenar_imagem(
        titulo="Bolo de Aniversário Festivo",
        categoria="Bolos",
        subcategoria="Festas",
    )
    if res:
        print(f"  Seletor OK: provedor={res['provider']} | autor={res.get('author')}")
        print(f"  Arquivo: {res.get('stored_path')}")
        print(f"  Dimensões: {res.get('final_width')}x{res.get('final_height')}")
        status_final["seletor_integrado"] = "FUNCIONANDO E VALIDADO"
    else:
        print("  Seletor retornou None — sem imagem disponível")
        status_final["seletor_integrado"] = "SEM RESULTADO"
except Exception as e:
    print(f"  Seletor falhou: {e}")
    traceback.print_exc()
    status_final["seletor_integrado"] = f"ERRO: {e}"


print("\n" + "=" * 60)
print("FASE 3 — REGRESSÃO: COMPATIBILIDADE DO PIPELINE LEGADO")
print("=" * 60)

# 3a. buscar_imagem_capa (assinatura original do pipeline)
print("\n  3a. Testando buscar_imagem_capa(titulo, tema, categoria)...")
try:
    res_capa = buscar_imagem_capa(
        titulo="Brigadeiro Gourmet",
        tema="Docinhos",
        categoria="Chocolates",
    )
    if res_capa:
        print(f"  OK: imagem_url={res_capa.get('imagem_url', '')[:60]}...")
        print(f"      imagem_fonte={res_capa.get('imagem_fonte')}")
        print(f"      imagem_autor={res_capa.get('imagem_autor')}")
        status_final["regressao_capa"] = "OK"
    else:
        print("  Retornou None — sem imagem")
        status_final["regressao_capa"] = "SEM RESULTADO"
except Exception as e:
    print(f"  FALHA: {e}")
    traceback.print_exc()
    status_final["regressao_capa"] = f"ERRO: {e}"

# 3b. buscar_imagem_receita (nova função)
print("\n  3b. Testando buscar_imagem_receita(titulo, categoria, subcategoria)...")
try:
    res_receita = buscar_imagem_receita(
        titulo="Pavê de Chocolate",
        categoria="Sobremesas",
        subcategoria="Pavês",
    )
    if res_receita:
        print(f"  OK: provider={res_receita.get('provider')} | mode={res_receita.get('mode')}")
        status_final["regressao_receita"] = "OK"
    else:
        print("  Retornou None")
        status_final["regressao_receita"] = "SEM RESULTADO"
except Exception as e:
    print(f"  FALHA: {e}")
    traceback.print_exc()
    status_final["regressao_receita"] = f"ERRO: {e}"

# 3c. Verifica imagem_service.py.bak (mecanismo legado preservado)
bak_path = str(ROOT / "services" / "imagem_service.py.bak")
if os.path.exists(bak_path):
    print(f"\n  3c. Backup do mecanismo legado preservado: imagem_service.py.bak")
    status_final["backup_legado"] = "PRESERVADO"
else:
    print(f"\n  3c. AVISO: imagem_service.py.bak não encontrado")
    status_final["backup_legado"] = "NÃO ENCONTRADO"

# 3d. Verifica pipeline importa a função esperada
print("\n  3d. Verificando import do pipeline gerar_artigos.py...")
try:
    pipeline_path = ROOT / "pipeline" / "gerar_artigos.py"
    if pipeline_path.exists():
        conteudo = pipeline_path.read_text(encoding="utf-8")
        if "buscar_imagem_capa" in conteudo:
            print("  OK: pipeline importa buscar_imagem_capa")
            status_final["regressao_pipeline"] = "OK"
        else:
            print("  AVISO: buscar_imagem_capa não encontrado no pipeline")
            status_final["regressao_pipeline"] = "AVISO"
    else:
        print(f"  gerar_artigos.py não encontrado em {pipeline_path}")
        status_final["regressao_pipeline"] = "NÃO ENCONTRADO"
except Exception as e:
    print(f"  ERRO: {e}")
    status_final["regressao_pipeline"] = f"ERRO: {e}"


# 3e. Verifica banco SQLite
print("\n  3e. Consultando registros do banco SQLite...")
try:
    registros = listar_imagens_registradas(limite=5)
    print(f"  Últimos {len(registros)} registros na tabela imagens_banco:")
    for r in registros:
        print(f"    ID={r['id']} | {r['provider']} | {r['search_query']} | {r['image_status']}")
    status_final["banco_sqlite"] = f"{len(registros)} registros"
except Exception as e:
    print(f"  ERRO: {e}")
    status_final["banco_sqlite"] = f"ERRO: {e}"


print("\n\n" + "=" * 60)
print("RESUMO FINAL")
print("=" * 60)
for k, v in status_final.items():
    simbolo = "✓" if "OK" in v or "VALIDADO" in v or "PRESERVADO" in v or "registros" in v else ("~" if "CONECTADO" in v or "SEM" in v or "NÃO ENCONTRADO" in v else "✗")
    print(f"  {simbolo} {k:<30}: {v}")

print("\n[CONCLUÍDO]")

# Exporta resultado para arquivo de saída
import json
saida = ROOT / "output" / "test_results_completo.json"
os.makedirs(saida.parent, exist_ok=True)
with open(saida, "w", encoding="utf-8") as f:
    json.dump({
        "status_final": status_final,
        "detalhes": {k: v for k, v in detalhes_testes.items() if v},
    }, f, ensure_ascii=False, indent=2)
print(f"\nResultados exportados: {saida}")

