#!/usr/bin/env python3
"""
snapshot_projeto.py - gera SNAPSHOT-PROJETO.md, um resumo compacto do projeto
para enviar a uma IA (por exemplo, anexando o arquivo em um chat).

O que faz:
  - lista a estrutura de pastas (sem node_modules, .git, __pycache__ etc.);
  - inclui o conteudo dos arquivos de texto mais importantes, ate um limite total;
  - NUNCA inclui arquivos .env (so .env.example, com os valores apagados);
  - apaga valores que parecem segredos (chaves, tokens, senhas, URLs de banco).

Uso (dentro da pasta do projeto):
  python snapshot_projeto.py
  python snapshot_projeto.py --max-kb 60 --file-kb 10 --out SNAPSHOT-PROJETO.md

IMPORTANTE: depois de gerar, ABRA o arquivo e procure por KEY, TOKEN, SECRET,
PASSWORD e postgres. Se achar algum valor real, apague a linha antes de enviar.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".idea",
    ".vscode", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "logs", "log", "pgdata", "postgres_data", "data", ".next", ".cache",
    "htmlcov", "site-packages", ".tox", ".eggs",
}
IGNORE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "SNAPSHOT-PROJETO.md",
}
TEXT_EXT = {
    ".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".json", ".sql", ".sh",
    ".ini", ".cfg", ".ts", ".js", ".html", ".css",
}
ALWAYS_NAMES = {"Dockerfile", "docker-compose.yml", "requirements.txt", ".gitignore", ".env.example", ".env.sample"}
ENV_EXAMPLE = {".env.example", ".env.sample"}
SENSITIVE_NAME = re.compile(r"(secret|credential|\.pem$|\.key$|id_rsa|\.p12$|\.pfx$)", re.I)
SECRET_VAR = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASS|DSN|URL|URI|CREDENTIAL)", re.I)
ASSIGN = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z0-9_.\-]+)(\s*[=:]\s*)(.+)$")
SAFE_VALUE_START = ("os.", "getenv", "environ", "settings", "config", "${", "<", "...", "None", "true", "false")
PATTERNS = [
    (re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s'\"]+"), "postgresql://***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "sk-***"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{16,}"), "gh***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}"), "github_pat_***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "AIza***"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{16,}"), "gsk_***"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "xox***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer ***"),
]
PRIORITY_PARTS = [
    "readme", "rodar_agente", "main.py", "app.py", "api.py", "requirements",
    ".env.example", "agents/", "pipeline/", "services/", "repositories/",
    "config/", ".github/workflows", "docker-compose", "dockerfile",
]


def is_env_secret_file(name: str) -> bool:
    return name.startswith(".env") and name not in ENV_EXAMPLE


def redact_line(line: str, env_style: bool) -> str:
    for pat, repl in PATTERNS:
        line = pat.sub(repl, line)
    m = ASSIGN.match(line)
    if m and SECRET_VAR.search(m.group(2)):
        value = m.group(4).strip()
        bare = value.strip("'\"")
        if env_style:
            if bare:
                return f"{m.group(1)}{m.group(2)}{m.group(3)}***"
        else:
            looks_literal = (
                len(bare) >= 8
                and "(" not in bare
                and " " not in bare
                and not bare.lower().startswith(SAFE_VALUE_START)
            )
            if looks_literal:
                return f"{m.group(1)}{m.group(2)}{m.group(3)}***"
    return line


def read_text(path: Path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:2048]:
        return None
    return raw.decode("utf-8", errors="replace")


def priority(rel: str) -> int:
    low = rel.lower()
    for i, part in enumerate(PRIORITY_PARTS):
        if part in low:
            return i
    return len(PRIORITY_PARTS)


def collect(root: Path):
    files = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts[:-1]):
            continue
        if path.is_dir():
            continue
        name = path.name
        if name in IGNORE_FILES or is_env_secret_file(name) or SENSITIVE_NAME.search(name):
            continue
        if name in ALWAYS_NAMES or path.suffix.lower() in TEXT_EXT:
            files.append(path)
    return files


def tree(root: Path, files, max_depth=4):
    lines = [root.name + "/"]
    seen_dirs = set()
    for path in files:
        rel = path.relative_to(root)
        parts = rel.parts
        for depth in range(1, min(len(parts), max_depth + 1)):
            d = parts[:depth]
            if d not in seen_dirs:
                seen_dirs.add(d)
                lines.append("  " * depth + d[-1] + "/")
        if len(parts) <= max_depth + 1:
            lines.append("  " * len(parts) + parts[-1] + f"  ({path.stat().st_size} bytes)")
    return "\n".join(lines)


def lang(path: Path) -> str:
    return {".py": "python", ".md": "markdown", ".yml": "yaml", ".yaml": "yaml", ".json": "json",
            ".sql": "sql", ".sh": "bash", ".ts": "typescript", ".js": "javascript",
            ".toml": "toml", ".html": "html", ".css": "css"}.get(path.suffix.lower(), "")


def main():
    ap = argparse.ArgumentParser(description="Gera um resumo compacto do projeto, sem segredos.")
    ap.add_argument("--max-kb", type=int, default=90, help="tamanho total aproximado do conteudo de arquivos (KB)")
    ap.add_argument("--file-kb", type=int, default=14, help="tamanho maximo por arquivo (KB)")
    ap.add_argument("--out", default="SNAPSHOT-PROJETO.md")
    args = ap.parse_args()

    root = Path.cwd()
    files = collect(root)
    files.sort(key=lambda p: (priority(str(p.relative_to(root)).replace("\\", "/")), p.stat().st_size))

    budget = args.max_kb * 1024
    per_file = args.file_kb * 1024
    used = 0
    included, omitted, truncated = [], [], []
    blocks = []

    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        text = read_text(path)
        if text is None:
            omitted.append(rel + " (binario)")
            continue
        env_style = path.name in ENV_EXAMPLE
        clean = "\n".join(redact_line(l, env_style) for l in text.split("\n"))
        note = ""
        if len(clean.encode("utf-8")) > per_file:
            head = clean[: int(per_file * 0.7)]
            tail = clean[-int(per_file * 0.3):]
            clean = head + "\n\n[... trecho omitido para economizar espaco ...]\n\n" + tail
            note = " (truncado)"
            truncated.append(rel)
        size = len(clean.encode("utf-8"))
        if used + size > budget:
            omitted.append(rel + " (limite total atingido)")
            continue
        used += size
        included.append(rel)
        blocks.append(f"### `{rel}`{note}\n\n````{lang(path)}\n{clean}\n````\n")

    out = []
    out.append(f"# Resumo do projeto: {root.name}\n")
    out.append(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} por snapshot_projeto.py.")
    out.append("Segredos foram apagados automaticamente; arquivos `.env` nao sao incluidos.\n")
    out.append("## Estrutura\n")
    out.append("```text\n" + tree(root, files) + "\n```\n")
    out.append(f"## Arquivos incluidos ({len(included)})\n")
    out.extend(blocks)
    if omitted:
        out.append("## Arquivos omitidos\n")
        out.extend(f"- {o}" for o in omitted)
        out.append("")
    Path(args.out).write_text("\n".join(out), encoding="utf-8")

    kb = Path(args.out).stat().st_size / 1024
    print(f"Arquivo gerado: {args.out} ({kb:.0f} KB)")
    print(f"Incluidos: {len(included)} | truncados: {len(truncated)} | omitidos: {len(omitted)}")
    print()
    print("ATENCAO: abra o arquivo e procure por KEY, TOKEN, SECRET, PASSWORD e postgres.")
    print("Se achar algum valor real, apague a linha antes de enviar para qualquer IA.")


if __name__ == "__main__":
    sys.exit(main())
