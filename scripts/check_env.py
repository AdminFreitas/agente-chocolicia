"""Script auxiliar: verifica variáveis de ambiente sem expor credenciais."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()

keys = [
    "PIXABAY_API_KEY",
    "PEXELS_API_KEY",
    "OPENVERSE_ENABLED",
    "WIKIMEDIA_ENABLED",
    "PIXABAY_ENABLED",
    "PEXELS_ENABLED",
]
for k in keys:
    v = os.getenv(k, "")
    if v:
        print(f"{k}: SET ({len(v)} chars)")
    else:
        print(f"{k}: NOT SET")

