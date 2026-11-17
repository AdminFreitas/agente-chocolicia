"""Ponto de composição para conectar à CLI existente sem alterar pipelines.

O pipeline local é injetável e sua assinatura deve ser preservada. Este módulo
entrega os serviços reais; o chamador mapeia Runtime para DependenciasReceita /
DependenciasDica conforme os dataclasses presentes no checkout local.
"""
from .compose import build_runtime


def build_services(
    *, dry_run: bool = True, fase: int | None = None, contrato: str = "v1",
    target: str = "preview",
):
    runtime = build_runtime(
        dry_run=dry_run, fase=fase, contrato=contrato, target=target
    )
    return {
        "runtime": runtime,
        "buscadores": runtime.search_providers,
        "gerar": runtime.generate,
        "cliente_site": runtime.site_client,
        "catalogo": runtime.catalog,
        "historico": runtime.store,
    }
