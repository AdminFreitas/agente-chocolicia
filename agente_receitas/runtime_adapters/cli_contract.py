"""Composição das dependências reais dos pipelines de receitas e dicas."""
from .compose import build_runtime
from .config import ConfigurationError


class _HistoricoStore:
    def __init__(self, store, run_id: str):
        self.store = store
        self.run_id = run_id

    def ja_existe(self, content_type: str, topic_slug: str) -> bool:
        return self.store.ja_existe(content_type, topic_slug)

    def reservar_pauta(self, content_type: str, topic_slug: str, tema: str, subcategoria: str | None) -> bool:
        return self.store.reservar_pauta(
            content_type, topic_slug, tema, subcategoria, self.run_id
        )


def build_services(
    *, dry_run: bool = True, target: str = "preview",
    tipo: str = "receita", assunto: str = "automatico",
    subcategoria: str | None = None, run_id: str = "",
):
    runtime = build_runtime(
        dry_run=dry_run, target=target
    )
    from agente_receitas.agents.analista import Analista
    from agente_receitas.agents.pesquisador import carregar_fontes, pesquisar_receita
    from agente_receitas.pipeline.gerar_receitas import DependenciasReceita, ValidadorPontoUnico
    from agente_receitas.services.busca_service import LeitorHTTP
    from agente_receitas.services.image_providers import ImageSelector, ImagensUsadasMemoria, SemVisao
    from agente_receitas.services.image_generation import gerar_imagem
    cfg_fontes = carregar_fontes()
    leitor = LeitorHTTP(fontes=cfg_fontes["fontes"], timeout=runtime.settings.request_timeout)

    def pesquisar(pauta: dict):
        return pesquisar_receita(
            pauta,
            buscadores=runtime.search_providers,
            leitor=leitor,
            analista=Analista(catalogo=runtime.catalog, fase=runtime.settings.site_phase),
            extrator=lambda prompt: runtime.generate("extraction", prompt).texto,
            cfg=cfg_fontes,
        )

    dependencias_receita = DependenciasReceita(
        pesquisar=pesquisar,
        gerar=runtime.generate,
        cliente=runtime.site_client,
        catalogo=runtime.catalog,
        selector=ImageSelector(),
        usadas=runtime.store or ImagensUsadasMemoria(),
        visao=getattr(runtime, "vision", None) or SemVisao(),
        validador=ValidadorPontoUnico(),
        gerar_imagem=gerar_imagem if getattr(runtime.settings, "image_generation_enabled", False) else None,
    )
    result = {
        "runtime": runtime,
        "buscadores": runtime.search_providers,
        "gerar": runtime.generate,
        "cliente_site": runtime.site_client,
        "catalogo": runtime.catalog,
        "historico": runtime.store,
        "dependencias_receita": dependencias_receita,
    }
    if tipo != "dica":
        return result
    if subcategoria:
        raise ValueError("dicas não aceitam --subcategoria")
    if not runtime.settings.site_articles_enabled:
        raise ConfigurationError("SITE_ARTICLES_ENABLED deve estar habilitado para o fluxo de dicas")

    from agente_receitas.agents.planejador import (
        AssuntoDica,
        AssuntosDicaMemoria,
        BloqueiosMemoria,
        CoberturaMock,
        FilaMemoria,
        HistoricoMemoria,
        ItemFila,
        TaxonomiaMemoria,
        carregar_calendario,
    )
    from agente_receitas.pipeline.gerar_conteudo_educativo import DependenciasDica
    from agente_receitas.services.busca_service import Orcamento, LeitorHTTP
    from agente_receitas.services.image_providers import ImageSelector
    from agente_receitas.validators.dica import ValidadorDica
    from pathlib import Path
    import json
    import secrets

    topics = runtime.catalog.tip_topics()
    risk_levels = {0: {"low"}, 1: {"low"}, 2: {"low", "medium"}, 3: {"low", "medium", "high"}}
    allowed = [
        topic for topic in topics
        if isinstance(topic, dict)
        and topic.get("active") is True
        and topic.get("agentEnabled") is True
        and topic.get("riskLevel") in risk_levels[runtime.settings.site_phase]
    ]
    requested = assunto.strip().lower()
    if requested != "automatico":
        selected = next((topic for topic in allowed if topic.get("slug") == requested), None)
        if selected is None:
            raise ValueError("ASSUNTO deve ser um assunto de dica habilitado para a fase atual")
    else:
        if not allowed:
            raise ConfigurationError("o site não oferece assuntos de dica habilitados para esta fase")
        selected = secrets.choice(allowed)

    assunto_slug = selected["slug"]
    fila = FilaMemoria([ItemFila(tema=selected["name"], assunto=assunto_slug)])
    assuntos = AssuntosDicaMemoria([
        AssuntoDica(
            slug=topic["slug"],
            risk_level=topic["riskLevel"],
            agent_enabled=topic["agentEnabled"] is True,
            active=topic["active"] is True,
        )
        for topic in topics if isinstance(topic, dict)
        and isinstance(topic.get("slug"), str)
        and isinstance(topic.get("riskLevel"), str)
    ])
    historico = (
        _HistoricoStore(runtime.store, run_id)
        if runtime.store is not None and not dry_run
        else HistoricoMemoria()
    )
    bloqueios_data = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "pautas_bloqueadas.json").read_text(encoding="utf-8")
    )
    bloqueios: dict[str, list[str]] = {}
    for item in bloqueios_data.get("itens", []):
        if isinstance(item, dict) and isinstance(item.get("motivo"), str):
            termos = item.get("termos", [])
            if isinstance(termos, list):
                bloqueios[item["motivo"]] = [term for term in termos if isinstance(term, str)]

    from agente_receitas.agents.pesquisador import pesquisar_dica

    def pesquisar_tip(pauta: dict) -> dict:
        budget = Orcamento(
            cfg_fontes["limites_por_pauta"]["max_buscas"],
            cfg_fontes["limites_por_pauta"]["max_paginas"],
            cfg_fontes["limites_por_pauta"]["timeout_min"],
        )
        return pesquisar_dica(
            pauta,
            buscadores=runtime.search_providers,
            leitor=leitor,
            extrator=lambda prompt: runtime.generate("extraction", prompt).texto,
            cfg=cfg_fontes,
            orcamento=budget,
        )

    deps_dica = DependenciasDica(
        fila=fila,
        taxonomia=TaxonomiaMemoria([]),
        assuntos=assuntos,
        cobertura=CoberturaMock(),
        historico=historico,
        cliente=runtime.site_client,
        pesquisar=pesquisar_tip,
        gerar=runtime.generate,
        validador=ValidadorDica(),
        visao=runtime.vision or SemVisao(),
        selector=ImageSelector(),
        usadas=runtime.store or ImagensUsadasMemoria(),
        conteudo_existente=None if dry_run else runtime.catalog,
        bloqueios=BloqueiosMemoria(bloqueios),
        calendario=carregar_calendario(),
        gerar_imagem=gerar_imagem if getattr(runtime.settings, "image_generation_enabled", False) else None,
    )
    result["dependencias_dica"] = deps_dica
    result["assunto_selecionado"] = assunto_slug
    result["dependencias_pendentes"] = {"dica": []}
    return result
