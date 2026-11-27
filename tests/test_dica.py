"""Testes do fluxo de dicas pelo endpoint dedicado do site."""
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
    "TEMPO_LEITURA: 4 min\n===CORPO===\n" + CORPO
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
            "SITE_TOKEN_DRAFT_PREVIEW": "integration-token",
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

    def test_dry_run_gera_payload_do_contrato_tips_sem_rede(self):
        with patch.object(gerar_dica, "ClienteSite") as cliente:
            result = gerar_dica.gerar_dica("preparo", dry_run=True)
        cliente.assert_not_called()
        payload = result["payload"]
        self.assertFalse(result["enviado"])
        self.assertEqual(payload["topicSlug"], "preparo")
        self.assertEqual(payload["tipType"], "dica")
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["reviewStatus"], "pending")
        self.assertEqual(payload["coverImageUrl"], COVER["sourceImageUrl"])
        self.assertGreaterEqual(len(payload["content"]), 600)
        self.assertEqual(len(payload["agentIdempotencyKey"]), 64)
        self.assertNotIn("bodyMd", payload)
        self.assertNotIn("tipTopic", payload)

    def test_envio_chama_somente_cliente_dedicado_de_dicas(self):
        resposta = SimpleNamespace(
            situacao="criado", http_status=201, id="tip-1",
            slug="como-acertar-o-ponto-do-brigadeiro", status="draft",
        )
        with patch.object(gerar_dica, "ClienteSite") as cliente_cls:
            cliente = cliente_cls.return_value
            cliente.criar_dica.return_value = resposta
            result = gerar_dica.gerar_dica("preparo", target="preview")
        args, kwargs = cliente_cls.call_args
        self.assertEqual(args[0], "https://preview.example.com")
        cliente.criar_dica.assert_called_once()
        sent = cliente.criar_dica.call_args.args[0]
        self.assertEqual(sent["topicSlug"], "preparo")
        self.assertEqual(result["site"]["id"], "tip-1")

    def test_publicacao_define_review_approved(self):
        with patch.object(gerar_dica, "ClienteSite") as cliente_cls:
            cliente_cls.return_value.criar_dica.return_value = SimpleNamespace(
                situacao="criado", http_status=201, id="tip-2",
                slug="como-acertar-o-ponto-do-brigadeiro", status="published",
            )
            result = gerar_dica.gerar_dica("preparo", target="preview", publish=True)
        self.assertEqual(result["payload"]["status"], "published")
        self.assertEqual(result["payload"]["reviewStatus"], "approved")

    def test_topico_desconhecido_e_rejeitado(self):
        with self.assertRaises(gerar_dica.DicaInvalida):
            gerar_dica.gerar_dica("assunto-inexistente", dry_run=True)

    def test_conteudo_curto_e_rejeitado(self):
        self.llm_mock.return_value = {
            **META,
            "texto": "TITULO: Dica curta\nRESUMO: Texto curto.\nTEMPO_LEITURA: 1 min\n===CORPO===\nSó uma frase.",
        }
        with self.assertRaises(gerar_dica.DicaInvalida):
            gerar_dica.gerar_dica("preparo", dry_run=True)


if __name__ == "__main__":
    unittest.main()
