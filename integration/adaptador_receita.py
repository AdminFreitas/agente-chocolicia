"""
integration/adaptador_receita.py — Converte a receita do agente para o contrato v1
documentado ou para o schema atual de receitas do site.

Quem decide o quê (docs/03 §6.2; 04 §6.3):
- O MODELO escreveu: título, descrição, introdução, ingredientes, passos, dica extra,
  perguntas, tags, termos e texto alternativo da imagem.
- O CÓDIGO define aqui: dificuldade (passos + técnicas da ficha), slug, dieta (da ficha,
  que veio do catálogo), ocasiões (da pauta), slug de ingrediente (catálogo), autor/aviso
  (o site), status (parâmetro), aiModel e generationMeta.
- O runtime atual escolhe o payload compatível com o endpoint existente; ambos os
  adaptadores validam antes do envio e falham sem efeitos de rede.

PENDENTE: storageNotes (vem da base curada config/seguranca.json, cujo formato a doc não
define; entra como parâmetro) e collections (a pauta não as traz; parâmetro).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Sequence

from pydantic import ValidationError

from agents.pesquisador import VOCABULARIO_FLAGS
from integration.cliente_site import ContratoInvalido
from integration.contratos import ReceitaLegada, ReceitaV1

_PADRAO_SLUG = re.compile(r"[^a-z0-9]+")


class IngredienteForaDoCatalogo(ContratoInvalido):
    """Fase 0/1: vocabulário fechado (docs/04 §7.2, ALG-01). Nada foi enviado."""

    def __init__(self, nomes: list[str]):
        self.nomes = nomes
        super().__init__([{"campo": "ingredients", "detalhe": "fora do catálogo: " + ", ".join(nomes[:8])}])


def slugificar(texto: str, maximo: int) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return _PADRAO_SLUG.sub("-", t).strip("-")[:maximo].strip("-")


def calcular_dificuldade(n_passos: int, flags: Sequence[str]) -> str:
    """
    docs/04 §6.3, por código: Difícil = mais de 15 passos ou técnica sensível;
    Média = de 9 a 15 passos ou técnica de atenção ao ponto; Fácil = o resto.
    Flags desconhecidas contam como sensíveis (na dúvida, o nível mais alto).
    """
    tipos = [VOCABULARIO_FLAGS.get(f, "sensivel") for f in flags]
    if n_passos > 15 or "sensivel" in tipos:
        return "Difícil"
    if n_passos >= 9 or "atencao" in tipos:
        return "Média"
    return "Fácil"


def reduzir_opcionais(corpo: dict) -> dict:
    """Redutor para o 413 (docs/06 §11): tira blocos opcionais, nunca ingredientes nem passos."""
    novo = dict(corpo)
    for campo in ("faq", "tips"):
        if novo.get(campo):
            novo.pop(campo)
            break
    return novo


def montar_payload_receita(
    conteudo: dict,
    *,
    pauta: dict,
    ficha: dict,
    cover: Optional[dict],
    run_id: str,
    fase: int,
    modelo: dict,
    prompt_version: str,
    catalogo,
    status: str = "draft",
    storage_notes: Optional[str] = None,
    colecoes: Sequence[str] = (),
    validators_version: str = "pendente",
) -> ReceitaV1:
    if not cover:
        raise ContratoInvalido([{"campo": "cover", "detalhe": "sem capa validada para a receita"}])
    if conteudo.get("subcategoria") != pauta.get("subcategoria"):
        raise ContratoInvalido([{"campo": "subcategorySlug", "detalhe": "a subcategoria vem da pauta e não pode mudar"}])
    if not pauta.get("topic_slug"):
        raise ContratoInvalido([{"campo": "generationMeta.topic_slug", "detalhe": "a pauta não tem topic_slug"}])
    if not pauta.get("author_id") and not pauta.get("author_slug"):
        raise ContratoInvalido([{"campo": "author", "detalhe": "a regra editorial não resolveu o autor da receita"}])

    # ---- ingredientes e catálogo (ALG-01: Fases 0 e 1 exigem vocabulário fechado)
    fora: list[str] = []
    secoes = []
    for sec in conteudo["ingredientes"]:
        itens = []
        for it in sec["itens"]:
            entrada = catalogo.resolver(it["nome"]) if getattr(catalogo, "disponivel", False) else None
            slug_ing = entrada.get("slug") if entrada else None
            if slug_ing is None:
                fora.append(it["nome"])
            itens.append({"name": it["nome"], "quantity": it["quantidade"], "unit": it["unidade"],
                          "note": it.get("observacao"), "ingredientSlug": slug_ing})
        secoes.append({"name": sec["nome"], "items": itens})
    if fora and fase <= 1:
        raise IngredienteForaDoCatalogo(fora)

    # ---- tags: slug, sem repetir categoria, subcategoria, ocasião, dieta ou coleção (04 §6.5)
    ocasioes = list(pauta.get("ocasiao") or [])
    dieta = list(ficha.get("etiquetas_dieta") or [])
    reservados = {pauta.get("categoria"), pauta.get("subcategoria"), *ocasioes, *dieta, *colecoes}
    tags: list[str] = []
    for t in conteudo.get("tags", []):
        s = slugificar(t, 40)
        if s and s not in reservados and s not in tags:
            tags.append(s)

    passos = [{"title": p.get("titulo"), "instruction": p["instrucao"]} for p in conteudo["modo_preparo"]]
    flags = list(ficha.get("tecnica_flags") or [])
    modelo_ia = "/".join(x for x in (modelo.get("provedor"), modelo.get("modelo")) if x)[:120] or "nao-informado"

    bruto = {
        "title": conteudo["titulo"],
        "slug": slugificar(conteudo["titulo"], 180),
        "excerpt": conteudo["descricao_curta"],
        "intro": conteudo.get("introducao"),
        "subcategorySlug": pauta["subcategoria"],
        "authorId": pauta.get("author_id"),
        "authorSlug": pauta.get("author_slug"),
        "prepTimeMin": conteudo["tempo_preparo_min"],
        "cookTimeMin": conteudo.get("tempo_cozimento_min"),
        "restTimeMin": conteudo.get("tempo_descanso_min"),
        "servings": conteudo["rendimento_porcoes"],
        "yieldLabel": conteudo.get("rendimento_texto"),
        "difficulty": calcular_dificuldade(len(passos), flags),
        "ingredients": secoes,
        "steps": passos,
        "tips": [conteudo["dica_extra"]] if conteudo.get("dica_extra") else [],  # 03 §6.2: dica_extra -> tips
        "storageNotes": storage_notes,
        "faq": [{"question": f["pergunta"], "answer": f["resposta"]} for f in conteudo.get("perguntas_frequentes", [])],
        "tags": tags[:12],
        "occasions": ocasioes,
        "collections": list(colecoes),
        "diet": dieta,
        "cover": cover,
        "coverImageAlt": conteudo["texto_alt_imagem"],
        "status": status,
        "aiModel": modelo_ia,
        "generationMeta": {
            "run_id": run_id,
            "topic_slug": pauta["topic_slug"],
            "prompt_version": prompt_version,
            "phase": fase,
            "sources": [
                {"domain": r["dominio"], "url": r["url"], "date": str(r["acessado_em"])[:10]}
                for r in ficha.get("referencias_registro", [])
            ],
            "validators_version": validators_version,
            "technique_flags": flags,
        },
    }
    try:
        return ReceitaV1.model_validate({k: v for k, v in bruto.items() if v is not None})
    except ValidationError as exc:
        raise ContratoInvalido(
            [{"campo": ".".join(map(str, e["loc"])), "detalhe": e["msg"]} for e in exc.errors()]
        ) from None


def montar_payload_receita_legada(
    conteudo: dict, *, pauta: dict, ficha: dict, cover: Optional[dict], status: str = "draft"
) -> ReceitaLegada:
    """Monta somente os campos conhecidos do POST /api/recipes legado."""
    if cover is not None and cover.get("mode") != "stock":
        raise ContratoInvalido([{"campo": "coverImageUrl", "detalhe": "o contrato legado exige URL de capa existente"}])
    categoria = pauta.get("categoria_legada")
    if not categoria:
        raise ContratoInvalido([{"campo": "category", "detalhe": "categoria legada explícita é obrigatória"}])
    bruto = {
        "title": conteudo["titulo"],
        "excerpt": conteudo["descricao_curta"],
        "category": categoria,
        "subcategorySlug": pauta.get("subcategoria"),
        "coverImageAlt": conteudo["texto_alt_imagem"],
        "ingredients": [
            {
                "name": secao["nome"],
                "items": [
                    {"name": item["nome"], "quantity": item["quantidade"], "unit": item["unidade"]}
                    for item in secao["itens"]
                ],
            }
            for secao in conteudo["ingredientes"]
        ],
        "steps": [{"instruction": passo["instrucao"]} for passo in conteudo["modo_preparo"]],
        "prepTimeMin": conteudo["tempo_preparo_min"],
        "cookTimeMin": conteudo.get("tempo_cozimento_min") or 0,
        "servings": conteudo["rendimento_porcoes"],
        "difficulty": calcular_dificuldade(
            len(conteudo["modo_preparo"]),
            list(ficha.get("tecnica_flags") or []),
        ),
        "status": status,
    }
    if cover is not None:
        bruto["coverImageUrl"] = cover["sourceImageUrl"]
    try:
        return ReceitaLegada.model_validate(bruto)
    except ValidationError as exc:
        raise ContratoInvalido(
            [{"campo": ".".join(map(str, e["loc"])), "detalhe": e["msg"]} for e in exc.errors()]
        ) from None
