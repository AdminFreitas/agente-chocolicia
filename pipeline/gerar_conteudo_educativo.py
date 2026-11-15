"""
pipeline/gerar_conteudo_educativo.py — Dicas (docs/01 §7.2, docs/07 §3 a §5, docs/04 §6.7).

Orquestra, para UMA dica por chamada: pauta (com assunto) -> pesquisa -> criação (Chef IA)
-> revisão por IA (família diferente) -> SEO -> capa -> payload v1 -> POST /api/articles.
Técnica e matéria: PENDENTE (prompts de docs/03 §8 e §9 ainda não escritos).

Tudo o que é externo entra por injeção (DependenciasDica); nada aqui lê .env, usa rede
ou LLM por conta própria. Regras de fail-closed desta etapa:
- Só vai como "published" se: fase >= 1, `publicar=True`, o validador aprovou
  (criação "aprovado"), o revisor aprovou, e NÃO há pendência alguma. Caso contrário
  o envio é "draft" (docs/01 D-06).
- Assuntos `equipamentos-compra` e `negocios` exigem HON-08 e HON-07 (08 §4.7; 07 §7).
  Sem um validador que declare cobrir esses IDs (atributo `ids_cobertos`), a dica é
  marcada "PENDENTE: validators HON-0x" e fica em rascunho.

PENDENTES (ver "Lacunas"): a pesquisa de dicas (a doc 02 não define a extração nem a ficha),
validators/, tetos de custo e limite diário (Passo 9), fumaça pós-publicação (PUB-01 a 07),
persistência do histórico (Passo 3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from agents import editor, planejador, revisor, seo
from agents.editor import ResultadoCriacao, Validador
from agents.revisor import ResultadoRevisao
from agents.seo import ResultadoSEO
from integration.adaptador_artigo import montar_payload_dica
from integration.cliente_site import ClienteSite, ContratoInvalido, ErroSite, RespostaCriacao
from services.imagem_service import escolher_capa
from services.image_providers import ImageSelector, ImagensUsadas, ImagensUsadasMemoria, ResultadoImagem, VerificadorVisao
from services.llm_cliente import FamiliaNaoGarantida, GerarFn

log = logging.getLogger(__name__)

CONFIG_CADENCIA = Path(__file__).resolve().parent.parent / "config" / "cadencia.json"

# docs/08 §4.7 (HON-07 e HON-08) e docs/07 §7.
EXIGENCIAS_POR_ASSUNTO = {"equipamentos-compra": "HON-08", "negocios": "HON-07"}
MIN_FONTES_DICA = 2  # docs/02 §5.3


def carregar_cadencia(caminho: Path | str = CONFIG_CADENCIA) -> dict:
    with Path(caminho).open("r", encoding="utf-8") as f:
        return json.load(f)


def verificar_minimos_dica(ficha: dict) -> list[str]:
    """
    docs/02 §5.3: dica exige 2 fontes e, quando envolver segurança ou conservação, 1 fonte
    técnica ou oficial. A doc não define os campos da ficha de dica; usei `fontes_consultadas`,
    `envolve_seguranca` e `fontes_tecnicas` (suposição, ver "Lacunas").
    """
    motivos = []
    if int(ficha.get("fontes_consultadas", 0) or 0) < MIN_FONTES_DICA:
        motivos.append(f"GATE-DICA-01: mínimo de {MIN_FONTES_DICA} fontes (02 §5.3)")
    if ficha.get("envolve_seguranca") and int(ficha.get("fontes_tecnicas", 0) or 0) < 1:
        motivos.append("GATE-DICA-02: segurança ou conservação exige 1 fonte técnica ou oficial (02 §5.3)")
    return motivos


@dataclass
class DependenciasDica:
    fila: Any  # planejador.FilaPautas
    taxonomia: Any  # planejador.Taxonomia
    assuntos: Any  # planejador.AssuntosDica
    cobertura: Any  # planejador.Cobertura
    historico: Any  # planejador.Historico
    cliente: ClienteSite
    # PENDENTE: pesquisa de dicas. Recebe a pauta (dict) e devolve a ficha (dict) no formato de
    # docs/02 §7.2 com status "aprovada_para_criacao".
    pesquisar: Optional[Callable[[dict], dict]] = None
    gerar: Optional[GerarFn] = None
    validador: Optional[Validador] = None
    visao: Optional[VerificadorVisao] = None
    selector: Optional[ImageSelector] = None
    usadas: Optional[ImagensUsadas] = None
    conteudo_existente: Any = None
    bloqueios: Any = None
    calendario: Optional[dict] = None
    tags_existentes: list[str] = field(default_factory=list)
    baixar: Optional[Callable[..., Any]] = None  # só para testes (download de imagem)


@dataclass
class ResultadoDica:
    # "sem_pauta" | "adiada_cadencia" | "rejected" | "error" | "generated" | "sent"
    # (rejected/error/generated/sent seguem agent_generations, docs/07 §4.3). "published"
    # só depois do teste de fumaça (Passo 9).
    estado: str
    etapa: str = ""
    codigo: Optional[str] = None
    pauta: Optional[dict] = None
    ficha: Optional[dict] = None
    criacao: Optional[ResultadoCriacao] = None
    revisao: Optional[ResultadoRevisao] = None
    seo: Optional[ResultadoSEO] = None
    imagem: Optional[ResultadoImagem] = None
    payload: Optional[dict] = None
    envio: Optional[RespostaCriacao] = None
    status_enviado: Optional[str] = None
    pendencias: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)


def _bloqueantes(falhas) -> list:
    return [f for f in falhas if f.gravidade == "bloqueante"]


def gerar_dica(
    deps: DependenciasDica,
    *,
    fase: int,
    run_id: str,
    publicar: bool = False,
    hoje: Optional[date] = None,
    geracao_imagem_permitida: bool = True,
    publicadas_na_semana: Optional[int] = None,
    revisor_obrigatorio: bool = True,
    validators_version: str = "pendente",
) -> ResultadoDica:
    pend: list[str] = []
    cad = carregar_cadencia()["artigos"]

    # ---- cadência (docs/07 §3): artigos só a partir da Fase 1
    if fase >= cad["a_partir_da_fase"]:
        if publicadas_na_semana is None:
            pend.append("PENDENTE: cadência semanal não verificada (informe publicadas_na_semana)")
        elif publicadas_na_semana >= cad["dica_por_semana"]:
            return ResultadoDica("adiada_cadencia", "cadencia", "CADENCIA",
                                 motivos=[f"já há {publicadas_na_semana} dica(s) na semana (limite {cad['dica_por_semana']})"])

    # ---- 1. pauta
    plan = planejador.escolher_pauta(
        deps.fila, deps.taxonomia, deps.cobertura, deps.historico, fase=fase, hoje=hoje,
        conteudo_existente=deps.conteudo_existente, bloqueios=deps.bloqueios, calendario=deps.calendario,
        tipo_conteudo="dica", assuntos=deps.assuntos,
    )
    if plan.pauta is None:
        return ResultadoDica("sem_pauta", "pauta", None, motivos=[f'{d["codigo"]}: {d["tema"]}' for d in plan.descartadas], pendencias=pend)
    pauta = plan.pauta.to_dict()
    pend += plan.pauta.avisos
    r = ResultadoDica("error", pauta=pauta, pendencias=pend)

    def falhar(estado: str, etapa: str, codigo: str, *motivos: str) -> ResultadoDica:
        r.estado, r.etapa, r.codigo = estado, etapa, codigo
        r.motivos += [m for m in motivos if m]
        return r

    # ---- 2. pesquisa (PENDENTE: interface)
    if deps.pesquisar is None:
        return falhar("error", "pesquisa", "PESQUISA-PENDENTE", "PENDENTE: pesquisa de dicas não implementada (docs/02 não define a ficha de dica)")
    try:
        ficha = deps.pesquisar(pauta)
    except Exception as exc:
        return falhar("error", "pesquisa", "PESQUISA-ERRO", type(exc).__name__)
    r.ficha = ficha
    if ficha.get("status") != "aprovada_para_criacao":
        return falhar("rejected", "pesquisa", "PESQUISA-GATE", *[str(m) for m in ficha.get("motivos", [])])
    minimos = verificar_minimos_dica(ficha)
    if minimos:
        return falhar("rejected", "pesquisa", minimos[0].split(":")[0], *minimos)

    # ---- 3. criação (erros do provedor abortam a execução, docs/07 §5)
    try:
        cri = editor.criar_dica(ficha, pauta, gerar=deps.gerar, validador=deps.validador)
    except Exception as exc:
        return falhar("error", "criacao", "CRIACAO-ERRO", type(exc).__name__)
    r.criacao = cri
    if cri.status == "rejeitado":
        return falhar("rejected", "criacao", cri.rejection_code or "SCH-02", *[f"{f.id}: {f.detalhe}" for f in _bloqueantes(cri.falhas)])
    forcar_rascunho = False
    if cri.status == "pendente_validacao":
        pend.append("PENDENTE: validators (sem validador, a dica não é aprovada)")
    exigido = EXIGENCIAS_POR_ASSUNTO.get(pauta["assunto"])
    cobertos = set(getattr(deps.validador, "ids_cobertos", ()) or ()) if deps.validador else set()
    if exigido and exigido not in cobertos:
        pend.append(f"PENDENTE: validators {exigido} (assunto {pauta['assunto']})")
        forcar_rascunho = True

    # ---- 4. revisão por IA, família diferente (docs/03 §12.3)
    if revisor_obrigatorio:
        try:
            rev = revisor.revisar_conteudo(cri.conteudo, ficha, cri.modelo.get("familia", ""), gerar=deps.gerar)
        except FamiliaNaoGarantida as exc:
            return falhar("error", "revisao", "REV-FAMILIA", str(exc))
        except Exception as exc:
            return falhar("error", "revisao", "REV-ERRO", type(exc).__name__)
        r.revisao = rev
        if not revisor.decisao_final(True, rev):
            return falhar("rejected", "revisao", "REV", rev.erro or "", *[f'{p["gravidade"]}: {p["descricao"]}' for p in rev.problemas])
    else:
        pend.append("PENDENTE: revisão por IA ignorada (revisor_obrigatorio=False)")

    # ---- 5. SEO (também é quem escreve o texto alternativo da capa)
    try:
        s = seo.ajustar_seo(cri.conteudo, tags_existentes=deps.tags_existentes, gerar=deps.gerar)
    except Exception as exc:
        return falhar("error", "seo", "SEO-ERRO", type(exc).__name__)
    r.seo = s
    if not s.aplicado:
        return falhar("rejected", "seo", "IMG-08", f"SEO não aplicado ({s.motivo}); sem texto alternativo para a capa")
    conteudo = s.conteudo
    if deps.validador is not None:  # o SEO muda título e descrição: revalidar (docs/05 §13)
        falhas = list(deps.validador.validar(conteudo, {"pauta": pauta, "ficha": ficha}))
        if _bloqueantes(falhas):
            return falhar("rejected", "seo", _bloqueantes(falhas)[0].id, *[f"{f.id}: {f.detalhe}" for f in _bloqueantes(falhas)])
    else:
        pend.append("PENDENTE: validators depois do SEO (HON, SIM, SEO-01 a SEO-08)")

    # ---- 6. capa (IMG-01 a IMG-07)
    usadas = deps.usadas if deps.usadas is not None else ImagensUsadasMemoria()
    extras = {"baixar": deps.baixar} if deps.baixar is not None else {}
    img = escolher_capa(conteudo, usadas=usadas, visao=deps.visao, selector=deps.selector,
                        geracao_permitida=geracao_imagem_permitida, **extras)
    r.imagem = img
    pend += img.pendencias
    if img.cover is None:
        return falhar("rejected", "imagem", "IMG-07", *img.pendencias)

    # ---- 7. payload e status
    publicavel = (
        fase >= 1 and publicar and cri.status == "aprovado" and r.revisao is not None
        and not forcar_rascunho and not pend
    )
    status = "published" if publicavel else "draft"
    try:
        payload = montar_payload_dica(
            conteudo, pauta=pauta, ficha=ficha, cover=img.cover, run_id=run_id, fase=fase, modelo=cri.modelo,
            prompt_version=cri.prompt_version, status=status, validators_version=validators_version,
        )
    except ContratoInvalido as exc:
        return falhar("rejected", "adaptador", "API-01", *[f'{e["campo"]}: {e["detalhe"]}' for e in exc.erros])
    r.payload, r.status_enviado = payload.model_dump(mode="json", exclude_none=True), status

    # ---- 8. envio
    try:
        envio = deps.cliente.criar_artigo(payload, run_id=run_id)
    except ErroSite as exc:
        return falhar("error", "envio", exc.codigo or type(exc).__name__, str(exc))
    except ContratoInvalido as exc:
        return falhar("rejected", "envio", "API-01", str(exc))
    r.envio = envio
    if envio.situacao == "duplicada":
        return falhar("rejected", "envio", "DUPLICADA", "a pauta já existe no site, de outra execução")
    if envio.situacao == "dry_run":
        r.estado, r.etapa = "generated", "dry_run"
        return r

    # só agora a imagem conta como usada (docs/08 IMG-05; selector.py)
    if img.status == "stock":
        m = img.meta
        usadas.registrar(img.cover["sourceImageUrl"], m["sha256"], img.cover["provider"], m["provider_image_id"])
    r.estado, r.etapa = "sent", "envio"
    return r
