"""Teste isolado — Pixabay apenas."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv; load_dotenv()

print("=== PIXABAY ===", flush=True)
from services.image_providers.pixabay import PixabayProvider
from services.image_providers.storage import baixar_e_processar_imagem
from services.image_providers.database import registrar_imagem

p = PixabayProvider()
print(f"Disponível: {p.is_available()}", flush=True)

r = p.search("carrot cake chocolate", limit=3, min_width=1280)
print(f"Hits: {len(r)}", flush=True)
if r:
    img = r[0]
    print(f"ID={img.provider_image_id} | {img.width}x{img.height} | {img.license}", flush=True)
    print(f"URL: {img.original_image_url[:60]}...", flush=True)

    dir_t = str(Path(__file__).parent.parent / "output" / "imagens" / "testes")
    os.makedirs(dir_t, exist_ok=True)
    proc = baixar_e_processar_imagem(img.original_image_url, slug="pixabay-ci", diretorio_destino=dir_t)
    print(f"Download OK: {proc['filename']} | {proc['size_bytes']//1024} KB | {proc['width']}x{proc['height']}", flush=True)
    reg = registrar_imagem(
        provider=img.provider, provider_image_id=img.provider_image_id,
        original_image_url=img.original_image_url, original_page_url=img.original_page_url,
        stored_image_url=proc["stored_url"], stored_path=proc["stored_path"],
        photographer=img.photographer, license=img.license, license_url=img.license_url,
        attribution_text=img.attribution_text, search_query="carrot cake chocolate",
        width=proc["width"], height=proc["height"], image_status="ci_validated",
    )
    print(f"SQLite ID: {reg}", flush=True)
    print("STATUS: FUNCIONANDO E VALIDADO", flush=True)
else:
    print("STATUS: CONECTADO, MAS SEM RESULTADO", flush=True)

