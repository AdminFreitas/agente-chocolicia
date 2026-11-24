"""
imagem_service.py — Capa da receita (Etapa 6 do fluxo: "SEO e visual"), docs/01 §8.2.

Entrada: o conteúdo validado (termos_busca_imagem, prompt_imagem, titulo,
subcategoria). Saída: ResultadoImagem com o objeto `cover` do payload do site
(docs/06 §7.1 modo "stock"; §7.2 modo "generate" em último caso).

O que mudou em relação à versão do DigitalTech:
- sem armazenamento local, sem SQLite e sem download para disco: a proveniência
  segue no payload e quem baixa e trata a imagem é o site;
- removidas buscar_imagem_capa e buscar_imagem_noticia (raspagem de og:image
  de notícias fica fora do escopo; não há notícias, docs/01 D-16);
- os termos vêm da receita (termos_busca_imagem), não do título; sem termo de
  reserva genérico, porque ele traria imagem do prato errado;
- filtro de licença, largura mínima, deduplicação e verificação por visão
  (services/image_providers/selector.py).

Pendências por interface: VerificadorVisao e ImagensUsadas persistente.
"""

from __future__ import annotations

from typing import Optional

from agente_receitas.services.image_providers import (
    ImageSelector,
    ImagensUsadas,
    ImagensUsadasMemoria,
    ResultadoImagem,
    SemVisao,
    VerificadorVisao,
)


def escolher_capa(
    conteudo: dict,
    *,
    usadas: Optional[ImagensUsadas] = None,
    visao: Optional[VerificadorVisao] = None,
    selector: Optional[ImageSelector] = None,
    geracao_permitida: bool = True,
    **kwargs,
) -> ResultadoImagem:
    """
    `geracao_permitida` vem do teto diário de imagens por IA (docs/06 §12), a ser
    aplicado pelo pipeline (Passo 9). Sem `visao`, a verificação IMG-04 fica
    PENDENTE e a escolha cai em "generate" (falha fechada).
    """
    termos = conteudo.get("termos_busca_imagem") or []
    prompt = conteudo.get("prompt_imagem") or ""
    if not termos or not prompt:
        raise ValueError("conteúdo sem termos_busca_imagem ou prompt_imagem")
    if conteudo.get("subcategoria"):
        esperado = f'{conteudo.get("titulo", "")} (subcategoria: {conteudo["subcategoria"]})'
    else:  # dica sem subcategoria (docs/04 §6.7)
        esperado = f'{conteudo.get("titulo", "")} (assunto: {conteudo.get("assunto", "")})'
    return (selector or ImageSelector()).selecionar(
        termos=termos,
        esperado=esperado,
        prompt_imagem=prompt,
        usadas=usadas if usadas is not None else ImagensUsadasMemoria(),
        visao=visao if visao is not None else SemVisao(),
        geracao_permitida=geracao_permitida,
        **kwargs,
    )
