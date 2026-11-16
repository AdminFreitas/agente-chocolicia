"""Etapa 6 (parte SEO) — ajusta título, descrição, palavras-chave, texto
alternativo, tags e temas relacionados de um conteúdo JÁ VALIDADO.

Base: docs/05-SEO.md §13 ("Insumo do módulo de SEO"). A regra central do
prompt é repetida aqui em código, como trava adicional: este módulo nunca
toca em ingredientes, quantidades, tempos, passos ou avisos — ele só lê
esses campos da receita recebida e nunca os reescreve no resultado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agents.editor import ReceitaSaida
from services.llm_cliente import GerarFn, extrair_json
from services.prompt_loader import MontadorPrompt

# Campos que o módulo de SEO tem permissão de propor (docs/05 §13, tarefas 1-6)
_CAMPOS_PERMITIDOS = {
    "titulo",
    "descricao_curta",
    "palavra_chave_principal",
    "palavras_secundarias",
    "texto_alt_imagem",
    "tags",
    "temas_relacionados",
}


class SeoSaida(BaseModel):
    titulo: str = Field(min_length=35, max_length=65)
    descricao_curta: str = Field(min_length=120, max_length=160)
    palavra_chave_principal: str = Field(min_length=1, max_length=80)
    palavras_secundarias: list[str] = Field(default_factory=list, max_length=4)
    texto_alt_imagem: str = Field(min_length=20, max_length=140)
    tags: list[str] = Field(min_length=4, max_length=10)
    temas_relacionados: list[str] = Field(min_length=2, max_length=6)


@dataclass
class ResultadoSeo:
    aprovado: bool
    saida: SeoSaida | None
    modelo_ia: str | None
    prompt_version: str | None
    erro: str | None = None


# Compatibilidade de nomenclatura com o pipeline educativo.
ResultadoSEO = ResultadoSeo


def _ficha_para_seo(receita: ReceitaSaida, tags_existentes: list[str]) -> dict[str, Any]:
    """Monta o "dado" que vai para o prompt de SEO — nada que o SEO possa
    reescrever indevidamente (sem passos, sem quantidades, sem avisos)."""
    return {
        "titulo_atual": receita.titulo,
        "descricao_atual": receita.descricao_curta,
        "introducao": receita.introducao,
        "subcategoria": receita.subcategoria,
        "tags_propostas": receita.tags,
        "tags_existentes": tags_existentes,
        "temas_relacionados_propostos": receita.temas_relacionados,
        "texto_alt_imagem_atual": receita.texto_alt_imagem,
    }


def ajustar_seo(
    *,
    receita: ReceitaSaida,
    tags_existentes: list[str],
    gerador: GerarFn,
    montador: MontadorPrompt | None = None,
) -> ResultadoSeo:
    montador = montador or MontadorPrompt()
    prompt_seo = montador.carregar_seo()
    dados = _ficha_para_seo(receita, tags_existentes)
    prompt = (
        f"{prompt_seo.texto}\n\n"
        "<dados_receita_validada>\n"
        f"{json.dumps(dados, ensure_ascii=False)}\n"
        "</dados_receita_validada>\n\n"
        "Responda somente com o objeto JSON das 6 tarefas."
    )
    resposta = gerador("seo", prompt)
    try:
        dados_saida, erro_json = extrair_json(resposta.texto)
        if erro_json or not isinstance(dados_saida, dict):
            raise ValueError(erro_json or "a resposta deve ser um objeto JSON")
        # trava: ignora qualquer campo fora do permitido, mesmo que o modelo
        # devolva algo a mais (ex.: tentando reescrever ingredientes).
        dados_saida = {k: v for k, v in dados_saida.items() if k in _CAMPOS_PERMITIDOS}
        saida = SeoSaida.model_validate(dados_saida)
    except (ValueError, ValidationError) as exc:
        return ResultadoSeo(
            aprovado=False,
            saida=None,
            modelo_ia=resposta.modelo,
            prompt_version=prompt_seo.versao,
            erro=f"SEO-00: saída inválida ({exc})",
        )
    return ResultadoSeo(
        aprovado=True,
        saida=saida,
        modelo_ia=resposta.modelo,
        prompt_version=prompt_seo.versao,
    )
