"""Pipeline de receitas com dependências explícitas e sem efeitos implícitos."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agents import editor, revisor, seo
from agents.editor import Falha, ResultadoCriacao
from integration.adaptador_receita import montar_payload_receita, montar_payload_receita_legada
from integration.cliente_site import ClienteSite, ContratoInvalido, ErroSite
from services.imagem_service import escolher_capa
from validators import ResultadoValidacao, validar_conteudo


@dataclass
class DependenciasReceita:
    pesquisar: Callable[[dict], Any]
    gerar: Any
    cliente: ClienteSite
    catalogo: Any
    selector: Any
    usadas: Any
    visao: Any
    baixar: Callable[..., Any] | None = None
    validador: Any | None = None
    tags_existentes: list[str] = field(default_factory=list)


@dataclass
class ResultadoReceita:
    estado: str
    etapa: str
    codigo: str | None = None
    ficha: dict | None = None
    criacao: ResultadoCriacao | None = None
    revisao: Any | None = None
    seo: Any | None = None
    imagem: Any | None = None
    payload: dict | None = None
    envio: Any | None = None
    motivos: list[str] = field(default_factory=list)


class ValidadorPontoUnico:
    ids_cobertos = frozenset()

    def validar(self, conteudo: dict, contexto: dict) -> list[Falha]:
        resultado: ResultadoValidacao = validar_conteudo(conteudo, contexto)
        return [Falha(f.id, f.detalhe, gravidade=f.gravidade, campo=f.campo) for f in resultado.falhas + resultado.avisos]


def validar_por_ponto_unico(conteudo: dict, contexto: dict | None = None) -> ResultadoValidacao:
    return validar_conteudo(conteudo, contexto)


def gerar_receita(deps: DependenciasReceita, pauta: dict, *, fase: int, run_id: str, dry_run: bool = True, publicar: bool = False, idempotency_key: str | None = None, validators_version: str = "pendente") -> ResultadoReceita:
    """Executa pesquisa, criação, validação, revisão, SEO, imagem, contrato e envio."""
    if not pauta.get("topic_slug") or (
        not pauta.get("subcategoria")
        and getattr(deps.cliente, "contract", "v1") != "legacy"
    ):
        return ResultadoReceita("rejected", "pauta", "PAUTA-01", motivos=["pauta sem topic_slug ou subcategoria"])
    try:
        pesquisa = deps.pesquisar(pauta)
    except Exception as exc:
        return ResultadoReceita("error", "pesquisa", "PESQUISA-ERRO", motivos=[type(exc).__name__])
    ficha = getattr(pesquisa, "ficha_consolidada", None) or getattr(pesquisa, "ficha", None)
    if ficha is None and isinstance(pesquisa, dict):
        ficha = pesquisa.get("ficha_consolidada")
    status_pesquisa = getattr(pesquisa, "status", None) or (pesquisa.get("status") if isinstance(pesquisa, dict) else None)
    if not ficha or status_pesquisa != "aprovada_para_criacao":
        return ResultadoReceita("rejected", "pesquisa", "PESQUISA-GATE", ficha=ficha, motivos=["ficha não aprovada para criação"])
    validador = deps.validador or ValidadorPontoUnico()
    try:
        criacao = editor.criar_receita(ficha, pauta, gerar=deps.gerar, validador=validador)
    except Exception as exc:
        return ResultadoReceita("error", "criacao", "CRIACAO-ERRO", ficha=ficha, motivos=[type(exc).__name__])
    if criacao.status == "rejeitado":
        return ResultadoReceita("rejected", "criacao", criacao.rejection_code, ficha=ficha, criacao=criacao)
    try:
        revisao = revisor.revisar_conteudo(criacao.conteudo, ficha, criacao.modelo.get("familia", ""), gerar=deps.gerar)
    except Exception as exc:
        return ResultadoReceita("error", "revisao", "REV-ERRO", ficha=ficha, criacao=criacao, motivos=[type(exc).__name__])
    if not revisor.decisao_final(True, revisao):
        return ResultadoReceita("rejected", "revisao", "REV", ficha=ficha, criacao=criacao, revisao=revisao)
    try:
        seo_result = seo.ajustar_seo(receita=criacao.conteudo, tags_existentes=deps.tags_existentes, gerador=deps.gerar)
    except Exception as exc:
        return ResultadoReceita("error", "seo", "SEO-ERRO", ficha=ficha, criacao=criacao, revisao=revisao, motivos=[type(exc).__name__])
    if not seo_result.aplicado:
        return ResultadoReceita("rejected", "seo", "IMG-08", ficha=ficha, criacao=criacao, revisao=revisao, seo=seo_result)
    conteudo = seo_result.conteudo
    extras = {"baixar": deps.baixar} if deps.baixar else {}
    imagem = escolher_capa(conteudo, usadas=deps.usadas, visao=deps.visao, selector=deps.selector, **extras)
    if imagem.cover is None:
        return ResultadoReceita("rejected", "imagem", "IMG-07", ficha=ficha, criacao=criacao, revisao=revisao, seo=seo_result, imagem=imagem)
    status = "published" if publicar and not dry_run and fase >= 1 else "draft"
    try:
        if getattr(deps.cliente, "contract", "v1") == "legacy":
            payload = montar_payload_receita_legada(
                conteudo, pauta=pauta, ficha=ficha, cover=imagem.cover, status=status
            )
        else:
            payload = montar_payload_receita(conteudo, pauta=pauta, ficha=ficha, cover=imagem.cover, run_id=run_id, fase=fase, modelo=criacao.modelo, prompt_version=criacao.prompt_version, catalogo=deps.catalogo, status=status, validators_version=validators_version)
    except ContratoInvalido as exc:
        return ResultadoReceita("rejected", "contrato", "API-01", ficha=ficha, criacao=criacao, revisao=revisao, seo=seo_result, imagem=imagem, motivos=[str(exc)])
    try:
        envio = deps.cliente.criar_receita(
            payload, run_id=run_id, idempotency_key=idempotency_key
        )
    except (ErroSite, ContratoInvalido) as exc:
        return ResultadoReceita("error", "envio", getattr(exc, "codigo", "API-01"), ficha=ficha, criacao=criacao, revisao=revisao, seo=seo_result, imagem=imagem, payload=payload.model_dump(mode="json"), motivos=[str(exc)])
    estado = (
        "generated" if envio.situacao == "dry_run"
        else "rejected" if envio.situacao == "duplicada"
        else "published" if envio.status == "published"
        else "sent"
    )
    if estado in {"sent", "published"} and imagem.meta and hasattr(deps.usadas, "registrar"):
        deps.usadas.registrar(
            imagem.cover["sourceImageUrl"],
            imagem.meta["sha256"],
            imagem.cover["provider"],
            imagem.meta["provider_image_id"],
        )
    return ResultadoReceita(estado, "envio", "DUPLICADA" if estado == "rejected" else None, ficha, criacao, revisao, seo_result, imagem, payload.model_dump(mode="json"), envio)
