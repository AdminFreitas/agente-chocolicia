"""Testes do fluxo atual de dicas: LLM e cliente do site simulados."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import gerar_dica

CORPO = "## Dica prática\n\n" + ("Trabalhe em pequenas etapas e observe a textura antes de avançar. " * 14)
TEXTO = (
    "TITULO: Como acertar o ponto do brigadeiro\n"
    "RESUMO: Veja como reconhecer a textura correta do brigadeiro durante o preparo.\n"
    "TEMPO_LEITURA: 4 min\n===CORPO===\n"
    + CORPO
)
META = {"texto": TEXTO, "provedor": "gemini", "modelo": "gemini-3.8-flash", "tempo_ms": 0}
COVER = {
    "mode": "stock",
    "provider": "pexels",
    "sourceImageUrl": "https://images.example.com/brigadeiro.jpg",
    "sourcePageUrl": "https://example.com/foto",
    "author": "Autora de teste",
    "license": "Licença de teste",
    "attributionText": "Foto: Autora de teste",
}


class DicaFlowTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "CHOCOLICIA_COVER_JSON": json.dumps(COVER),
            "AGENT_PHASE": "1",
            "SITE_BASE_URL_PREVIEW": "https://preview.example.com",
            "SITE_TOKEN_PUBLISH_PREVIEW": "publish-test-token",
            "SITE_TOKEN_DRAFT_PREVIEW": "draft-test-token",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = patch.object(gerar_dica, "OUTPUT_DIR", Path(self.tmp.name))
        self.output.start()
        self.addCleanup(self.output.stop)

        self.llm = patch.object(
            gerar_dica.llm_service,
            "gerar_texto_com_metadados",
            return_value=META,
        )
        self.llm_mock = self.llm.start()
        self.addCleanup(self.llm.stop)

    def test_dry_run_valida_payload_sem_publicar(self):
        with patch.object(gerar_dica, "ClienteSite") as cliente:
            result = gerar_dica.gerar_dica("preparo", dry_run=True)

        cliente.assert_not_called()
        self.assertFalse(result["enviado"])
        payload = result["payload"]
        self.assertEqual(payload["type"], "tip")
        self.assertEqual(payload["tipTopic"], "preparo")
        self.assertEqual(payload["status"], "published")
        self.assertEqual(payload["slug"], "como-acertar-o-ponto-do-brigadeiro")
        self.assertEqual(payload["aiModel"], "gemini:gemini-3.8-flash")
        self.assertGreaterEqual(len(payload["bodyMd"]), 600)

    def test_publicacao_usa_cliente_v1_e_token_do_preview(self):
        resposta_site = SimpleNamespace(id="article-1", slug="como-acertar-o-ponto-do-brigadeiro", status="published")
        with patch.object(gerar_dica, "ClienteSite") as cliente_cls:
            cliente = cliente_cls.return_value
            cliente.criar_artigo.return_value = resposta_site
            result = gerar_dica.gerar_dica("preparo", target="preview")

        cliente_cls.assert_called_once()
        args, kwargs = cliente_cls.call_args
        self.assertEqual(args[0], "https://preview.example.com")
        self.assertEqual(kwargs["token_publish"], "publish-test-token")
        self.assertEqual(kwargs["contract"], "v1")
        self.assertTrue(kwargs["articles_enabled"])
        cliente.criar_artigo.assert_called_once()
        self.assertTrue(result["enviado"])
        self.assertEqual(result["site"]["status"], "published")

    def test_sem_token_de_publicacao_nao_chama_cliente(self):
        with patch.dict(os.environ, {"SITE_TOKEN_PUBLISH_PREVIEW": ""}), patch.object(
            gerar_dica, "ClienteSite"
        ) as cliente:
            with self.assertRaisesRegex(gerar_dica.DicaInvalida, "token de publicação"):
                gerar_dica.gerar_dica("preparo", target="preview")
        cliente.assert_not_called()

    def test_topico_desconhecido_e_rejeitado(self):
        with self.assertRaises(gerar_dica.DicaInvalida):
            gerar_dica.gerar_dica("assunto-inexistente", dry_run=True)

    def test_resposta_curta_e_rejeitada(self):
        self.llm_mock.return_value = {
            **META,
            "texto": "TITULO: Dica curta\nRESUMO: Texto curto.\nTEMPO_LEITURA: 1 min\n===CORPO===\nSó uma frase.",
        }
        with self.assertRaises(gerar_dica.DicaInvalida):
            gerar_dica.gerar_dica("preparo", dry_run=True)


if __name__ == "__main__":
    unittest.main()
