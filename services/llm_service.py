import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Callable

import httpx

from config.settings import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
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
    modelos = config.get(tarefa, [])
    if not isinstance(modelos, list):
        raise ModeloNaoAprovado(f"Configuração inválida para a tarefa '{tarefa}'")
    return modelos


def _modelos_elegiveis(tarefa: str, familia_excluida: str | None = None) -> list[dict]:
    modelos = _modelos_aprovados(tarefa)
    if not modelos:
        raise ModeloNaoAprovado(f"Nenhum modelo aprovado para a tarefa '{tarefa}'")
    elegiveis = []
    for item in modelos:
        if not isinstance(item, dict):
            raise ModeloNaoAprovado(f"Entrada inválida de modelo na tarefa '{tarefa}'")
        provedor = item.get("provedor")
        if not isinstance(provedor, str) or not provedor.strip():
            raise ModeloNaoAprovado(f"Modelo sem provedor na tarefa '{tarefa}'")
        familia = item.get("familia")
        modelo = item.get("modelo")
        if not isinstance(modelo, str) or not modelo.strip():
            raise ModeloNaoAprovado(f"Modelo sem identificador aprovado na tarefa '{tarefa}'")
        if not isinstance(familia, str) or not familia.strip():
            raise ModeloNaoAprovado(f"Modelo sem família aprovada na tarefa '{tarefa}'")
        if familia_excluida is not None and familia == familia_excluida:
            continue
        elegiveis.append(item)
    if not elegiveis:
        raise ModeloNaoAprovado(
            f"Nenhum modelo aprovado de família diferente para a tarefa '{tarefa}'"
        )
    return elegiveis


def validar_configuracao_modelos(tarefas: list[str]) -> None:
    """Falha antes de qualquer rede se faltar modelo, família independente ou credencial."""
    modelos_por_tarefa = {}
    for tarefa in tarefas:
        modelos = _modelos_elegiveis(tarefa)
        configurados = [
            item for item in modelos
            if _chave_provedor(str(item["provedor"])) and str(_chave_provedor(str(item["provedor"]))).strip()
        ]
        if not configurados:
            raise ModeloNaoAprovado(
                f"Nenhum modelo aprovado com credencial configurada para a tarefa '{tarefa}'"
            )
        modelos_por_tarefa[tarefa] = configurados
    familias_criacao = {item["familia"] for item in modelos_por_tarefa["criacao"]}
    if not any(
        modelo["familia"] != familia
        for familia in familias_criacao
        for modelo in modelos_por_tarefa["revisao"]
    ):
        raise ModeloNaoAprovado("não há modelo de revisão aprovado em família independente")


def _chave_provedor(provedor: str) -> str | None:
    return {
        "gemini": GEMINI_API_KEY,
        "groq": GROQ_API_KEY,
        "openrouter": OPENROUTER_API_KEY,
    }.get(provedor)


def _modelo_resolvido(item: dict) -> str:
    return item.get("modelo", "").strip()


def _chamar_gemini(prompt: str, modelo: str) -> str:
    from google import genai

    resposta = genai.Client(api_key=GEMINI_API_KEY).models.generate_content(
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
    if provedor == "gemini":
        return _chamar_gemini(prompt, modelo)
    if provedor in {"groq", "openrouter"}:
        return _chamar_openai_compativel(prompt, modelo, provedor)
    raise ModeloNaoAprovado(f"Provedor nao suportado: {provedor}")


def _contabilizar(prompt: str, texto: str) -> None:
    CONTADORES["tokens"] += len((prompt + texto).split())


def _gerar_com_metadados(
    tarefa: str,
    prompt: str,
    tentativas_por_provedor: int = 2,
    familia_excluida: str | None = None,
) -> dict[str, Any]:
    modelos = _modelos_elegiveis(tarefa, familia_excluida)
    erros = []
    tentativas = 0
    for item in modelos:
        provedor = item.get("provedor", "")
        if not _chave_provedor(provedor):
            erros.append(f"{provedor}: chave nao configurada")
            continue
        for _ in range(max(1, tentativas_por_provedor)):
            tentativas += 1
            inicio = time.monotonic()
            try:
                CONTADORES["requisicoes"] += 1
                texto = _chamar_provedor(item, prompt)
                _contabilizar(prompt, texto)
                if texto and texto.strip():
                    return {
                        "texto": texto.strip(),
                        "provedor": provedor,
                        "modelo": _modelo_resolvido(item),
                        "familia": item.get("familia", ""),
                        "tentativas": tentativas,
                        "tempo_ms": int((time.monotonic() - inicio) * 1000),
                    }
                raise RuntimeError("Resposta vazia")
            except Exception as exc:
                erros.append(f"{provedor}: {exc}")
            finally:
                time.monotonic() - inicio
    raise RuntimeError(f"Falha nos modelos aprovados: {'; '.join(erros)}")


def gerar_texto(
    tarefa: str,
    prompt: str | None = None,
    tentativas_por_provedor: int = 2,
    *,
    familia_excluida: str | None = None,
) -> str:
    if prompt is None:
        prompt = tarefa
        tarefa = "criacao"
    return _gerar_com_metadados(tarefa, prompt, tentativas_por_provedor, familia_excluida)["texto"]


def gerar_texto_com_metadados(
    tarefa: str,
    prompt: str | None = None,
    tentativas_por_provedor: int = 2,
    *,
    familia_excluida: str | None = None,
) -> dict:
    if prompt is None:
        prompt = tarefa
        tarefa = "criacao"
    return _gerar_com_metadados(tarefa, prompt, tentativas_por_provedor, familia_excluida)


def gerar_artigo(tema: str, categoria: str = "Tecnologia", tentativas_por_provedor: int = 2) -> dict:
    prompt = f"""Voce e um escritor especializado em Chocolicia.
Escreva um artigo em portugues sobre: "{tema}"
Categoria: {categoria}
Responda com:
TITULO: ...
RESUMO: ...
TEMPO_LEITURA: X min
===CORPO===
..."""
    texto = gerar_texto("criacao", prompt, tentativas_por_provedor)
    dados = _parsear_resposta(texto)
    return {
        **dados,
        "slug": _gerar_slug(dados["titulo"]),
        "categoria": categoria,
        "conteudo_markdown": dados["corpo"].strip(),
        "data": date.today().isoformat(),
        "provedor": _modelos_aprovados("criacao")[0]["provedor"],
    }
