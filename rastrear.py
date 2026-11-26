"""
rastrear.py — Rastreia quais arquivos .py são realmente importados
a partir do ponto de entrada (rodar_agente.py).

Uso: python rastrear.py

Limitações: ignora importações dinâmicas (__import__, importlib) e relativas
(from . import x). Trate a lista "NUNCA IMPORTADOS" como candidatos, não
como verdade absoluta.
"""
import ast
from pathlib import Path

raiz = Path(".").resolve()
vistos = set()


def resolver(mod):
    base = raiz / mod.replace(".", "/")
    for p in (base.with_suffix(".py"), base / "__init__.py"):
        if p.exists():
            return p
    return None


def visitar(arq):
    if arq in vistos:
        return
    vistos.add(arq)
    try:
        source = arq.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except Exception as e:
        print(f"  [AVISO] Não foi possível analisar {arq.relative_to(raiz)}: {e}")
        return
    for n in ast.walk(tree):
        mods = []
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
        for m in mods:
            r = resolver(m)
            if r:
                visitar(r)


ponto_de_entrada = raiz / "rodar_agente.py"
if not ponto_de_entrada.exists():
    print(f"ERRO: {ponto_de_entrada} não encontrado.")
    raise SystemExit(1)

visitar(ponto_de_entrada)

# Coleta todos os .py do projeto (exclui .venv, __pycache__, node_modules)
EXCLUIR = {".venv", "__pycache__", "node_modules", ".git", ".pytest_cache", "actions-runner", "_legado", "chocolicia-integracao", "api_conflito_backup"}
todos = {
    p.resolve()
    for p in raiz.rglob("*.py")
    if not any(parte in EXCLUIR for parte in p.parts)
}

usados = sorted(vistos)
nao_usados = sorted(todos - vistos)

print("=" * 60)
print(f"PONTO DE ENTRADA: rodar_agente.py")
print(f"USADOS ({len(usados)} arquivos):")
for p in usados:
    try:
        print(f"  {p.relative_to(raiz)}")
    except ValueError:
        print(f"  {p}")

print(f"\nNUNCA IMPORTADOS — candidatos a apagar ({len(nao_usados)} arquivos):")
for p in nao_usados:
    try:
        print(f"  {p.relative_to(raiz)}")
    except ValueError:
        print(f"  {p}")

print("=" * 60)
print("\nNOTA: importações relativas (from . import x) e dinâmicas não são detectadas.")
print("Revise manualmente antes de apagar qualquer arquivo.")
