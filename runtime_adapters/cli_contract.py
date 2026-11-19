"""Ponto de composição para conectar à CLI existente sem alterar pipelines.

O pipeline local é injetável e sua assinatura deve ser preservada. Este módulo
entrega as dependências já implementadas para o pipeline de receitas. Pesquisa
de dicas não é composta enquanto não houver fonte de pesquisa própria validada.
"""
from .compose import build_runtime


def build_services(
    *, dry_run: bool = True, target: str = "preview",
):
    runtime = build_runtime(
        dry_run=dry_run, target=target
    )
    from agents.analista import Analista
    from agents.pesquisador import pesquisar_receita
    from pipeline.gerar_receitas import DependenciasReceita, ValidadorPontoUnico
    from services.busca_service import LeitorHTTP
    from services.image_providers import ImageSelector, ImagensUsadasMemoria, SemVisao

    def pesquisar(pauta: dict):
        return pesquisar_receita(
            pauta,
            buscadores=runtime.search_providers,
            leitor=LeitorHTTP(),
            analista=Analista(catalogo=runtime.catalog, fase=runtime.settings.site_phase),
            extrator=lambda prompt: runtime.generate("extraction", prompt).texto,
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
    )
    return {
        "runtime": runtime,
        "buscadores": runtime.search_providers,
        "gerar": runtime.generate,
        "cliente_site": runtime.site_client,
        "catalogo": runtime.catalog,
        "historico": runtime.store,
        "dependencias_receita": dependencias_receita,
        "dependencias_pendentes": {
            "dica": [
                "pesquisa e seleção de tipTopic não estão implementadas no agente",
                "POST /api/articles não está implantado no destino local",
            ]
        },
    }
