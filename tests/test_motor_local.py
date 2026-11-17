"""Testes do motor local sem Ollama e sem PostgreSQL."""

import json

import httpx
import pytest

from integration.cliente_site import ClienteSite
from motor_local.database_manager import RecipeDatabaseManager
from motor_local.main_agent import run_fully_autonomous_pipeline, run_recipe_pipeline
from motor_local.publicador import AutonomousPublisher, interpretar_ingrediente, montar_payload_publicado
from motor_local.recipe_processor import (
    ChocoliciaRecipeAgent,
    duracao_iso8601,
    extrair_json,
    ingredientes_ausentes,
    meta_description,
    slugificar,
)


RECEITA = {
    "title": "Bolo de cenoura com ganache",
    "description": "Massa úmida de cenoura e uma ganache intensa, com corte macio e cobertura brilhante.",
    "prep_time": "20 minutos",
    "cook_time": "1 hora e 15 minutos",
    "servings": "8 porções",
    "difficulty": "Médio",
    "ingredients": ["200g de chocolate amargo 70%", "3 cenouras médias", "200g de farinha de trigo"],
    "steps": [
        "Rale as cenouras e misture com a farinha de trigo.",
        "Asse até a massa ficar firme.",
        "Derreta o chocolate amargo e cubra o bolo.",
    ],
    "tips": ["Sirva no mesmo dia."],
}


class Resposta:
    def __init__(self, texto: str, status: int = 200):
        self._texto = texto
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)

    def json(self):
        return {"response": self._texto}


class ClienteFalso:
    def __init__(self, texto: str):
        self.texto = texto
        self.payload = None

    def post(self, url, json):
        self.payload = json
        self.url = url
        return Resposta(self.texto)


class CursorFalso:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return (7,)

    def close(self):
        pass


class ConnFalsa:
    def __init__(self):
        self.cursor_obj = CursorFalso()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_extrai_json_com_cerca_markdown():
    bruto = "```json\n" + json.dumps({"title": "Brigadeiro"}) + "\n```"
    assert extrair_json(bruto)["title"] == "Brigadeiro"


def test_duracao_slug_e_meta():
    assert duracao_iso8601("20 minutos") == "PT20M"
    assert duracao_iso8601("1 hora e 15 minutos") == "PT1H15M"
    assert duracao_iso8601("45 min") == "PT45M"
    assert slugificar("Bolo de Açaí Cremoso!") == "bolo-de-acai-cremoso"
    meta = meta_description("Ganache", "x" * 400)
    assert len(meta) <= 160
    assert meta.endswith("...")


def test_ingrediente_ausente():
    assert ingredientes_ausentes(["100g de nozes"], ["Misture a farinha."]) == ["100g de nozes"]
    assert ingredientes_ausentes(RECEITA["ingredients"], RECEITA["steps"]) == []


def test_geracao_enriquece_seo_e_schema():
    cliente = ClienteFalso(json.dumps(RECEITA))
    agente = ChocoliciaRecipeAgent(cliente=cliente, model_name="mistral:7b-instruct")
    resultado = agente.generate_recipe("bolo de cenoura")
    assert resultado["status"] == "success"
    dados = resultado["data"]
    assert dados["slug"] == "bolo-de-cenoura-com-ganache"
    assert dados["schema_org"]["@type"] == "Recipe"
    assert dados["schema_org"]["prepTime"] == "PT20M"
    assert dados["schema_org"]["cookTime"] == "PT1H15M"
    assert dados["schema_org"]["recipeInstructions"][0]["@type"] == "HowToStep"
    assert cliente.payload["format"] == "json"
    assert cliente.payload["model"] == "mistral:7b-instruct"


def test_geracao_falha_quando_ingrediente_nao_entra_no_preparo():
    receita = dict(RECEITA, ingredients=RECEITA["ingredients"] + ["50g de nozes picadas"])
    agente = ChocoliciaRecipeAgent(cliente=ClienteFalso(json.dumps(receita)))
    resultado = agente.generate_recipe("bolo")
    assert resultado["status"] == "failed"
    assert "nozes" in resultado["error"]


def test_persistencia_separa_rascunho_e_falha():
    conn = ConnFalsa()
    banco = RecipeDatabaseManager(conectar=lambda _url: conn)
    recipe_id = banco.save_recipe_to_db(
        {"status": "success", "data": {**RECEITA, "slug": "bolo", "meta_description": "meta", "schema_org": {"@type": "Recipe"}}},
        topic="bolo",
    )
    assert recipe_id == 7
    assert "agent_recipe_drafts" in conn.cursor_obj.query
    assert conn.cursor_obj.params[-2] == "draft"
    assert conn.committed and conn.closed

    conn_falha = ConnFalsa()
    RecipeDatabaseManager(conectar=lambda _url: conn_falha).save_recipe_to_db(
        {"status": "failed", "error": "timeout"},
        topic="bolo",
    )
    assert conn_falha.cursor_obj.params[0] == "failed"
    assert "error_log" in conn_falha.cursor_obj.query


def test_pipeline_devolve_id(monkeypatch):
    agente = ChocoliciaRecipeAgent(cliente=ClienteFalso(json.dumps(RECEITA)))
    banco = RecipeDatabaseManager(conectar=lambda _url: ConnFalsa())
    resultado = run_recipe_pipeline("bolo de cenoura", agent=agente, db_manager=banco)
    assert resultado["recipe_id"] == 7
    assert resultado["status"] == "success"


def _receita_publicavel() -> dict:
    receita = dict(RECEITA)
    receita["steps"] = list(RECEITA["steps"]) + ["Deixe amornar antes de cortar."]
    receita["slug"] = "bolo-de-cenoura-com-ganache"
    receita["meta_description"] = "meta"
    receita["schema_org"] = {"@type": "Recipe"}
    return receita


def test_interpreta_quantidades_e_monta_contrato_publicado():
    assert interpretar_ingrediente("200g de chocolate amargo 70%")["unit"] == "g"
    assert interpretar_ingrediente("2 colheres de sopa de manteiga")["unit"] == "colher de sopa"
    assert interpretar_ingrediente("3 cenouras médias")["unit"] == "unidade"
    payload = montar_payload_publicado(
        _receita_publicavel(),
        subcategoria="bolos",
        run_id="abc123",
        model_name="mistral:7b-instruct",
        fase=1,
    )
    assert payload.status == "published"
    assert payload.difficulty == "Média"
    assert payload.prepTimeMin == 20
    assert payload.cookTimeMin == 75
    assert payload.servings == 8
    assert payload.cover.mode == "generate"


def test_pipeline_publica_quando_o_contrato_passa():
    receita = _receita_publicavel()
    agente = ChocoliciaRecipeAgent(cliente=ClienteFalso(json.dumps({k: v for k, v in receita.items() if k not in {"slug", "meta_description", "schema_org"}})))
    cliente = ClienteSite("https://chocolicia.test", token_publish="token-teste", fase=1, dry_run=True)
    banco = RecipeDatabaseManager(conectar=lambda _url: ConnFalsa())
    resultado = run_fully_autonomous_pipeline(
        "bolo de cenoura",
        agent=agente,
        db_manager=banco,
        publisher=AutonomousPublisher(cliente=cliente, subcategoria="bolos"),
    )
    assert resultado["status"] == "success"
    assert resultado["published"] is False
    assert resultado["site"]["situacao"] == "dry_run"
    assert resultado["recipe_id"] == 7


def test_pipeline_rejeita_receita_curta_sem_chamar_a_rede():
    agente = ChocoliciaRecipeAgent(cliente=ClienteFalso(json.dumps(RECEITA)))
    banco = RecipeDatabaseManager(conectar=lambda _url: ConnFalsa())
    resultado = run_fully_autonomous_pipeline(
        "bolo",
        agent=agente,
        db_manager=banco,
        publisher=AutonomousPublisher(
            cliente=ClienteSite("https://chocolicia.test", token_publish="token-teste", fase=1, dry_run=True),
            subcategoria="bolos",
        ),
    )
    assert resultado["status"] == "failed"
    assert resultado["published"] is False
    assert "4 passos" in resultado["error"]


def test_banco_exige_url_quando_nao_ha_conexao_injetada(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_AGENTE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL_AGENTE"):
        RecipeDatabaseManager().save_recipe_to_db({"status": "failed", "error": "x"})
