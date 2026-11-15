"""
busca_service.py — Interface de busca e leitura de páginas (Passo 5, item 1).

Base: docs/02-PESQUISA.md §4.2 (busca restrita às fontes aprovadas e limites),
§8 (falhas), §10 (segurança) e §11 (respeito às fontes).

O que este módulo entrega:
- Buscador: interface de busca com filtro de domínios (provedor ainda não
  definido, ver 02 §12). Só existe o BuscadorMock.
- LeitorPaginas: interface de leitura do texto da página. O texto é DADO BRUTO
  e fica só em memória (02 §6.2). Só existe o LeitorMock; o leitor HTTP real é
  PENDENTE até o portão de termos de uso e robots.txt (02 §12).
- Orcamento: limites por pauta (buscas, páginas, tempo).
- buscar_com_tentativas(): tentativas e troca de provedor (02 §8).

Nada aqui acessa a rede.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence
from urllib.parse import urlparse


class BuscaIndisponivel(Exception):
    """Todos os provedores falharam (02 §8: a execução termina com status erro)."""


class OrcamentoEsgotado(Exception):
    """Limite de buscas, páginas ou tempo da pauta atingido (02 §4.2)."""


class ProvedorNaoDefinido(Exception):
    """PESQUISA_PROVEDOR aponta para um provedor sem implementação (02 §12)."""


@dataclass(frozen=True)
class ResultadoBusca:
    url: str
    titulo: str
    dominio: str = ""

    def __post_init__(self) -> None:
        if not self.dominio:
            object.__setattr__(self, "dominio", dominio_de(self.url))


def dominio_de(url: str) -> str:
    """Host em minúsculas, sem 'www.'."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def dominio_permitido(dominio: str, permitidos: Sequence[str]) -> bool:
    """Igual a um domínio aprovado ou subdomínio dele (02 §10 item 3)."""
    d = dominio.lower()
    return any(d == p.lower() or d.endswith("." + p.lower()) for p in permitidos if p)


class Buscador(Protocol):
    nome: str

    def buscar(
        self, consulta: str, dominios: Sequence[str], max_resultados: int
    ) -> list[ResultadoBusca]: ...


class LeitorPaginas(Protocol):
    def ler(self, url: str) -> str:
        """Devolve o texto bruto da página. Quem chama não grava em disco."""
        ...


# --------------------------------------------------------------------------
# Provedores de teste
# --------------------------------------------------------------------------


@dataclass
class BuscadorMock:
    """
    Provedor de teste. `respostas` mapeia consulta -> resultados; a chave "*"
    vale para qualquer consulta. `falhas` é o número de chamadas que devem
    levantar erro antes de responder (simula indisponibilidade).
    """

    respostas: dict[str, list[ResultadoBusca]] = field(default_factory=dict)
    falhas: int = 0
    nome: str = "mock"
    chamadas: list[str] = field(default_factory=list)

    def buscar(self, consulta, dominios, max_resultados):
        self.chamadas.append(consulta)
        if self.falhas > 0:
            self.falhas -= 1
            raise RuntimeError("mock: provedor indisponível")
        itens = self.respostas.get(consulta, self.respostas.get("*", []))
        if dominios:
            itens = [r for r in itens if dominio_permitido(r.dominio, dominios)]
        return list(itens[:max_resultados])


@dataclass
class LeitorMock:
    """Leitor de teste: url -> texto (ou Exception para simular bloqueio)."""

    paginas: dict[str, str | Exception] = field(default_factory=dict)
    lidas: list[str] = field(default_factory=list)

    def ler(self, url: str) -> str:
        self.lidas.append(url)
        valor = self.paginas.get(url)
        if valor is None:
            raise LookupError(f"mock: página não cadastrada: {url}")
        if isinstance(valor, Exception):
            raise valor
        return valor


class LeitorHTTP:
    """
    PENDENTE (02 §12): leitura real só depois do portão de termos de uso e
    robots.txt de cada fonte. Deve respeitar robots.txt, limites e bloqueios e
    identificar-se de forma honesta (02 §11).
    """

    def ler(self, url: str) -> str:  # pragma: no cover
        raise NotImplementedError(
            "PENDENTE: leitor HTTP depende do portão de termos de uso e "
            "robots.txt das fontes (docs/02 §12)."
        )


def criar_buscador(nome: str) -> Buscador:
    """Fábrica por PESQUISA_PROVEDOR. Só 'mock' existe (provedor não definido)."""
    if (nome or "mock").strip().lower() == "mock":
        return BuscadorMock()
    raise ProvedorNaoDefinido(
        f"Provedor de busca '{nome}' não implementado (decisão pendente, docs/02 §12)."
    )


# --------------------------------------------------------------------------
# Orçamento por pauta
# --------------------------------------------------------------------------


@dataclass
class Orcamento:
    """Limites por pauta (02 §4.2). Uma busca lógica conta 1, mesmo com retentativas."""

    max_buscas: int = 8
    max_paginas: int = 6
    timeout_min: float = 10
    relogio: Callable[[], float] = time.monotonic
    buscas: int = 0
    paginas: int = 0
    _inicio: float | None = None

    def iniciar(self) -> None:
        if self._inicio is None:
            self._inicio = self.relogio()

    def _checar_tempo(self) -> None:
        self.iniciar()
        if (self.relogio() - self._inicio) > self.timeout_min * 60:
            raise OrcamentoEsgotado("tempo máximo da etapa de pesquisa atingido")

    def consumir_busca(self) -> None:
        self._checar_tempo()
        if self.buscas >= self.max_buscas:
            raise OrcamentoEsgotado("limite de buscas por pauta atingido")
        self.buscas += 1

    def consumir_pagina(self) -> None:
        self._checar_tempo()
        if self.paginas >= self.max_paginas:
            raise OrcamentoEsgotado("limite de páginas por pauta atingido")
        self.paginas += 1

    @property
    def buscas_restantes(self) -> int:
        return max(0, self.max_buscas - self.buscas)

    @property
    def paginas_restantes(self) -> int:
        return max(0, self.max_paginas - self.paginas)


def buscar_com_tentativas(
    buscadores: Sequence[Buscador],
    consulta: str,
    dominios: Sequence[str],
    max_resultados: int,
    orcamento: Orcamento,
    tentativas: int = 2,
    espera: Callable[[float], None] = time.sleep,
) -> list[ResultadoBusca]:
    """
    02 §8: até `tentativas` por provedor; depois troca de provedor, se houver;
    sem provedor disponível levanta BuscaIndisponivel.

    Defesa (02 §10 item 3): descarta qualquer resultado fora dos domínios
    aprovados, mesmo que o provedor ignore o filtro.
    """
    orcamento.consumir_busca()
    ultimo_erro: Exception | None = None
    for buscador in buscadores:
        for tentativa in range(1, max(1, tentativas) + 1):
            try:
                brutos = buscador.buscar(consulta, dominios, max_resultados)
            except Exception as exc:  # provedor externo: qualquer falha conta
                ultimo_erro = exc
                if tentativa < tentativas:
                    espera(float(tentativa))
                continue
            return [r for r in brutos if dominio_permitido(r.dominio, dominios)]
    raise BuscaIndisponivel(f"nenhum provedor respondeu: {ultimo_erro}")
