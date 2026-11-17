"""Publicação direta no site depois que a receita passa no contrato v1.

Não há fila de aprovação. O que o contrato rejeita não é enviado. Publicar
exige SITE_BASE_URL em HTTPS, SITE_TOKEN_PUBLISH e AGENT_PHASE >= 1.
"""

from __future__ import annotations

import os
import re
from typing import Any

from integration.cliente_site import ClienteSite
from integration.contratos import ReceitaV1

_DIFICULDADE = {"Fácil": "Fácil", "Médio": "Média", "Média": "Média", "Avançado": "Difícil", "Difícil": "Difícil"}

_UNIDADE_FRASE = (
    ("colheres de sopa", "colher de sopa"),
    ("colher de sopa", "colher de sopa"),
    ("colheres de chá", "colher de chá"),
    ("colher de chá", "colher de chá"),
    ("xícaras", "xícara"),
    ("xícara", "xícara"),
    ("xicaras", "xícara"),
    ("xicara", "xícara"),
    ("pitadas", "pitada"),
    ("pitada", "pitada"),
    ("unidades", "unidade"),
    ("unidade", "unidade"),
    ("dentes", "dente"),
    ("dente", "dente"),
    ("fatias", "fatia"),
    ("fatia", "fatia"),
    ("caixinhas", "caixinha"),
    ("caixinha", "caixinha"),
    ("latas", "lata"),
    ("lata", "lata"),
    ("maços", "maço"),
    ("maço", "maço"),
    ("ramos", "ramo"),
    ("ramo", "ramo"),
)
_UNIDADE_CURTA = {"kg": "kg", "ml": "ml", "g": "g", "l": "l"}


class AutonomousPublisher:
    def __init__(
        self,
        *,
        cliente: ClienteSite | None = None,
        subcategoria: str | None = None,
        dry_run: bool = False,
        fase: int | None = None,
    ):
        self.subcategoria = (subcategoria or os.getenv("MOTOR_SUBCATEGORIA") or "").strip()
        self.cliente = cliente or cliente_de_ambiente(dry_run=dry_run, fase=fase)
        self.dry_run = self.cliente.dry_run

    def publish_recipe(self, recipe_data: dict, *, run_id: str, model_name: str) -> Any:
        if not self.subcategoria:
            raise ValueError("informe a subcategoria (argumento ou MOTOR_SUBCATEGORIA)")
        payload = montar_payload_publicado(
            recipe_data,
            subcategoria=self.subcategoria,
            run_id=run_id,
            model_name=model_name,
            fase=self.cliente.fase,
        )
        return self.cliente.criar_receita(payload, run_id=run_id)


def cliente_de_ambiente(*, dry_run: bool, fase: int | None = None) -> ClienteSite:
    base = os.getenv("SITE_BASE_URL", "").strip()
    token = os.getenv("SITE_TOKEN_PUBLISH", "").strip()
    fase_efetiva = fase if fase is not None else _fase_ambiente()
    if not token and not dry_run:
        raise RuntimeError("SITE_TOKEN_PUBLISH não configurado")
    if not token and dry_run:
        token = "dry-run"
    return ClienteSite(
        base,
        token_publish=token or None,
        fase=fase_efetiva,
        dry_run=dry_run,
    )


def montar_payload_publicado(
    data: dict[str, Any],
    *,
    subcategoria: str,
    run_id: str,
    model_name: str,
    fase: int,
) -> ReceitaV1:
    passos = [passo.strip() for passo in data.get("steps") or [] if str(passo).strip()]
    ingredientes = [item.strip() for item in data.get("ingredients") or [] if str(item).strip()]
    if len(passos) < 4:
        raise ValueError("a publicação exige pelo menos 4 passos")
    if len(ingredientes) < 2:
        raise ValueError("a publicação exige pelo menos 2 ingredientes")

    dificuldade = _DIFICULDADE.get(str(data.get("difficulty", "")).strip())
    if dificuldade is None:
        raise ValueError("dificuldade fora do contrato do site")

    prep = minutos_totais(str(data.get("prep_time", "")))
    cook = minutos_totais(str(data.get("cook_time", "")))
    porcoes = porcoes_inteiras(str(data.get("servings", "")))
    if prep < 1 or porcoes < 1:
        raise ValueError("tempo de preparo e rendimento precisam ser numéricos")

    titulo = str(data["title"]).strip()
    prompt_imagem = f"Fotografia aproximada do prato pronto: {titulo}. Sem pessoas, sem texto e sem marca."
    corpo = {
        "title": titulo,
        "slug": data.get("slug"),
        "excerpt": recortar_excerpt(str(data.get("description", ""))),
        "subcategorySlug": subcategoria,
        "prepTimeMin": prep,
        "cookTimeMin": cook,
        "servings": porcoes,
        "yieldLabel": str(data.get("servings", ""))[:80] or None,
        "difficulty": dificuldade,
        "ingredients": [{"name": "Ingredientes", "items": [interpretar_ingrediente(item) for item in ingredientes]}],
        "steps": [{"instruction": passo[:1200]} for passo in passos],
        "tips": [dica[:1000] for dica in (data.get("tips") or []) if str(dica).strip()][:5],
        "cover": {"mode": "generate", "imagePrompt": prompt_imagem[:2000]},
        "coverImageAlt": recortar_alt(titulo),
        "status": "published",
        "aiModel": (model_name or "mistral:7b-instruct")[:120],
        "generationMeta": {
            "run_id": run_id,
            "topic_slug": data["slug"],
            "prompt_version": "motor-local-1",
            "phase": fase,
            "validators_version": "motor-local",
            "technique_flags": [],
            "sources": [],
        },
    }
    return ReceitaV1.model_validate(corpo)


def interpretar_ingrediente(texto: str) -> dict[str, str]:
    bruto = " ".join(texto.split())
    frase = re.match(
        r"^(\d+(?:[.,]\d+)?)\s+(" + "|".join(re.escape(nome) for nome, _ in _UNIDADE_FRASE) + r")\s+(?:de\s+)?(.+)$",
        bruto,
        flags=re.IGNORECASE,
    )
    if frase:
        unidade = dict(_UNIDADE_FRASE)[frase.group(2).lower()]
        return {"name": frase.group(3).strip(), "quantity": frase.group(1), "unit": unidade}

    curta = re.match(r"^(\d+(?:[.,]\d+)?)\s*(kg|ml|g|l)\b\s*(?:de\s+)?(.+)$", bruto, flags=re.IGNORECASE)
    if curta:
        return {
            "name": curta.group(3).strip(),
            "quantity": curta.group(1),
            "unit": _UNIDADE_CURTA[curta.group(2).lower()],
        }

    contavel = re.match(r"^(\d+(?:[.,]\d+)?)\s+(.+)$", bruto)
    if contavel:
        return {"name": contavel.group(2).strip(), "quantity": contavel.group(1), "unit": "unidade"}
    raise ValueError(f"ingrediente sem quantidade padronizada: {texto}")


def minutos_totais(texto: str) -> int:
    normalizado = texto.lower().replace("horas", "hora").replace("minutos", "minuto")
    total = 0
    horas = re.search(r"(\d+)\s*hora", normalizado)
    minutos = re.search(r"(\d+)\s*minuto", normalizado) or re.search(r"(\d+)\s*min\b", normalizado)
    if horas:
        total += int(horas.group(1)) * 60
    if minutos:
        total += int(minutos.group(1))
    if horas or minutos:
        return total
    numero = re.search(r"(\d+)", normalizado)
    return int(numero.group(1)) if numero else 0


def porcoes_inteiras(texto: str) -> int:
    numero = re.search(r"(\d+)", texto)
    return int(numero.group(1)) if numero else 0


def recortar_excerpt(texto: str, limite: int = 160) -> str:
    base = re.sub(r"\s+", " ", texto).strip()
    if len(base) <= limite:
        return base
    return base[: limite - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def recortar_alt(titulo: str) -> str:
    alt = f"Foto ilustrativa de {titulo}".strip()
    if len(alt) > 240:
        alt = alt[:237].rstrip() + "..."
    return alt


def _fase_ambiente() -> int:
    bruto = os.getenv("AGENT_PHASE", "1").strip() or "1"
    try:
        return int(bruto)
    except ValueError as exc:
        raise RuntimeError("AGENT_PHASE deve ser um inteiro de 0 a 3") from exc
