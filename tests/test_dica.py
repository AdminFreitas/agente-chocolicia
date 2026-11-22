"""Fluxo --dica: LLM simulado, site simulado (httpx.post), sem rede nem chaves reais."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx

import rodar_agente
from integration.site_client import SiteAPIError
from pipeline import gerar_dica

CORPO = "## Dica\n\n" + ("Temperar o chocolate com paciência garante brilho e estalo. " * 20)
TEXTO = f"TITULO: Como temperar chocolate sem erro\nRESUMO: Passo a passo simples.\nTEMPO_LEITURA: 4 min\n===CORPO===\n{CORPO}"
META = {"texto": TEXTO, "provedor": "gemini", "modelo": "gemini-3.8-flash", "tempo_ms": 0}
SITE_ENV = {
    "SITE_BASE_URL": "https://preview.example.com",
    "SITE_TOKEN_DRAFT": "token-da-integracao",
    "CRON_SECRET": "nao-deve-ser-usado",
    "TARGET": "preview",
}


def resp(status, body=None):
    return httpx.Response(status, json=body or {}, request=httpx.Request("POST", "https://x"))


class DicaFlowTests(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, SITE_ENV, clear=False)
        p.start()
        self.addCleanup(p.stop)
        t = patch.object(gerar_dica, "OUTPUT_DIR", __import__("pathlib").Path(__import__("tempfile").mkdtemp()))
        t.start()
        self.addCleanup(t.stop)
        llm = patch.object(gerar_dica.llm_service, "gerar_texto_com_metadados", return_value=META)
        self.llm = llm.start()
        self.addCleanup(llm.stop)

    def test_dry_run_gera_e_valida_sem_enviar(self):
        with patch("httpx.post") as post:
            r = gerar_dica.gerar_dica("preparo", dry_run=True)
        post.assert_not_called()
        self.assertFalse(r["enviado"])
        p = r["payload"]
        self.assertEqual(p["articleType"], "dica")
        self.assertEqual(p["topicSlug"], "preparo")
        self.assertEqual(p["status"], "draft")
        self.assertEqual(p["slug"], "como-temperar-chocolate-sem-erro")
        self.assertEqual(p["aiModel"], "gemini:gemini-3.8-flash")

    def test_envio_usa_url_token_e_corpo_estrito(self):
        with patch("httpx.post", return_value=resp(201, {"id": "1"})) as post:
            r = gerar_dica.gerar_dica("preparo")
        self.assertTrue(r["enviado"])
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://preview.example.com/api/articles")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-da-integracao")
        self.assertNotIn("nao-deve-ser-usado", str(kwargs["headers"]))
        allowed = {"title", "slug", "excerpt", "content", "articleType", "status", "categoryId", "topicId",
                   "categorySlug", "topicSlug", "coverImageUrl", "coverImageAlt", "seoTitle", "seoDescription",
                   "author", "aiModel", "generationMeta", "tags", "images"}
        self.assertTrue(set(kwargs["json"]) <= allowed, set(kwargs["json"]) - allowed)

    def test_sem_token_falha(self):
        with patch.dict(os.environ, {"SITE_TOKEN_DRAFT": ""}), patch("httpx.post") as post:
            with self.assertRaises(SiteAPIError):
                gerar_dica.gerar_dica("preparo")
        post.assert_not_called()

    def test_slug_duplicado_409_interrompe_sem_criar_alternativo(self):
        with patch("httpx.post", return_value=resp(409, {"code": "duplicate_slug"})) as post:
            with self.assertRaises(SiteAPIError) as caught:
                gerar_dica.gerar_dica("preparo")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("Não criei um slug alternativo", str(caught.exception))
        self.assertEqual(post.call_count, 1)

    def test_erro_401_nao_tenta_novamente(self):
        with patch("httpx.post", return_value=resp(401)) as post:
            with self.assertRaises(SiteAPIError) as ctx:
                gerar_dica.gerar_dica("preparo")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(post.call_count, 1)

    def test_corpo_curto_e_assunto_invalido_reprovam(self):
        curto = dict(META, texto="TITULO: X\nRESUMO: y\n===CORPO===\ncurto")
        self.llm.return_value = curto
        with self.assertRaises(gerar_dica.DicaInvalida):
            gerar_dica.gerar_dica("preparo", dry_run=True)
        with self.assertRaises(gerar_dica.DicaInvalida):
            gerar_dica.gerar_dica("inexistente", dry_run=True)

    def test_falha_do_llm_propaga(self):
        self.llm.side_effect = RuntimeError("sem chave")
        with self.assertRaises(RuntimeError):
            gerar_dica.gerar_dica("preparo", dry_run=True)

    def test_dicas_sao_sempre_rascunhos_em_qualquer_ambiente(self):
        with patch.dict(os.environ, {"AGENT_PHASE": "1"}):
            self.assertEqual(gerar_dica._status("producao"), "draft")
            self.assertEqual(gerar_dica._status("preview"), "draft")
        with patch.dict(os.environ, {"AGENT_PHASE": "0"}):
            self.assertEqual(gerar_dica._status("producao"), "draft")


class CliTests(unittest.TestCase):
    def test_dica_chama_pipeline_e_retorna_zero(self):
        with patch("pipeline.gerar_dica.gerar_dica", return_value={"enviado": False, "payload": {"slug": "s"}}) as g:
            code = rodar_agente.main(["--dica", "--assunto", "negocios", "--target", "preview", "--dry-run"])
        self.assertEqual(code, 0)
        g.assert_called_once_with("negocios", target="preview", dry_run=True)

    def test_dica_falha_retorna_um(self):
        with patch("pipeline.gerar_dica.gerar_dica", side_effect=RuntimeError("x")):
            self.assertEqual(rodar_agente.main(["--dica"]), 1)

    def test_artigo_continua_funcionando(self):
        with patch.object(rodar_agente, "rodar_artigo", return_value=True) as a, \
             patch.object(rodar_agente, "rodar_dica") as d:
            self.assertEqual(rodar_agente.main(["--artigo"]), 0)
        a.assert_called_once()
        d.assert_not_called()

    def test_sem_argumentos_e_erro(self):
        with self.assertRaises(SystemExit):
            rodar_agente.main([])

    def test_importar_nao_exige_banco(self):
        import importlib, sys
        sys.modules.pop("config.database", None)
        importlib.reload(rodar_agente)
        self.assertNotIn("config.database", sys.modules)


if __name__ == "__main__":
    unittest.main()
