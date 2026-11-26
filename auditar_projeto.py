#!/usr/bin/env python3
"""
auditar_projeto.py - Auditoria e limpeza segura de projetos.

FASE 1 (escanear): somente LEITURA. Gera relatorio_limpeza.json e um resumo no terminal.
FASE 2 (limpar):   le o relatorio, pergunta item a item e MOVE para uma pasta de
                   quarentena (_quarentena_<data>). Exclusao definitiva so com --definitivo.

Uso:
    python3 auditar_projeto.py escanear --raiz /caminho/do/projeto
    python3 auditar_projeto.py limpar   --raiz /caminho/do/projeto

Somente biblioteca padrao do Python (sem pip install).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# CONFIGURACAO (ajuste aqui conforme o seu projeto)
# ----------------------------------------------------------------------------
ARQ_RELATORIO = "relatorio_limpeza.json"

# Nunca entramos nestas pastas.
PASTAS_IGNORADAS = {".git", "node_modules", ".venv", "venv", "env"}

# Lixo gerado automaticamente: risco BAIXO (pode ser recriado).
PASTAS_CACHE = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                ".ipynb_checkpoints", "htmlcov"}
ARQUIVOS_LIXO = {".DS_Store", "Thumbs.db", ".coverage"}

# Artefatos de build: revisar antes de remover.
PASTAS_BUILD = {"dist", "build"}

# Palavras que, como "pedaco" do nome, indicam arquivo provisorio/relatorio.
TOKENS_SUSPEITOS = {
    "relatorio", "relatorios", "relatório", "relatórios", "report", "reports",
    "resumo", "summary", "backup", "bkp", "bak", "copia", "cópia", "copy",
    "old", "antigo", "tmp", "temp", "rascunho", "draft",
}
EXTENSOES_SUSPEITAS = {".log", ".bak", ".old", ".tmp", ".orig", ".rej", ".swp"}

# Resquicio do projeto original: DigitalTech, digital-tech, digital_tech...
PADRAO_LEGADO = re.compile(r"digital[\s_\-]?tech", re.IGNORECASE)

PASTAS_DE_TESTE = {"tests", "test", "__tests__"}
EXTENSOES_TEXTO = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini",
                   ".cfg", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".sql",
                   ".sh", ".rst", ".xml"}
NOMES_TEXTO = {"Dockerfile", "Makefile", "README"}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}

LIMITE_LEITURA = 1_000_000      # 1 MB: nao lemos arquivos maiores para buscar texto
LIMITE_GRANDE = 5_000_000       # 5 MB: sinaliza arquivos grandes
CATEGORIAS_SEGURAS = {"CACHE", "LIXO", "VAZIA"}
CATEGORIAS_SO_INFORMATIVAS = {"LEGADO_CONTEUDO"}  # exigem EDITAR, nao excluir


@dataclass
class Item:
    caminho: str      # relativo a raiz
    tipo: str         # "arquivo" | "pasta"
    categoria: str
    risco: str        # "SEGURO" | "REVISAR"
    motivo: str
    tamanho: int


# ----------------------------------------------------------------------------
# Utilitarios
# ----------------------------------------------------------------------------
def tamanho(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*")
                   if f.is_file() and not f.is_symlink())
    except OSError:
        return 0


def humano(n: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n} B"


def nome_suspeito(nome: str) -> bool:
    p = Path(nome)
    if p.suffix.lower() in EXTENSOES_SUSPEITAS or nome.endswith("~"):
        return True
    tokens = re.split(r"[_\-.\s]+", p.stem.lower())
    return any(t in TOKENS_SUSPEITOS for t in tokens)


def eh_teste(nome: str) -> bool:
    n = nome.lower()
    stem = Path(n).stem
    return (stem.startswith(("test_", "teste_", "test-", "teste-"))
            or stem.endswith(("_test", "_teste"))
            or ".test." in n or ".spec." in n)


def eh_texto(p: Path) -> bool:
    return (p.suffix.lower() in EXTENSOES_TEXTO or p.name in NOMES_TEXTO) \
        and p.name not in LOCKFILES


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


# ----------------------------------------------------------------------------
# FASE 1 - escanear (somente leitura)
# ----------------------------------------------------------------------------
def escanear(raiz: Path) -> None:
    itens: list[Item] = []
    ocorrencias: list[dict] = []
    por_tamanho: dict[int, list[Path]] = defaultdict(list)
    testes_organizados = 0
    ignorar_arquivos = {ARQ_RELATORIO, Path(__file__).name}

    def add(p: Path, categoria: str, risco: str, motivo: str) -> None:
        itens.append(Item(
            caminho=p.relative_to(raiz).as_posix(),
            tipo="pasta" if p.is_dir() else "arquivo",
            categoria=categoria, risco=risco, motivo=motivo, tamanho=tamanho(p),
        ))

    for atual, dirs, arquivos in os.walk(raiz, followlinks=False):
        atual_p = Path(atual)

        # Pasta completamente vazia
        if atual_p != raiz and not any(atual_p.iterdir()):
            add(atual_p, "VAZIA", "SEGURO", "Pasta vazia")
            dirs[:] = []
            continue

        manter = []
        for d in sorted(dirs):
            p = atual_p / d
            if d in PASTAS_IGNORADAS or d.startswith("_quarentena") or p.is_symlink():
                continue
            if d in PASTAS_CACHE or d.endswith(".egg-info"):
                add(p, "CACHE", "SEGURO", "Cache/artefato regenerável")
            elif d in PASTAS_BUILD:
                add(p, "BUILD", "REVISAR", "Artefato de build (confirme que não é versionado)")
            elif PADRAO_LEGADO.search(d):
                add(p, "LEGADO_NOME", "REVISAR", "Nome da pasta contém 'DigitalTech'")
            elif nome_suspeito(d):
                add(p, "SUSPEITO", "REVISAR", "Nome sugere relatório/backup/cópia/temporário")
            else:
                manter.append(d)
        dirs[:] = manter

        for nome in sorted(arquivos):
            p = atual_p / nome
            rel = p.relative_to(raiz)
            if p.is_symlink() or nome in ignorar_arquivos:
                continue
            if nome.startswith(".env"):          # segredos: NUNCA tocamos nem lemos
                continue

            if nome.endswith(".pyc") or nome in ARQUIVOS_LIXO:
                add(p, "LIXO", "SEGURO", "Arquivo gerado automaticamente")
                continue
            if PADRAO_LEGADO.search(nome):
                add(p, "LEGADO_NOME", "REVISAR", "Nome do arquivo contém 'DigitalTech'")
                continue

            if eh_teste(nome):
                if any(parte.lower() in PASTAS_DE_TESTE for parte in rel.parts[:-1]):
                    testes_organizados += 1
                else:
                    add(p, "TESTE_SOLTO", "REVISAR",
                        "Arquivo de teste fora de uma pasta tests/")
            elif nome_suspeito(nome):
                add(p, "SUSPEITO", "REVISAR", "Nome sugere relatório/backup/log/temporário")

            try:
                tam = p.stat().st_size
            except OSError:
                continue
            if tam > LIMITE_GRANDE:
                add(p, "GRANDE", "REVISAR", f"Arquivo grande ({humano(tam)})")
            if tam > 0 and nome != "__init__.py":
                por_tamanho[tam].append(p)

            # Busca de "DigitalTech" dentro do conteúdo (apenas texto, apenas leitura)
            if eh_texto(p) and 0 < tam <= LIMITE_LEITURA:
                try:
                    linhas = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                achados = [(i, l.strip()[:120]) for i, l in enumerate(linhas, 1)
                           if PADRAO_LEGADO.search(l)]
                if achados:
                    ocorrencias.append({
                        "caminho": rel.as_posix(),
                        "total": len(achados),
                        "exemplos": [{"linha": i, "texto": t} for i, t in achados[:3]],
                    })

    # Duplicados (mesmo conteúdo): agrupa por tamanho e confirma por hash
    ja_marcados = {i.caminho for i in itens}
    for tam, lista in por_tamanho.items():
        if len(lista) < 2:
            continue
        grupos: dict[str, list[Path]] = defaultdict(list)
        for p in lista:
            try:
                grupos[sha256(p)].append(p)
            except OSError:
                pass
        for copias in grupos.values():
            if len(copias) < 2:
                continue
            copias.sort(key=lambda x: (len(x.parts), x.as_posix()))
            original = copias[0].relative_to(raiz).as_posix()
            for dup in copias[1:]:
                if dup.relative_to(raiz).as_posix() not in ja_marcados:
                    add(dup, "DUPLICADO", "REVISAR", f"Conteúdo idêntico a '{original}'")

    ocorrencias.sort(key=lambda o: -o["total"])
    relatorio = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "raiz": str(raiz),
        "testes_em_pasta_tests": testes_organizados,
        "itens": [asdict(i) for i in sorted(itens, key=lambda i: (i.categoria, i.caminho))],
        "ocorrencias_digitaltech": ocorrencias,
    }
    (raiz / ARQ_RELATORIO).write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    imprimir_resumo(relatorio)


def imprimir_resumo(rel: dict) -> None:
    print(f"\n=== AUDITORIA: {rel['raiz']} ===")
    por_cat: dict[str, list[dict]] = defaultdict(list)
    for i in rel["itens"]:
        por_cat[i["categoria"]].append(i)

    for cat, lista in por_cat.items():
        total = sum(i["tamanho"] for i in lista)
        print(f"\n[{cat}] {len(lista)} item(ns) - {humano(total)} - risco {lista[0]['risco']}")
        for i in lista[:15]:
            print(f"   - {i['caminho']}  ({i['motivo']})")
        if len(lista) > 15:
            print(f"   ... e mais {len(lista) - 15} (veja {ARQ_RELATORIO})")

    oc = rel["ocorrencias_digitaltech"]
    print(f"\n[LEGADO_CONTEUDO] {len(oc)} arquivo(s) com 'DigitalTech' no texto "
          f"(precisam ser EDITADOS, não excluídos):")
    for o in oc[:15]:
        ex = o["exemplos"][0]
        print(f"   - {o['caminho']}: {o['total']}x  (ex.: linha {ex['linha']}: {ex['texto']})")
    if len(oc) > 15:
        print(f"   ... e mais {len(oc) - 15} (veja {ARQ_RELATORIO})")

    print(f"\nTestes dentro de tests/: {rel['testes_em_pasta_tests']} (não marcados)")
    print(f"\nRelatório salvo em: {ARQ_RELATORIO}")
    print("Nada foi alterado. Revise o relatório e, se quiser, rode a fase 'limpar'.")


# ----------------------------------------------------------------------------
# FASE 2 - limpar (move para quarentena; exclusão definitiva só com --definitivo)
# ----------------------------------------------------------------------------
def git_limpo(raiz: Path) -> bool | None:
    """True = sem alterações pendentes | False = há alterações | None = não é repositório git."""
    try:
        r = subprocess.run(["git", "-C", str(raiz), "status", "--porcelain"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() == ""


def confirmar(pergunta: str) -> bool:
    return input(f"{pergunta} [s/N] ").strip().lower() in {"s", "sim"}


def caminho_seguro(raiz: Path, rel: str) -> Path | None:
    """Garante que o alvo está DENTRO da raiz e não é .git/.env (evita apagar algo errado)."""
    alvo = raiz / rel
    partes = Path(rel).parts
    if ".git" in partes or any(p.startswith(".env") for p in partes):
        return None
    try:
        alvo.parent.resolve().relative_to(raiz.resolve())
    except ValueError:
        return None
    return alvo if (alvo.exists() or alvo.is_symlink()) and not alvo.is_symlink() else None


def remover(raiz: Path, rel: str, pasta_q: Path, definitivo: bool) -> bool:
    alvo = caminho_seguro(raiz, rel)
    if alvo is None:
        print(f"   ! Ignorado (inexistente ou protegido): {rel}")
        return False
    if definitivo:
        shutil.rmtree(alvo) if alvo.is_dir() else alvo.unlink()
    else:
        destino = pasta_q / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(alvo), str(destino))
    return True


def limpar(raiz: Path, definitivo: bool) -> None:
    arq = raiz / ARQ_RELATORIO
    if not arq.exists():
        sys.exit(f"Relatório não encontrado. Rode primeiro: escanear --raiz {raiz}")
    dados = json.loads(arq.read_text(encoding="utf-8"))

    estado = git_limpo(raiz)
    if estado is not True:
        aviso = "não é um repositório git" if estado is None else "há alterações não commitadas"
        print(f"ATENÇÃO: {aviso}. Recomendado: git add -A && git commit -m 'antes da limpeza'")
        if not confirmar("Continuar mesmo assim?"):
            sys.exit("Cancelado.")

    if definitivo and input('Exclusão DEFINITIVA. Digite EXCLUIR para confirmar: ') != "EXCLUIR":
        sys.exit("Cancelado.")

    grupos: dict[str, list[dict]] = defaultdict(list)
    for i in dados["itens"]:
        if i["categoria"] not in CATEGORIAS_SO_INFORMATIVAS:
            grupos[i["categoria"]].append(i)

    pasta_q = raiz / f"_quarentena_{datetime.now():%Y%m%d_%H%M%S}"
    removidos = 0
    for cat, lista in grupos.items():
        print(f"\n=== {cat} ({len(lista)} item(ns)) ===")
        if cat in CATEGORIAS_SEGURAS:
            for i in lista:
                print(f"   - {i['caminho']}")
            if confirmar("Remover TODOS deste grupo?"):
                removidos += sum(remover(raiz, i["caminho"], pasta_q, definitivo) for i in lista)
        else:
            for i in lista:
                print(f"\n   {i['caminho']}  ({humano(i['tamanho'])})\n   Motivo: {i['motivo']}")
                if confirmar("   Remover este item?"):
                    removidos += remover(raiz, i["caminho"], pasta_q, definitivo)

    destino = "excluídos definitivamente" if definitivo else f"movidos para {pasta_q.name}/"
    print(f"\n{removidos} item(ns) {destino}.")
    print("Teste o projeto. Se tudo funcionar, apague a quarentena e faça o commit.")
    print("Para desfazer: mova os itens de volta ou use 'git restore'.")


# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoria e limpeza segura de projetos.")
    ap.add_argument("fase", choices=["escanear", "limpar"])
    ap.add_argument("--raiz", default=".", help="Pasta raiz do projeto (padrão: atual)")
    ap.add_argument("--definitivo", action="store_true",
                    help="Exclui de verdade (padrão: move para quarentena)")
    args = ap.parse_args()

    raiz = Path(args.raiz).resolve()
    if not raiz.is_dir():
        sys.exit(f"Pasta inválida: {raiz}")
    if args.fase == "escanear":
        escanear(raiz)
    else:
        limpar(raiz, args.definitivo)


if __name__ == "__main__":
    main()
