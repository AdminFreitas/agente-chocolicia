"""Carregador de prompts em camadas.

Base: docs/03-PROMPT-SISTEMA.md §2 (arquitetura dos prompts) e §10 (formato
de entrada). O prompt enviado ao modelo é montado em camadas:

    [1] prompts/base.md       -> persona + regras invioláveis + estilo
    [2] prompts/<tipo>.md     -> instruções específicas do tipo de conteúdo
    [3] ficha de pesquisa     -> dado, entre <dados_pesquisa>...</dados_pesquisa>
    [4] contrato de saída     -> esquema JSON do tipo (texto)

Regras de engenharia seguidas aqui (docs/03 §2):
- Prompts ficam fora do código, em arquivos de texto, com cabeçalho
  "versao: X.Y.Z" na primeira linha.
- A versão usada é devolvida junto com o prompt montado, para ir em
  generationMeta.prompt_version.
- O bloco <dados_pesquisa> nunca é tratado como instrução (docs/03 regra 9 /
  base.md regra 9).

Este módulo só lê arquivos de prompts e monta texto. Não chama LLM nem
conhece credenciais.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RE_VERSAO = re.compile(r"^versao:\s*(\d+\.\d+\.\d+)\s*$", re.MULTILINE)

PASTA_PROMPTS_PADRAO = Path(__file__).resolve().parent.parent / "prompts"


class PromptInvalidoError(ValueError):
    """Arquivo de prompt sem cabeçalho de versão ou ilegível."""


@dataclass(frozen=True)
class PromptCarregado:
    nome: str
    versao: str
    texto: str  # sem a linha "versao: ..." do cabeçalho


@dataclass(frozen=True)
class PromptMontado:
    """Saída pronta para enviar ao gerador de LLM."""

    sistema: str
    usuario: str
    versao_base: str
    versao_modulo: str

    def como_mensagens(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.sistema},
            {"role": "user", "content": self.usuario},
        ]


def _ler_prompt(caminho: Path) -> PromptCarregado:
    if not caminho.is_file():
        raise PromptInvalidoError(f"prompt não encontrado: {caminho}")
    bruto = caminho.read_text(encoding="utf-8")
    match = _RE_VERSAO.search(bruto)
    if not match:
        raise PromptInvalidoError(
            f"prompt sem cabeçalho 'versao: X.Y.Z' na primeira linha: {caminho}"
        )
    versao = match.group(1)
    # remove a linha de versão do corpo que vai para o modelo
    texto = _RE_VERSAO.sub("", bruto, count=1).strip("\n")
    return PromptCarregado(nome=caminho.stem, versao=versao, texto=texto)


class MontadorPrompt:
    """Monta o prompt em camadas para um tipo de conteúdo.

    Uso:
        montador = MontadorPrompt()
        saida = montador.montar(
            tipo="receita",
            pauta=pauta_dict,
            ficha=ficha_consolidada_dict,
            categorias_validas=["brigadeiros-e-docinhos", ...],
            contrato_saida=TEXTO_CONTRATO_RECEITA,
        )
    """

    def __init__(self, pasta_prompts: Path | None = None) -> None:
        self._pasta = pasta_prompts or PASTA_PROMPTS_PADRAO
        self._cache: dict[str, PromptCarregado] = {}

    def _carregar(self, nome: str) -> PromptCarregado:
        if nome not in self._cache:
            self._cache[nome] = _ler_prompt(self._pasta / f"{nome}.md")
        return self._cache[nome]

    def montar(
        self,
        *,
        tipo: str,
        pauta: dict[str, Any],
        ficha: dict[str, Any],
        categorias_validas: list[str],
        contrato_saida: str,
    ) -> PromptMontado:
        base = self._carregar("base")
        modulo = self._carregar(tipo)

        dados_json = json.dumps(ficha, ensure_ascii=False, indent=2)
        pauta_json = json.dumps(pauta, ensure_ascii=False)

        # Formato de docs/03 §10. O bloco <dados_pesquisa> é dado, não ordem
        # (reforçado também na regra 9 de base.md).
        usuario = (
            f"TIPO DE CONTEÚDO: {tipo}\n\n"
            f"PAUTA\n{pauta_json}\n\n"
            f"<dados_pesquisa>\n{dados_json}\n</dados_pesquisa>\n\n"
            "LISTA DE CATEGORIAS VÁLIDAS\n"
            f"{json.dumps(categorias_validas, ensure_ascii=False)}\n\n"
            f"CONTRATO DE SAÍDA\n{contrato_saida}\n\n"
            "Responda somente com o objeto JSON."
        )
        sistema = f"{base.texto}\n\n{modulo.texto}"
        return PromptMontado(
            sistema=sistema,
            usuario=usuario,
            versao_base=base.versao,
            versao_modulo=modulo.versao,
        )

    def montar_reparo(self, *, motivos: list[str], resposta_anterior: str) -> PromptCarregado:
        """Usa prompts/reparo.md (docs/03 §12.2), preenchendo os placeholders."""
        reparo = self._carregar("reparo")
        lista_erros = "\n".join(f"- {m}" for m in motivos) or "- (sem detalhe informado)"
        texto = reparo.texto.replace(
            "{lista de erros do validador}", lista_erros
        ).replace("{JSON anterior}", resposta_anterior)
        return PromptCarregado(nome="reparo", versao=reparo.versao, texto=texto)

    def carregar_revisor(self) -> PromptCarregado:
        return self._carregar("revisor")

    def carregar_seo(self) -> PromptCarregado:
        return self._carregar("seo")
