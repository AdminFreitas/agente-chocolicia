"""
integration/contratos.py — Modelos Pydantic do contrato v1 agente -> site.

Base: contrato de receitas e imagens do site; as dicas usam o contrato físico de /api/tips.
(versionamento); docs/04 §9.1 (unidades) e §6.2 (etiquetas de dieta habilitadas).
O site é o dono do contrato (docs/01 D-11): este módulo é a CÓPIA do agente.

Os nomes dos campos são os da API (inglês, camelCase), de propósito: o payload
sai direto de model_dump(). Regras vindas do código do site (shared/recipes.ts)
e não da doc estão marcadas com "SITE:".

Comandos:
    python -m integration.contratos --exportar    # regrava contracts/*.schema.json
    python -m integration.contratos --verificar   # falha se contracts/ estiver desatualizado

PENDENTE: o site ainda não exporta contracts/ (Bloco 1). Os arquivos de contracts/
deste repositório são GERADOS pelo agente e NÃO são a cópia canônica do site.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1"
PASTA_CONTRATOS = Path(__file__).resolve().parent.parent / "contracts"

SLUG_RE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SLUG = re.compile(SLUG_RE)

# docs/04 §9.1: unidade fora da lista rejeita a receita.
UNIDADES = (
    "g", "kg", "ml", "l", "xícara", "colher de sopa", "colher de chá", "unidade",
    "pitada", "dente", "fatia", "lata", "caixinha", "maço", "ramo",
)
# docs/04 §6.2: `sem-gluten` e `sem-lactose` estão reservadas e desabilitadas nas Fases 1 e 2.
DIETAS_HABILITADAS = ("vegetariana", "vegana")
TAGS_RESERVADAS_DESABILITADAS = ("sem-gluten", "sem-lactose")


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Imagem (docs/06 §7)
# --------------------------------------------------------------------------


class CoverStock(_Estrito):
    mode: Literal["stock"]
    provider: str = Field(min_length=1, max_length=40)
    sourceImageUrl: str = Field(min_length=1, max_length=2048, pattern=r"^https://")
    sourcePageUrl: str = Field(min_length=1, max_length=2048, pattern=r"^https://")
    # Pode ser vazio em CC0/domínio público (selector.py): ver "Lacunas do site".
    author: str = Field(max_length=200)
    license: str = Field(min_length=1, max_length=120)
    attributionText: str = Field(max_length=400)


class CoverGenerate(_Estrito):
    mode: Literal["generate"]
    imagePrompt: str = Field(min_length=1, max_length=2000)


Cover = Annotated[Union[CoverStock, CoverGenerate], Field(discriminator="mode")]


# --------------------------------------------------------------------------
# Receita (docs/06 §6.2)
# --------------------------------------------------------------------------


class ItemIngredienteV1(_Estrito):
    name: str = Field(min_length=1, max_length=180)
    quantity: str = Field(min_length=1, max_length=80)
    unit: Literal[UNIDADES]  # type: ignore[valid-type]
    note: Optional[str] = Field(default=None, max_length=180)
    # Obrigatório na Fase 1; nulo para `unresolved` nas fases seguintes (06 §6.2).
    ingredientSlug: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=SLUG_RE)


class SecaoIngredientesV1(_Estrito):
    name: str = Field(min_length=1, max_length=100)  # SITE: ingredientSectionSchema (max 100)
    items: list[ItemIngredienteV1] = Field(min_length=1, max_length=80)


class PassoV1(_Estrito):
    title: Optional[str] = Field(default=None, max_length=120)
    instruction: str = Field(min_length=1, max_length=1200)


class FaqV1(_Estrito):
    question: str = Field(min_length=1, max_length=240)
    answer: str = Field(min_length=1, max_length=1200)


class FonteV1(_Estrito):
    # 06 §6.2 diz "sources (domínio, URL e data)" sem nomear as chaves. PENDENTE: confirmar.
    domain: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class GenerationMetaV1(_Estrito):
    run_id: str = Field(min_length=1, max_length=64)
    topic_slug: str = Field(min_length=1, max_length=180, pattern=SLUG_RE)
    prompt_version: str = Field(min_length=1, max_length=200)
    phase: int = Field(ge=0, le=3)
    sources: list[FonteV1] = Field(default_factory=list, max_length=20)
    validators_version: str = Field(min_length=1, max_length=40)
    # Não consta em 06 §6.2, mas o CODEX-01 (Etapa 3, item 3) manda o servidor conferir a
    # dificuldade por `generationMeta.technique_flags`.
    technique_flags: list[str] = Field(default_factory=list, max_length=10)


def _slugs_unicos(valores: list[str], rotulo: str) -> list[str]:
    for v in valores:
        if not SLUG.match(v) or len(v) > 40:
            raise ValueError(f"{rotulo}: '{v}' não é um slug válido de até 40 caracteres")
    if len(set(valores)) != len(valores):
        raise ValueError(f"{rotulo}: valores repetidos")
    return valores


class ReceitaV1(_Estrito):
    title: str = Field(min_length=5, max_length=180)
    slug: Optional[str] = Field(default=None, min_length=3, max_length=180, pattern=SLUG_RE)
    excerpt: str = Field(min_length=20, max_length=160)
    category: Optional[str] = Field(default=None, min_length=2, max_length=80)
    intro: Optional[str] = Field(default=None, max_length=2000)  # limite da doc: não informado
    subcategorySlug: str = Field(min_length=1, max_length=120, pattern=SLUG_RE)
    secondarySubcategorySlugs: list[str] = Field(default_factory=list, max_length=2)
    prepTimeMin: int = Field(ge=1, le=1440)
    cookTimeMin: Optional[int] = Field(default=None, ge=0, le=1440)
    restTimeMin: Optional[int] = Field(default=None, ge=0, le=10080)
    servings: int = Field(ge=1, le=500)
    yieldLabel: Optional[str] = Field(default=None, max_length=80)
    difficulty: Literal["Fácil", "Média", "Difícil"]
    ingredients: list[SecaoIngredientesV1] = Field(min_length=1, max_length=20)
    steps: list[PassoV1] = Field(min_length=4, max_length=20)
    tips: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=5)
    storageNotes: Optional[str] = Field(default=None, max_length=3000)
    faq: list[FaqV1] = Field(default_factory=list, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=12)
    occasions: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    diet: list[str] = Field(default_factory=list)
    cover: Cover
    coverImageUrl: Optional[AnyHttpUrl] = None
    coverImageAlt: str = Field(min_length=8, max_length=240)
    status: Literal["draft", "published"] = "draft"  # D-06: o padrão é draft
    aiModel: str = Field(min_length=1, max_length=120)
    generationMeta: GenerationMetaV1

    @model_validator(mode="after")
    def _regras(self):
        _slugs_unicos(self.tags, "tags")
        _slugs_unicos(self.occasions, "occasions")
        _slugs_unicos(self.collections, "collections")
        _slugs_unicos(self.secondarySubcategorySlugs, "secondarySubcategorySlugs")
        if set(self.tags) & set(TAGS_RESERVADAS_DESABILITADAS):
            raise ValueError("tags: etiqueta reservada e desabilitada (sem-gluten/sem-lactose)")
        invalidas = [d for d in self.diet if d not in DIETAS_HABILITADAS]
        if invalidas:
            raise ValueError(f"diet: etiqueta não habilitada: {invalidas}")
        if len(set(self.diet)) != len(self.diet):
            raise ValueError("diet: valores repetidos")
        return self


# Compatibilidade com o endpoint legado POST /api/recipes.
class IngredienteLegado(_Estrito):
    name: str = Field(min_length=1, max_length=180)
    quantity: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=40)


class SecaoIngredientesLegada(_Estrito):
    name: str = Field(min_length=1, max_length=100)
    items: list[IngredienteLegado] = Field(min_length=1, max_length=80)


class PassoLegado(_Estrito):
    instruction: str = Field(min_length=1, max_length=1200)


class ReceitaLegada(_Estrito):
    title: str = Field(min_length=5, max_length=180)
    excerpt: str = Field(min_length=20, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    categorySlug: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=SLUG_RE)
    subcategorySlug: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=SLUG_RE)
    coverImageUrl: AnyHttpUrl
    coverImageAlt: str = Field(min_length=8, max_length=240)
    ingredients: list[SecaoIngredientesLegada] = Field(min_length=1, max_length=20)
    steps: list[PassoLegado] = Field(min_length=2, max_length=30)
    prepTimeMin: int = Field(ge=1, le=1440)
    cookTimeMin: int = Field(ge=0, le=1440)
    servings: int = Field(ge=1, le=500)
    difficulty: Literal["Fácil", "Média", "Difícil"]
    status: Literal["draft", "published"] = "draft"


# --------------------------------------------------------------------------
# Esquemas exportados (teste de contrato, docs/06 §14)
# --------------------------------------------------------------------------

_ARQUIVOS = {"recipe.v1.schema.json": ReceitaV1}
_ORIGEM = "gerado pelo agente a partir de integration/contratos.py (NÃO é a cópia canônica do site)"


def gerar_schemas() -> dict[str, dict]:
    saida = {}
    for nome, modelo in _ARQUIVOS.items():
        s = modelo.model_json_schema()
        s["x-origem"] = _ORIGEM
        s["x-contract-version"] = CONTRACT_VERSION
        saida[nome] = s
    return saida


def _texto(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def exportar(pasta: Path = PASTA_CONTRATOS) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nome, schema in gerar_schemas().items():
        destino = pasta / nome
        destino.write_text(_texto(schema), encoding="utf-8", newline="\n")
        escritos.append(destino)
    return escritos


def desatualizados(pasta: Path = PASTA_CONTRATOS) -> list[str]:
    ruins = []
    for nome, schema in gerar_schemas().items():
        arq = pasta / nome
        if not arq.is_file() or arq.read_text(encoding="utf-8") != _texto(schema):
            ruins.append(nome)
    return ruins


def validar_receita(payload: dict) -> ReceitaV1:
    """API-01: o payload é válido contra o contrato v1."""
    return ReceitaV1.model_validate(payload)


if __name__ == "__main__":  # pragma: no cover
    if "--exportar" in sys.argv:
        print("\n".join(str(p) for p in exportar()))
    elif "--verificar" in sys.argv:
        ruins = desatualizados()
        print("contracts/ desatualizado: " + ", ".join(ruins) if ruins else "contracts/ em dia")
        sys.exit(1 if ruins else 0)
    else:
        print(__doc__)
