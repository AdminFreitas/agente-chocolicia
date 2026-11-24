"""
services/image_providers/selector.py — Seleção da capa (docs/01 §8.2, docs/08 §4.9).

Fluxo (01 §8.2): termos do mais específico ao mais geral -> bancos de imagens em
ordem de prioridade -> triagem barata -> download SÓ EM MEMÓRIA -> verificação por
visão -> proveniência no payload. Sem candidata utilizável, devolve
cover.mode = "generate" com o prompt_imagem (docs/06 §7.1 e §7.2).

Verificações aplicadas (docs/08 §4.9):
  IMG-01 licença (licencas.py)             IMG-02 largura mínima 1280 px (metadado e arquivo real)
  IMG-03 host de origem permitido + HTTPS  IMG-04 visão (VerificadorVisao)
  IMG-05 imagem já usada (url, id e hash)  IMG-06 proveniência completa
  IMG-07 IA só depois de esgotar os bancos e se o teto permitir (parâmetro)
IMG-08 (texto alternativo) é do conteúdo/SEO, não da seleção.

PENDENTES (ver "Lacunas"): VerificadorVisao real (o llm_service não aceita imagem),
ImagensUsadas persistente (a doc não define a origem), lista de hosts conferida.
O agente NÃO registra a imagem como usada: quem publica chama
ImagensUsadas.registrar() depois do sucesso no site.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, Sequence
from urllib.parse import urlparse

from agente_receitas.services.busca_service import dominio_permitido
from agente_receitas.services.image_providers.base import ImageProvider, StandardImageResult
from agente_receitas.services.image_providers.licencas import classificar_licenca
from agente_receitas.services.image_providers.openverse import OpenverseProvider
from agente_receitas.services.image_providers.pexels import PexelsProvider
from agente_receitas.services.image_providers.pixabay import PixabayProvider
from agente_receitas.services.image_providers.storage import ImagemBaixada, baixar_imagem_em_memoria
from agente_receitas.services.image_providers.wikimedia import WikimediaProvider

log = logging.getLogger(__name__)

MIN_WIDTH = 1280  # docs/08 IMG-02
# Parâmetros de implementação (a doc não define): limitam custo e tráfego por execução.
MAX_DOWNLOADS = 6
MAX_VERIFICACOES_VISAO = 4
CANDIDATAS_POR_BUSCA = 5
_AUTOR_PLACEHOLDER = {
    "autor desconhecido", "autor wikimedia", "pixabay contributor", "pexels photographer", "unknown", "desconhecido",
}


# --------------------------------------------------------------------------
# Interfaces (PENDENTES) e implementações de teste
# --------------------------------------------------------------------------


class VisaoIndisponivel(Exception):
    """Não há verificador de visão configurado (IMG-04 PENDENTE)."""


@dataclass
class ResultadoVisao:
    prato_correto: Optional[bool] = None
    sem_pessoas: Optional[bool] = None
    sem_texto_ou_marca: Optional[bool] = None
    enquadramento_ok: Optional[bool] = None
    observacao: str = ""

    def _campos(self) -> dict:
        return {
            "prato_correto": self.prato_correto, "sem_pessoas": self.sem_pessoas,
            "sem_texto_ou_marca": self.sem_texto_ou_marca, "enquadramento_ok": self.enquadramento_ok,
        }

    @property
    def aprovado(self) -> bool:
        """Falha fechada: None (não avaliado) reprova."""
        return all(v is True for v in self._campos().values())

    def reprovados(self) -> list[str]:
        return [n for n, v in self._campos().items() if v is not True]


class VerificadorVisao(Protocol):
    def verificar(self, imagem: bytes, mime: str, esperado: str) -> ResultadoVisao:
        """IMG-04. `imagem` fica só em memória. PENDENTE: o llm_service não aceita imagem."""
        ...


class SemVisao:
    def verificar(self, imagem, mime, esperado):
        raise VisaoIndisponivel("PENDENTE: verificação por visão (o llm_service não suporta imagem)")


class ImagensUsadas(Protocol):
    """IMG-05. PENDENTE: a doc não define a origem desta informação (ver "Lacunas")."""

    def usada_url(self, url: str) -> bool: ...
    def usada_provider_id(self, provider: str, provider_image_id: str) -> bool: ...
    def usada_hash(self, sha256: str) -> bool: ...
    def registrar(self, url: str, sha256: str, provider: str, provider_image_id: str) -> None: ...


class ImagensUsadasMemoria:
    def __init__(self) -> None:
        self._urls: set[str] = set()
        self._ids: set[tuple[str, str]] = set()
        self._hashes: set[str] = set()

    def usada_url(self, url):
        return url in self._urls

    def usada_provider_id(self, provider, provider_image_id):
        return (provider, provider_image_id) in self._ids

    def usada_hash(self, sha256):
        return sha256 in self._hashes

    def registrar(self, url, sha256, provider, provider_image_id):
        self._urls.add(url)
        self._hashes.add(sha256)
        self._ids.add((provider, provider_image_id))


# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------


@dataclass
class ResultadoImagem:
    status: str  # "stock" | "generate" | "sem_imagem"
    cover: Optional[dict] = None  # payload do site (docs/06 §7.1/§7.2)
    meta: dict = field(default_factory=dict)  # dados internos (id, largura, hash...). Não vão no cover.
    conteudo: bytes | None = field(default=None, repr=False)  # bytes transitórios para upload; nunca entram no payload
    rejeitadas: list[dict] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    buscas: int = 0
    downloads: int = 0
    verificacoes_visao: int = 0


# --------------------------------------------------------------------------
# Seletor
# --------------------------------------------------------------------------


class ImageSelector:
    def __init__(
        self,
        providers: Optional[Sequence[ImageProvider]] = None,
        *,
        hosts_permitidos: Optional[Sequence[str]] = None,
        min_width: int = MIN_WIDTH,
    ):
        # Ordem de prioridade (01 §8.2 passo 1): Pixabay, Pexels, Openverse, Wikimedia.
        self.providers = list(providers) if providers is not None else [
            PixabayProvider(), PexelsProvider(), OpenverseProvider(), WikimediaProvider(),
        ]
        if hosts_permitidos is None:
            hosts_permitidos = [h for p in self.providers for h in getattr(p, "IMAGE_HOSTS", ())]
        self.hosts = list(hosts_permitidos)
        self.min_width = min_width

    # ---- triagem sem download ---------------------------------------------------

    def _triagem(self, c: StandardImageResult, usadas: ImagensUsadas) -> Optional[tuple[str, str]]:
        """Devolve (código, motivo) se a candidata deve ser recusada; None se passa."""
        lic = classificar_licenca(c.provider, c.license, c.license_url)
        if not lic.aceita:  # IMG-01
            return "IMG-01", lic.motivo
        if c.width <= 0 or c.width < self.min_width:  # IMG-02 (metadado)
            return "IMG-02", f"largura {c.width or 'desconhecida'} < {self.min_width}"
        if not c.is_horizontal:  # os recortes 1:1, 4:3 e 16:9 (06 §7.1) exigem imagem horizontal
            return "IMG-02", "imagem vertical"
        url = c.original_image_url or ""
        partes = urlparse(url)
        if partes.scheme.lower() != "https":  # IMG-03
            return "IMG-03", "URL da imagem não é HTTPS"
        if not dominio_permitido(partes.hostname or "", self.hosts):
            return "IMG-03", f"host fora da lista permitida: {partes.hostname}"
        # IMG-06: proveniência completa (autor e atribuição só são dispensados em CC0 e domínio público)
        pagina = urlparse(c.original_page_url or "")
        if not c.provider or not (c.license or "").strip() or pagina.scheme.lower() != "https":
            return "IMG-06", "provedor, licença ou página de origem ausentes"
        dispensa = lic.codigo in ("cc0", "pdm")
        autor = (c.photographer or "").strip()
        if not dispensa and (not autor or autor.lower() in _AUTOR_PLACEHOLDER):
            return "IMG-06", "autor ausente"
        if not dispensa and not (c.attribution_text or "").strip():
            return "IMG-06", "texto de atribuição ausente"
        if usadas.usada_url(url) or usadas.usada_provider_id(c.provider, c.provider_image_id):  # IMG-05
            return "IMG-05", "imagem já usada em outro conteúdo"
        return None

    @staticmethod
    def _cover_stock(c: StandardImageResult) -> dict:
        """Objeto exatamente como docs/06 §7.1."""
        return {
            "mode": "stock",
            "provider": c.provider,
            "sourceImageUrl": c.original_image_url,
            "sourcePageUrl": c.original_page_url,
            "author": (c.photographer or "").strip(),
            "license": c.license,
            "attributionText": (c.attribution_text or "").strip(),
        }

    # ---- seleção ------------------------------------------------------------------

    def selecionar(
        self,
        *,
        termos: Sequence[str],
        esperado: str,
        prompt_imagem: str,
        usadas: ImagensUsadas,
        visao: VerificadorVisao,
        baixar: Callable[..., ImagemBaixada] = baixar_imagem_em_memoria,
        geracao_permitida: bool = True,
        lang: str = "en",
    ) -> ResultadoImagem:
        res = ResultadoImagem(status="generate")
        ativos = [p for p in self.providers if p.is_available()]
        if not ativos:
            res.pendencias.append("nenhum provedor de banco de imagens disponível (configurar chaves)")

        vistos: set[tuple[str, str]] = set()
        abortar = False
        for termo in (t.strip() for t in termos if t and t.strip()):  # do mais específico ao mais geral
            if abortar:
                break
            for prov in ativos:
                if abortar:
                    break
                res.buscas += 1
                try:
                    candidatas = prov.search(query=termo, limit=CANDIDATAS_POR_BUSCA, min_width=self.min_width, lang=lang)
                except Exception as exc:
                    log.warning("%s: falha na busca (%s)", prov.name, type(exc).__name__)
                    continue

                for c in candidatas:
                    chave = (c.provider, c.provider_image_id)
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    ident = {"provider": c.provider, "id": c.provider_image_id}

                    motivo = self._triagem(c, usadas)
                    if motivo:
                        res.rejeitadas.append({**ident, "codigo": motivo[0], "motivo": motivo[1]})
                        continue
                    if res.downloads >= MAX_DOWNLOADS or res.verificacoes_visao >= MAX_VERIFICACOES_VISAO:
                        res.pendencias.append("limite de downloads ou verificações por visão atingido")
                        abortar = True
                        break

                    res.downloads += 1
                    try:
                        img = baixar(c.original_image_url, hosts_permitidos=self.hosts)
                    except Exception as exc:
                        res.rejeitadas.append({**ident, "codigo": "IMG-03", "motivo": f"download recusado: {type(exc).__name__}"})
                        continue
                    if img.largura < self.min_width:  # IMG-02 no arquivo real
                        res.rejeitadas.append({**ident, "codigo": "IMG-02", "motivo": f"largura real {img.largura} < {self.min_width}"})
                        continue
                    if usadas.usada_hash(img.sha256):  # IMG-05 por conteúdo
                        res.rejeitadas.append({**ident, "codigo": "IMG-05", "motivo": "mesma imagem (hash) já usada"})
                        continue

                    try:
                        v = visao.verificar(img.conteudo, img.mime, esperado)
                    except VisaoIndisponivel as exc:
                        res.pendencias.append(f"IMG-04: {exc}")
                        abortar = True
                        break
                    except Exception as exc:
                        res.verificacoes_visao += 1
                        res.rejeitadas.append({**ident, "codigo": "IMG-04", "motivo": f"erro na verificação: {type(exc).__name__}"})
                        continue
                    res.verificacoes_visao += 1
                    if not v.aprovado:
                        res.rejeitadas.append({**ident, "codigo": "IMG-04", "motivo": "reprovada: " + ", ".join(v.reprovados())})
                        continue

                    res.status = "stock"
                    res.cover = self._cover_stock(c)
                    res.meta = {
                        "provider_image_id": c.provider_image_id,
                        "width": img.largura, "height": img.altura, "sha256": img.sha256,
                        "mime": img.mime, "search_query": termo, "license_url": c.license_url,
                        "author_url": c.photographer_url, "visao": v.observacao,
                    }
                    res.conteudo = img.conteudo
                    return res  # os bytes ficam apenas no resultado transitório

        # Nenhuma candidata utilizável (IMG-07): geração por IA, se o teto permitir.
        if geracao_permitida:
            res.status = "generate"
            res.cover = {"mode": "generate", "imagePrompt": prompt_imagem}
        else:
            res.status = "sem_imagem"
            res.cover = None
            res.pendencias.append("IMG-07: geração por IA indisponível (teto diário)")
        return res
