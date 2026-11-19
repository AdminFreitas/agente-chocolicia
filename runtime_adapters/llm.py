from __future__ import annotations
import base64
from dataclasses import dataclass
import json
import httpx
from services.llm_cliente import RespostaLLM

class LLMConfigurationError(RuntimeError): pass
class IndependentFamilyUnavailable(LLMConfigurationError): pass

@dataclass
class OpenAICompatibleGenerator:
    api_key: str
    base_url: str
    models: dict[str, dict]
    timeout: float = 90.0
    provider: str = "openai-compatible"

    def __call__(self, tarefa: str, prompt: str, *, familia_excluida: str | None = None):
        key = {"criacao":"creation", "reparo":"repair", "revisao":"review",
             "extracao":"extraction", "seo":"seo", "visao":"vision"}.get(tarefa, tarefa)
        config = self.models.get(key)
        if not config or not config.get("model") or not config.get("family"):
            raise LLMConfigurationError(f"Modelo/família não configurados para tarefa {key}")
        family = config["family"]
        if familia_excluida and family == familia_excluida:
            raise IndependentFamilyUnavailable(
                f"A tarefa {key} está configurada na mesma família excluída ({family}); "
                "configure uma família independente antes da revisão."
            )
        headers = {"Content-Type": "application/json"}
        if self.provider != "ollama":
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={"model":config["model"],"messages":[{"role":"user","content":prompt}],
                  "temperature":0.4},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Resposta do provedor LLM fora do formato Chat Completions") from exc
        return RespostaLLM(
            texto=content,
            provedor=self.provider,
            modelo=config["model"],
            familia=family,
        )


@dataclass
class OpenAICompatibleVisionVerifier:
    api_key: str
    base_url: str
    model: str
    timeout: float = 90.0
    provider: str = "openai-compatible"

    def verificar(self, imagem: bytes, mime: str, esperado: str):
        from services.image_providers.selector import ResultadoVisao

        headers = {"Content-Type": "application/json"}
        if self.provider != "ollama":
            headers["Authorization"] = f"Bearer {self.api_key}"
        prompt = (
            "Verifique a imagem de comida anexada para uma capa de receita. "
            f"Prato esperado: {esperado}. Responda somente JSON com quatro booleanos: "
            "prato_correto, sem_pessoas, sem_texto_ou_marca, enquadramento_ok. "
            "Marque false quando não puder confirmar."
        )
        data_url = f"data:{mime};base64,{base64.b64encode(imagem).decode('ascii')}"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            values = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Resposta do verificador visual fora do formato JSON") from exc
        fields = (
            "prato_correto", "sem_pessoas", "sem_texto_ou_marca", "enquadramento_ok"
        )
        if not isinstance(values, dict) or any(type(values.get(name)) is not bool for name in fields):
            raise RuntimeError("Resposta do verificador visual sem os quatro booleanos obrigatórios")
        return ResultadoVisao(
            **{name: values[name] for name in fields},
            observacao="Verificação visual automática",
        )
