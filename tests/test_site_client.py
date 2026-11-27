"""Testes do cliente do site: sem rede, sem chaves reais."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from integration import site_client
from integration.site_client import SiteAPIError

COVER = {
    "mode": "stock",
    "provider": "pexels",
    "sourceImageUrl": "https://images.example.com/brigadeiro.jpg",
    "sourcePageUrl": "https://example.com/foto",
    "author": "Autora Teste",
    "license": "licença de teste",
    "attributionText": "Foto de Autora Teste",
}


def recipe_payload(**overrides) -> dict:
    payload = {
        "title": "Brigadeiro de colher",
        "slug": "brigadeiro-de-colher",
        "excerpt": "Brigadeiro cremoso de colher para festas.",
        "tags": ["brigadeiro"],
        "cover": COVER,
        "coverImageAlt": "Tigela com brigadeiro de colher",
        "status": "draft",
        "aiModel": "modelo-teste",
        "generationMeta": {"run_id": "run-1"},
        "intro": "Texto local",
        "restTimeMin": 10,
        "yieldLabel": "8 porções",
        "subcategorySlug": "brigadeiros",
        "prepTimeMin": 10,
        "cookTimeMin": 15,
        "servings": 8,
        "difficulty": "Fácil",
        "ingredients": [{"name": "Base", "items": [{"name": "leite condensado", "quantity": "1", "unit": "lata"}]}],
        "steps": [{"instruction": "a"}, {"instruction": "b"}, {"instruction": "c"}, {"instruction": "d"}],
        "tips": [],
        "faq": [],
    }
    payload.update(overrides)
    return payload


def response(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body or {}, request=httpx.Request("POST", "https://site.example.com"))


class BaseUrlTests(unittest.TestCase):
    def test_precedencia_e_padrao(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(site_client.resolve_base_url(), "https://www.chocolicia.site")
        with patch.dict("os.environ", {"SITE_BASE_URL": "https://preview.example.com/"}, clear=True):
            self.assertEqual(site_client.resolve_base_url(), "https://preview.example.com")
        env = {"SITE_BASE_URL": "https://a.example.com", "CHOCOLICIA_API_URL": "https://b.example.com"}
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(site_client.resolve_base_url(), "https://a.example.com")

    def test_preview_nao_aponta_para_producao(self):
        with patch.dict("os.environ", {"TARGET": "preview"}, clear=True):
            with self.assertRaisesRegex(SiteAPIError, "TARGET=preview"):
                site_client.resolve_base_url()
        env = {"TARGET": "preview", "CHOCOLICIA_API_URL": "https://www.chocolicia.site"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(SiteAPIError, "TARGET=preview"):
                site_client.resolve_base_url()
        env = {"TARGET": "preview", "SITE_BASE_URL": "https://preview.example.com"}
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(site_client.resolve_base_url(), "https://preview.example.com")

    def test_endpoint_por_tipo(self):
        with patch.dict("os.environ", {"SITE_BASE_URL": "https://s.example.com"}, clear=True):
            self.assertEqual(site_client.resolve_endpoint("receita"), "https://s.example.com/api/recipes")
            with self.assertRaisesRegex(SiteAPIError, "somente receitas"):
                site_client.resolve_endpoint("dica")


class TokenTests(unittest.TestCase):
    def test_token_por_status(self):
        env = {"CHOCOLICIA_TOKEN_DRAFT": "draft-token", "SITE_TOKEN_PUBLISH": "publish-token"}
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(site_client.select_token("draft"), "draft-token")
            self.assertEqual(site_client.select_token("published"), "publish-token")

    def test_cron_secret_nao_e_usado_como_token_do_site(self):
        with patch.dict("os.environ", {"CRON_SECRET": "segredo-do-cron"}, clear=True):
            with self.assertRaisesRegex(SiteAPIError, "RECIPES_AGENT_TOKEN"):
                site_client.select_token("draft")


class PayloadTests(unittest.TestCase):
    def test_categoria_derivada_da_subcategoria(self):
        self.assertEqual(site_client.category_for_subcategory("brigadeiros"), "Brigadeiros e docinhos")
        self.assertEqual(site_client.category_for_subcategory("bolos-caseiros"), "Bolos")
        with self.assertRaisesRegex(SiteAPIError, "não existe no site"):
            site_client.category_for_subcategory("brigadeiros-e-docinhos")

    def test_conversao_para_o_schema_do_site(self):
        body = site_client.to_site_recipe_payload(recipe_payload())
        self.assertEqual(body["category"], "Brigadeiros e docinhos")
        self.assertEqual(body["coverImageUrl"], COVER["sourceImageUrl"])
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["generationMeta"]["run_id"], "run-1")
        self.assertEqual(body["generationMeta"]["cover"]["author"], "Autora Teste")
        for local_only in ("cover", "intro", "restTimeMin", "yieldLabel"):
            self.assertNotIn(local_only, body)

    def test_capa_gerada_nao_e_suportada(self):
        payload = recipe_payload(cover={"mode": "generate", "imagePrompt": "prato pronto"})
        with self.assertRaisesRegex(SiteAPIError, "coverImageUrl"):
            site_client.to_site_recipe_payload(payload)


class PostContentTests(unittest.TestCase):
    ENV = {
        "TARGET": "preview",
        "SITE_BASE_URL": "https://preview.example.com",
        "CHOCOLICIA_TOKEN_DRAFT": "token-de-teste",
    }

    def test_envia_receita_ao_endpoint_do_site(self):
        with patch.dict("os.environ", self.ENV, clear=True), patch.object(
            site_client.httpx, "post", return_value=response(201, {"status": "draft", "slug": "brigadeiro-de-colher"})
        ) as post:
            result = site_client.post_content(recipe_payload(), "receita", "brigadeiro")
        self.assertEqual(result["status"], "draft")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://preview.example.com/api/recipes")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-de-teste")
        self.assertEqual(kwargs["json"]["category"], "Brigadeiros e docinhos")
        self.assertNotIn("cover", kwargs["json"])

    def test_nao_envia_nada_sem_token(self):
        with patch.dict("os.environ", {"SITE_BASE_URL": "https://preview.example.com"}, clear=True), patch.object(
            site_client.httpx, "post"
        ) as post:
            with self.assertRaises(SiteAPIError):
                site_client.post_content(recipe_payload(), "receita", "brigadeiro")
        post.assert_not_called()

    def test_erro_4xx_nao_e_repetido(self):
        with patch.dict("os.environ", self.ENV, clear=True), patch.object(
            site_client.httpx, "post", return_value=response(401, {"error": "Não autorizado."})
        ) as post:
            with self.assertRaises(SiteAPIError) as caught:
                site_client.post_content(recipe_payload(), "receita", "brigadeiro")
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(post.call_count, 1)

    def test_erro_5xx_nao_repete_post_ambiguo(self):
        with patch.dict("os.environ", self.ENV, clear=True), patch.object(
            site_client.httpx, "post", return_value=response(502)
        ) as post:
            with self.assertRaises(SiteAPIError) as caught:
                site_client.post_content(recipe_payload(), "receita", "brigadeiro")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("Não repeti o POST", str(caught.exception))
        self.assertEqual(post.call_count, 1)

    def test_503_tem_mensagem_especifica_e_nao_repete(self):
        with patch.dict("os.environ", self.ENV, clear=True), patch.object(
            site_client.httpx, "post", return_value=response(503, {"error": "token não configurado"})
        ) as post:
            with self.assertRaises(SiteAPIError) as caught:
                site_client.post_content(recipe_payload(), "receita", "brigadeiro")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("HTTP 503", str(caught.exception))
        self.assertEqual(post.call_count, 1)

    def test_cliente_legado_recusa_dicas_e_exige_cliente_v1(self):
        payload = {"status": "published", "type": "tip", "generationMeta": {"run_id": "run-2"}}
        with patch.dict("os.environ", self.ENV, clear=True), patch.object(site_client.httpx, "post") as post:
            with self.assertRaisesRegex(SiteAPIError, "somente receitas"):
                site_client.post_content(payload, "dica", "como-evitar")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
