"""Geração de receita via Ollama, saneamento do JSON e metadados de SEO."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_PALAVRAS_VAZIAS = {
    "de", "da", "do", "das", "dos", "com", "sem", "para", "por", "em", "no", "na",
    "nos", "nas", "e", "ou", "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "g", "kg", "mg", "ml", "l", "xicara", "xicaras", "colher", "colheres",
    "pitada", "pitadas", "unidade", "unidades", "cerca", "aprox", "qb",
}


class RecipeOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=8, max_length=180)
    description: str = Field(min_length=40)
    prep_time: str = Field(min_length=2, max_length=40)
    cook_time: str = Field(min_length=2, max_length=40)
    servings: str = Field(min_length=2, max_length=40)
    difficulty: str
    ingredients: list[str] = Field(min_length=2)
    steps: list[str] = Field(min_length=3)
    tips: list[str] = Field(default_factory=list)

    def modelo_validado(self) -> "RecipeOutput":
        permitidas = {"Fácil", "Médio", "Avançado"}
        if self.difficulty not in permitidas:
            raise ValueError(f"dificuldade fora do vocabulário: {self.difficulty}")
        return self


class ChocoliciaRecipeAgent:
    def __init__(
        self,
        ollama_host: str | None = None,
        model_name: str | None = None,
        cliente: httpx.Client | None = None,
        timeout: float = 120,
    ):
        self.ollama_host = (ollama_host or os.getenv("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL") or "mistral:7b-instruct"
        self._cliente = cliente
        self.timeout = timeout

    def _generate_prompt(self, recipe_topic: str) -> str:
        return f"""Você é um chef confeiteiro sênior e redator gastronômico especialista no site Chocolícia.
Gere uma receita original, apetitosa e tecnicamente rigorosa sobre: {recipe_topic}.

DIRETRIZES DE ESCRITA:
- Use linguagem natural, fluida e sofisticada, evitando clichês e introduções robóticas de IA.
- Garanta que todos os ingredientes listados sejam rigorosamente utilizados no modo de preparo.
- Organize o modo de preparo em etapas claras e sequenciais.
- Não afirme que a receita foi testada na cozinha do Chocolícia.

Retorne APENAS um objeto JSON válido com as seguintes chaves:
- "title": Título atraente da receita.
- "description": Breve descrição sensorial e acolhedora (máx. 2 parágrafos).
- "prep_time": Tempo de preparo (ex: "20 minutos").
- "cook_time": Tempo de cozimento/forno (ex: "45 minutos").
- "servings": Rendimento (ex: "8 porções").
- "difficulty": Dificuldade ("Fácil", "Médio" ou "Avançado").
- "ingredients": Lista de strings com quantidades padronizadas.
- "steps": Lista de strings detalhando o passo a passo.
- "tips": Lista opcional de dicas culinárias e de conservação.
"""

    def generate_recipe(self, topic: str) -> dict[str, Any]:
        prompt = self._generate_prompt(topic)
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.7},
        }
        try:
            raw_text = self._chamar_ollama(payload)
            recipe = RecipeOutput.model_validate(extrair_json(raw_text)).modelo_validado()
            ausentes = ingredientes_ausentes(recipe.ingredients, recipe.steps)
            if ausentes:
                raise ValueError("ingredientes não usados no modo de preparo: " + "; ".join(ausentes))
            data = recipe.model_dump()
            data["slug"] = slugificar(data["title"])
            data["meta_description"] = meta_description(data["title"], data["description"])
            data["schema_org"] = schema_org_recipe(data)
            return {"status": "success", "data": data}
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    def _chamar_ollama(self, payload: dict[str, Any]) -> str:
        url = f"{self.ollama_host}/api/generate"
        if self._cliente is not None:
            response = self._cliente.post(url, json=payload)
        else:
            response = httpx.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        corpo = response.json()
        texto = corpo.get("response", "")
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("resposta vazia do Ollama")
        return texto


def extrair_json(texto: str) -> dict[str, Any]:
    limpo = re.sub(r"```(?:json)?", "", texto).strip()
    try:
        dados = json.loads(limpo)
    except json.JSONDecodeError:
        inicio = limpo.find("{")
        fim = limpo.rfind("}")
        if inicio < 0 or fim <= inicio:
            raise
        dados = json.loads(limpo[inicio : fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("o modelo não devolveu um objeto JSON")
    return dados


def slugificar(titulo: str, maximo: int = 80) -> str:
    ascii_titulo = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_titulo.lower()).strip("-")
    return slug[:maximo].strip("-")


def meta_description(titulo: str, descricao: str, limite: int = 160) -> str:
    base = re.sub(r"\s+", " ", f"Aprenda a fazer {titulo} com esta receita passo a passo do Chocolícia. {descricao}").strip()
    if len(base) <= limite:
        return base
    corte = base[: limite - 3].rsplit(" ", 1)[0].rstrip(".,;:")
    return corte + "..."


def duracao_iso8601(texto: str) -> str:
    """Converte '1 hora e 20 minutos' em PT1H20M. Sem número, devolve PT0M."""
    normalizado = texto.lower().replace("minutos", "minuto").replace("horas", "hora").replace("segundos", "segundo")
    partes: list[str] = []
    for nome, codigo in (("hora", "H"), ("minuto", "M"), ("segundo", "S")):
        encontrado = re.search(rf"(\d+)\s*{nome}", normalizado)
        if encontrado:
            partes.append(f"{int(encontrado.group(1))}{codigo}")
    if not partes:
        minutos = re.search(r"(\d+)\s*min\b", normalizado) or re.search(r"(\d+)", normalizado)
        if minutos:
            return f"PT{int(minutos.group(1))}M"
        return "PT0M"
    return "PT" + "".join(partes)


def schema_org_recipe(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org/",
        "@type": "Recipe",
        "name": data["title"],
        "description": data["description"],
        "prepTime": duracao_iso8601(data["prep_time"]),
        "cookTime": duracao_iso8601(data["cook_time"]),
        "recipeYield": data["servings"],
        "recipeIngredient": data["ingredients"],
        "recipeInstructions": [{"@type": "HowToStep", "text": step} for step in data["steps"]],
    }


def ingredientes_ausentes(ingredients: list[str], steps: list[str]) -> list[str]:
    preparo = _normalizar(" ".join(steps))
    ausentes = []
    for item in ingredients:
        tokens = [t for t in _normalizar(item).split() if len(t) >= 4 and t not in _PALAVRAS_VAZIAS and not t.isdigit()]
        if tokens and not any(token in preparo for token in tokens):
            ausentes.append(item)
    return ausentes


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()
