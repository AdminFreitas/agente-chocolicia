"""
services/image_providers/licencas.py — Política de licença de imagem (docs/08 IMG-01).

Aceita:  CC0, domínio público (PDM), licenças próprias dos provedores aprovados
         (Pixabay e Pexels, por nome exato) e CC BY (exige atribuição).
Recusa:  qualquer licença com NC, ND ou SA, "todos os direitos reservados" e
         qualquer licença desconhecida ou vazia.

PENDENTE (docs/00 §6): os termos de Pixabay, Pexels, Openverse e Wikimedia ainda
não foram conferidos; as licenças próprias dos provedores são aceitas como
instruído, mas isso deve ser revisto depois da conferência.
"""

import re
from dataclasses import dataclass

_PROPRIAS = {
    "pixabay": {"pixabay content license", "pixabay license"},
    "pexels": {"pexels license"},
}
_RESTRITIVOS = {"nc", "nd", "sa"}
_RESERVADOS = ("all rights reserved", "todos os direitos reservados", "copyright")
_DOMINIO_PUBLICO = ("public domain", "dominio publico", "publicdomain")


@dataclass(frozen=True)
class Licenca:
    aceita: bool
    codigo: str  # "cc0" | "pdm" | "cc-by" | "propria" | "recusada"
    exige_atribuicao: bool
    motivo: str


def _tokens(texto: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).split()


def classificar_licenca(provedor: str, nome: str | None, url: str | None = None) -> Licenca:
    bruto = (nome or "").strip()
    if not bruto:
        return Licenca(False, "recusada", False, "licença ausente")
    baixo = bruto.lower()
    toks = _tokens(bruto)

    if any(r in baixo for r in _RESERVADOS):
        return Licenca(False, "recusada", False, "direitos reservados")
    if _RESTRITIVOS & set(toks):
        return Licenca(False, "recusada", False, f"licença com restrição ({'/'.join(sorted(_RESTRITIVOS & set(toks)))})")

    if "cc0" in toks[:2] or toks[:2] == ["cc", "zero"] or toks[:2] == ["cc", "0"]:
        return Licenca(True, "cc0", False, "ok")
    if "pdm" in toks or any(p in baixo for p in _DOMINIO_PUBLICO):
        return Licenca(True, "pdm", False, "ok")

    if baixo in _PROPRIAS.get(provedor, set()):
        return Licenca(True, "propria", False, "licença própria do provedor")

    # "CC BY 4.0", "CC-BY-4.0", "by 4.0" (Openverse monta "CC BY 4.0")
    for i in range(len(toks) - 1):
        if toks[i] == "cc" and toks[i + 1] == "by":
            return Licenca(True, "cc-by", True, "ok")
    if toks[:1] == ["by"]:
        return Licenca(True, "cc-by", True, "ok")

    return Licenca(False, "recusada", False, f"licença desconhecida: {bruto[:60]}")
