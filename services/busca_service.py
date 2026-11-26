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

import os
import time
import ipaddress
import json
import socket
from html.parser import HTMLParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


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
    snippet: str = ""
    date: str | None = None
    last_updated: str | None = None

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
        self,
        consulta: str | Sequence[str],
        dominios: Sequence[str] | None = None,
        max_resultados: int = 10,
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
    """Leitor limitado às fontes com termos aprovados e respeitando robots.txt."""

    def __init__(
        self,
        fontes: Sequence[dict] | None = None,
        *,
        user_agent: str = "ChocoliciaRecipeAgent/1.0 (+https://www.chocolicia.site/agent)",
        timeout: float = 10.0,
        max_bytes: int = 2_000_000,
        cliente: httpx.Client | None = None,
    ):
        if fontes is None:
            path = Path(__file__).resolve().parents[1] / "config" / "fontes.json"
            fontes = json.loads(path.read_text(encoding="utf-8")).get("fontes", [])
        self._fontes = [
            f for f in fontes
            if f.get("ativa") is True and f.get("termos_aprovados") is True and f.get("dominio")
        ]
        self._user_agent = user_agent
        self._max_bytes = max_bytes
        self._client = cliente or httpx.Client(timeout=timeout, follow_redirects=False)
        self._robots: dict[str, RobotFileParser] = {}

    @staticmethod
    def _public_host(host: str) -> bool:
        try:
            addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)}
        except (OSError, ValueError):
            return False
        return bool(addresses) and all(ip.is_global for ip in addresses)

    @staticmethod
    def _plain_text(html: str) -> str:
        class TextExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.parts: list[str] = []
                self.hidden = 0

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag in {"script", "style", "noscript", "svg", "template"}:
                    self.hidden += 1

            def handle_endtag(self, tag: str) -> None:
                if tag in {"script", "style", "noscript", "svg", "template"} and self.hidden:
                    self.hidden -= 1

            def handle_data(self, data: str) -> None:
                if not self.hidden and data.strip():
                    self.parts.append(data.strip())

        parser = TextExtractor()
        parser.feed(html)
        return " ".join(parser.parts)

    def _approved_source(self, host: str) -> dict | None:
        return next(
            (f for f in self._fontes if dominio_permitido(host, [f["dominio"]])),
            None,
        )

    def _robots_for(self, origin: str, host: str) -> RobotFileParser:
        if host not in self._robots:
            robots_url = urljoin(origin, "/robots.txt")
            response = self._client.get(robots_url, headers={"User-Agent": self._user_agent})
            if response.status_code in {401, 403, 429} or response.status_code >= 500:
                raise PermissionError("robots.txt indisponível ou bloqueado")
            if response.is_redirect:
                raise PermissionError("redirecionamento de robots.txt não permitido")
            parser = RobotFileParser(robots_url)
            parser.parse(response.text.splitlines() if response.status_code == 200 else [])
            self._robots[host] = parser
        return self._robots[host]

    def ler(self, url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            raise ValueError("URL de fonte deve usar HTTPS e não pode conter credenciais")
        if self._approved_source(host) is None:
            raise PermissionError("termos de uso da fonte ainda não foram aprovados")
        if not self._public_host(host):
            raise PermissionError("host de fonte não é público")
        origin = f"https://{host}"
        robots = self._robots_for(origin, host)
        if not robots.can_fetch(self._user_agent, url):
            raise PermissionError("robots.txt não permite a leitura da página")
        response = self._client.get(
            url,
            headers={"User-Agent": self._user_agent, "Accept": "text/html"},
        )
        if response.is_redirect:
            raise PermissionError("redirecionamento de página não permitido")
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", "").lower():
            raise ValueError("fonte não retornou HTML")
        if len(response.content) > self._max_bytes:
            raise ValueError("página excede o limite de bytes")
        return self._plain_text(response.text)[:30_000]


class BuscadorPerplexity:
    """
    Provedor de busca com Perplexity Search API (POST https://api.perplexity.ai/search).
    Usa o SDK oficial (from perplexity import Perplexity).
    Retorna resultados estruturados (url, titulo, snippet, date, last_updated) sem respostas LLM.
    """

    nome: str = "perplexity"

    def __init__(
        self,
        api_key: str | None = None,
        cliente: Any = None,
        *,
        country: str | None = "BR",
        search_context_size: str | None = None,
        search_language_filter: Sequence[str] | None = None,
        search_recency_filter: str | None = None,
        max_retries: int = 2,
    ) -> None:
        self.country = country
        self.search_context_size = search_context_size
        self.search_language_filter = list(search_language_filter) if search_language_filter else None
        self.search_recency_filter = search_recency_filter
        self.max_retries = max_retries

        if cliente is not None:
            self._cliente = cliente
        else:
            resolved_key = (api_key or os.getenv("PERPLEXITY_API_KEY") or "").strip()
            if not resolved_key:
                raise ValueError(
                    "PERPLEXITY_API_KEY não configurada. Crie uma chave em "
                    "https://console.perplexity.ai e configure a variável de ambiente PERPLEXITY_API_KEY."
                )
            from perplexity import Perplexity
            self._cliente = Perplexity(api_key=resolved_key, max_retries=max_retries)

    def buscar(
        self,
        consulta: str | Sequence[str],
        dominios: Sequence[str] | None = None,
        max_resultados: int = 10,
        *,
        country: str | None = None,
        search_context_size: str | None = None,
        search_language_filter: Sequence[str] | None = None,
        search_recency_filter: str | None = None,
    ) -> list[ResultadoBusca]:
        if isinstance(consulta, str):
            consultas = [consulta.strip()] if consulta.strip() else []
        else:
            consultas = [c.strip() for c in consulta if c and c.strip()]

        if not consultas:
            return []

        limite_resultados = max(1, min(20, int(max_resultados)))
        domain_filter: list[str] | None = None
        if dominios:
            domain_filter = [d.strip() for d in dominios if d and d.strip()][:20]

        pais = country if country is not None else self.country
        context_size = search_context_size if search_context_size is not None else self.search_context_size
        lang_filter = list(search_language_filter) if search_language_filter is not None else self.search_language_filter
        recency_filter = search_recency_filter if search_recency_filter is not None else self.search_recency_filter

        # API Perplexity Search aceita até 5 consultas por requisição
        lotes = [consultas[i : i + 5] for i in range(0, len(consultas), 5)]

        resultados_consolidados: list[ResultadoBusca] = []
        urls_vistas: set[str] = set()

        for lote in lotes:
            kwargs: dict[str, Any] = {
                "query": lote[0] if len(lote) == 1 else lote,
                "max_results": limite_resultados,
            }
            if domain_filter:
                kwargs["search_domain_filter"] = domain_filter
            if pais:
                kwargs["country"] = pais
            if context_size in {"low", "medium", "high"}:
                kwargs["search_context_size"] = context_size
            if lang_filter:
                kwargs["search_language_filter"] = lang_filter
            if recency_filter in {"hour", "day", "week", "month", "year"}:
                kwargs["search_recency_filter"] = recency_filter

            try:
                resposta = self._cliente.search.create(**kwargs)
            except Exception as exc:
                nome_erro = exc.__class__.__name__
                status_code = getattr(exc, "status_code", None)
                if nome_erro == "AuthenticationError" or status_code == 401:
                    raise RuntimeError(
                        "Falha de autenticação na API Perplexity (401). "
                        "Verifique PERPLEXITY_API_KEY em https://console.perplexity.ai."
                    ) from exc
                if nome_erro == "RateLimitError" or status_code == 429:
                    headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
                    retry_after = headers.get("retry-after") or headers.get("Retry-After")
                    aviso_retry = f" (Retry-After: {retry_after})" if retry_after else ""
                    raise RuntimeError(
                        f"Limite de requisições excedido na API Perplexity (429){aviso_retry}."
                    ) from exc
                raise RuntimeError(f"Erro na chamada da API Perplexity: {exc}") from exc

            itens = getattr(resposta, "results", None) or []
            for item in itens:
                url = str(getattr(item, "url", "") or "").strip()
                if not url or url in urls_vistas:
                    continue

                if dominios and not dominio_permitido(dominio_de(url), dominios):
                    continue

                urls_vistas.add(url)
                titulo = str(getattr(item, "title", "") or "").strip()
                snippet = str(getattr(item, "snippet", "") or "").strip()
                date_val = getattr(item, "date", None)
                last_updated_val = getattr(item, "last_updated", None)

                resultados_consolidados.append(
                    ResultadoBusca(
                        url=url,
                        titulo=titulo,
                        snippet=snippet,
                        date=str(date_val) if date_val else None,
                        last_updated=str(last_updated_val) if last_updated_val else None,
                    )
                )

        return resultados_consolidados


def criar_buscador(nome: str, **kwargs: Any) -> Buscador:
    """Fábrica por PESQUISA_PROVEDOR."""
    provedor = (nome or "mock").strip().lower()
    if provedor == "mock":
        return BuscadorMock()
    if provedor in {"perplexity", "perplexityai"}:
        return BuscadorPerplexity(**kwargs)
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
