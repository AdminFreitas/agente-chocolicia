import base64
import json as json_lib

import httpx

from runtime_adapters.llm import OpenAICompatibleVisionVerifier


def test_verificador_visual_envia_imagem_em_memoria_e_exige_quatro_booleanos(monkeypatch):
    chamado = {}

    def fake_post(url, *, headers, json: dict, timeout):
        chamado.update(url=url, headers=headers, payload=json, timeout=timeout)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": json_lib.dumps({
                "prato_correto": True,
                "sem_pessoas": True,
                "sem_texto_ou_marca": True,
                "enquadramento_ok": True,
            })}}],
        })

    monkeypatch.setattr("runtime_adapters.llm.httpx.post", fake_post)
    verifier = OpenAICompatibleVisionVerifier(
        "unused", "http://127.0.0.1:11434/v1", "vision-model", provider="ollama"
    )
    result = verifier.verificar(b"image-bytes", "image/jpeg", "brigadeiro")

    image_url = chamado["payload"]["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.endswith(base64.b64encode(b"image-bytes").decode("ascii"))
    assert result.aprovado is True
