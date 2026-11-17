from __future__ import annotations
from dataclasses import dataclass
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
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type":"application/json"},
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
            provedor="openai-compatible",
            modelo=config["model"],
            familia=family,
        )
