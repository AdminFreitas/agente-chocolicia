import json
import os
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Callable

import httpx

from config.settings import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    FALLBACK_ORDER,
)


class ModeloNaoAprovado(RuntimeError):
    pass


CONTADORES = {"requisicoes": 0, "tokens": 0}
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "modelos_aprovados.json"


def _remover_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _gerar_slug(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9\s-]", "", texto.lower())
    texto = re.sub(r"\s+", "-", texto.strip())
    return re.sub(r"-+", "-", texto)[:80]


def _parsear_resposta(texto: str) -> dict:
    texto = re.sub(r"^```[a-zA-Z]*\n?", "", texto.strip(), flags=re.MULTILINE)
    texto = re.sub(r"\n?```$", "", texto)
    linhas = texto.splitlines()
    titulo = None
    resumo = ""
    tempo_leitura = "5 min"
    indice_corpo = len(linhas)

    for indice, linha_original in enumerate(linhas):
        linha = linha_original.strip()
        if not linha:
            continue
        if linha == "===CORPO===":
            indice_corpo = indice + 1
            break
        normalizada = _remover_acentos(linha).upper()
        if normalizada.startswith("TITULO:"):
            titulo = linha.split(":", 1)[1].strip()
        elif normalizada.startswith("RESUMO:"):
            resumo = linha.split(":", 1)[1].strip()
        elif normalizada.startswith("TEMPO_LEITURA:"):
            tempo_leitura = linha.split(":", 1)[1].strip()
        else:
            indice_corpo = indice
            break

    corpo = "\n".join(linhas[indice_corpo:]).strip()
    if not titulo or not corpo:
        raise ValueError("Resposta incompleta do modelo (faltou titulo ou corpo)")
    return {"titulo": titulo, "excerpt": resumo, "readTime": tempo_leitura, "corpo": corpo}


parsear_resposta_padrao = _parsear_resposta
gerar_slug = _gerar_slug


def _modelos_aprovados(tarefa: str) -> list[dict]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as arquivo:
        config = json.load(arquivo)
    return config.get(tarefa, [])


def _ordenar_modelos_por_fallback(modelos: list[dict]) -> list[dict]:
    """Ordena somente modelos aprovados, respeitando a preferência global."""
    ordem = [item.strip().lower() for item in FALLBACK_ORDER.split(",") if item.strip()]
    prioridade = {provedor: indice for indice, provedor in enumerate(ordem)}
    return [
        item
        for _, item in sorted(
            enumerate(modelos),
            key=lambda par: (
                prioridade.get(str(par[1].get("provedor", "")).strip().lower(), len(prioridade)),
                par[0],
            ),
        )
    ]


def _chave_provedor(provedor: str) -> str | None:
    if provedor == "ollama":
        return "local"  # Ollama não exige chave de API; disponibilidade é validada na chamada.
    return {
        "gemini": GEMINI_API_KEY,
        "groq": GROQ_API_KEY,
        "openrouter": OPENROUTER_API_KEY,
    }.get(provedor)


def _modelo_resolvido(item: dict) -> str:
    modelo = item.get("modelo", "").strip()
    if modelo:
        return modelo
    padrao = {
        "gemini": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "groq": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "openrouter": os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
        "ollama": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
    }
    return padrao.get(item["provedor"], "")


def _novo_cliente_gemini():
    from google import genai

    return genai.Client(api_key=GEMINI_API_KEY)


def _chamar_gemini(prompt: str, modelo: str) -> str:
    # Mantém uma referência forte ao cliente durante toda a chamada.
    # O context manager fecha o transporte ao concluir, inclusive em exceções.
    # Um cliente novo por requisição evita compartilhar clientes entre execuções.
    with _novo_cliente_gemini() as cliente:
        resposta = cliente.models.generate_content(
            model=modelo,
            contents=prompt,
        )
        if not getattr(resposta, "text", None):
            raise RuntimeError("Resposta vazia do Gemini")
        return resposta.text


def _chamar_openai_compativel(prompt: str, modelo: str, provedor: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions" if provedor == "groq" else "https://openrouter.ai/api/v1/chat/completions"
    chave = GROQ_API_KEY if provedor == "groq" else OPENROUTER_API_KEY
    resposta = httpx.post(
        url,
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        json={"model": modelo, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    return dados["choices"][0]["message"]["content"]


def _chamar_provedor(item: dict, prompt: str) -> str:
    provedor = item["provedor"].lower()
    modelo = _modelo_resolvido(item)
    if not modelo:
        raise ModeloNaoAprovado(f"Modelo aprovado sem identificador para {provedor}")
    if provedor == "ollama":
        from integration.ollama_provider import gerar_texto as gerar_ollama
        return gerar_ollama(prompt, modelo)
    if provedor == "gemini":
        return _chamar_gemini(prompt, modelo)
    if provedor in {"groq", "openrouter"}:
        return _chamar_openai_compativel(prompt, modelo, provedor)
    raise ModeloNaoAprovado(f"Provedor nao suportado: {provedor}")


def _contabilizar(prompt: str, texto: str) -> None:
    CONTADORES["tokens"] += len((prompt + texto).split())


class RespostaProvedorVazia(RuntimeError):
    """Resposta vazia: erro transitório que permite tentar outro provedor aprovado."""


def _codigo_http(exc: Exception) -> int | None:
    for obj in (exc, getattr(exc, "response", None), getattr(exc, "cause", None)):
        if obj is None:
            continue
        for attr in ("status_code", "code"):
            value = getattr(obj, attr, None)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def _erro_configuracao(exc: Exception) -> bool:
    code = _codigo_http(exc)
    return code in {400, 401, 403, 404}


def _erro_transitorio(exc: Exception) -> bool:
    code = _codigo_http(exc)
    if code in {408, 425, 429, 500, 502, 503, 504}:
        return True
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError, ConnectionError, RespostaProvedorVazia))


def _gerar_texto_com_metadados(
    tarefa: str, prompt: str, tentativas_por_provedor: int = 2
) -> dict:
    modelos = _ordenar_modelos_por_fallback(_modelos_aprovados(tarefa))
    if not modelos:
        raise ModeloNaoAprovado(f"Nenhum modelo aprovado para a tarefa '{tarefa}'")

    erros: list[str] = []
    inicio_total = time.monotonic()
    for indice, item in enumerate(modelos):
        provedor = str(item.get("provedor", "")).lower()
        chave = _chave_provedor(provedor)
        if not chave:
            erros.append(f"{provedor}: chave ausente")
            continue

        modelo = _modelo_resolvido(item)
        if not modelo:
            raise ModeloNaoAprovado(f"Modelo aprovado sem identificador para {provedor}")

        for tentativa in range(max(1, tentativas_por_provedor)):
            try:
                CONTADORES["requisicoes"] += 1
                texto = _chamar_provedor(item, prompt)
                if not texto or not texto.strip():
                    raise RespostaProvedorVazia("Resposta vazia")
                texto = texto.strip()
                _contabilizar(prompt, texto)
                return {
                    "texto": texto,
                    "provedor": provedor,
                    "modelo": modelo,
                    "tempo_ms": int((time.monotonic() - inicio_total) * 1000),
                }
            except ModeloNaoAprovado:
                raise
            except Exception as exc:
                if _erro_configuracao(exc):
                    code = _codigo_http(exc)
                    erros.append(
                        f"{provedor}: erro de autenticação/configuração"
                        + (f" HTTP {code}" if code else "")
                    )
                    # Credencial ou modelo inválido neste provedor não deve
                    # impedir a tentativa do próximo provedor aprovado.
                    break
                if not _erro_transitorio(exc):
                    raise RuntimeError(
                        f"Erro não classificado como transitório no provedor '{provedor}' "
                        f"({type(exc).__name__}); fallback interrompido."
                    ) from exc
                erros.append(
                    f"{provedor}: falha transitória"
                    + (f" HTTP {_codigo_http(exc)}" if _codigo_http(exc) else "")
                )

    raise RuntimeError(
        "Nenhum provedor aprovado conseguiu gerar a resposta: "
        + "; ".join(erros)
    )


def gerar_texto(
    tarefa: str, prompt: str | None = None, tentativas_por_provedor: int = 2
) -> str:
    if prompt is None:
        prompt = tarefa
        tarefa = "criacao"
    return _gerar_texto_com_metadados(tarefa, prompt, tentativas_por_provedor)["texto"]


def gerar_texto_com_metadados(
    tarefa: str, prompt: str | None = None, tentativas_por_provedor: int = 2
) -> dict:
    if prompt is None:
        prompt = tarefa
        tarefa = "criacao"
    return _gerar_texto_com_metadados(tarefa, prompt, tentativas_por_provedor)


def gerar_artigo(tema: str, categoria: str = "Culinária", tentativas_por_provedor: int = 2) -> dict:
    prompt = f"""Você é um redator culinário especializado em Chocolícia.
Escreva um conteúdo culinário em português do Brasil sobre: "{tema}"
Categoria: {categoria}
Responda com:
TITULO: ...
RESUMO: ...
TEMPO_LEITURA: X min
===CORPO===
..."""
    resposta = gerar_texto_com_metadados("criacao", prompt, tentativas_por_provedor)
    dados = _parsear_resposta(resposta["texto"])
    return {
        **dados,
        "slug": _gerar_slug(dados["titulo"]),
        "categoria": categoria,
        "conteudo_markdown": dados["corpo"].strip(),
        "data": date.today().isoformat(),
        "provedor": resposta["provedor"],
        "modelo": resposta["modelo"],
    }
