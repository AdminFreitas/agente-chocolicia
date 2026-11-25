"""Cliente HTTP do agente para os contratos atual e v1 do site.

O runtime usa `legacy` até o servidor aceitar v1: esse caminho envia somente o schema
atual de receitas, omite `X-Contract-Version` e bloqueia publicação. O caminho v1
mantém os cabeçalhos e escopos definidos em docs/06.

Erros 4xx não são reenviados; 429 respeita Retry-After; 5xx e timeout têm retentativas
limitadas. Tokens não aparecem em logs, repr nem mensagens de erro. `dry_run` valida
o payload e não faz rede. O transporte é injetável para testes.
"""

from __future__ import annotations

import hashlib
import base64
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from agente_receitas.integration.contratos import CONTRACT_VERSION, ArtigoV1, ReceitaLegada, ReceitaV1

log = logging.getLogger(__name__)

TIMEOUT_PADRAO = 60.0  # docs/06 §12: "valor a confirmar de acordo com o plano da Vercel"
MAX_TENTATIVAS = 3  # docs/06 §11
MAX_ESPERA_429 = 120.0  # parâmetro de implementação: teto da espera por Retry-After


# --------------------------------------------------------------------------
# Exceções (nenhuma carrega cabeçalhos ou token)
# --------------------------------------------------------------------------


class ErroSite(Exception):
    def __init__(self, mensagem: str, *, codigo: str = "", http_status: int = 0, detalhes: Any = None, request_id: str = ""):
        super().__init__(mensagem)
        self.mensagem, self.codigo, self.http_status = mensagem, codigo, http_status
        self.detalhes, self.request_id = detalhes or [], request_id

    def __str__(self) -> str:
        partes = [self.mensagem]
        if self.http_status:
            partes.append(f"HTTP {self.http_status}")
        if self.codigo:
            partes.append(f"code={self.codigo}")
        if self.request_id:
            partes.append(f"request_id={self.request_id}")
        return " | ".join(partes)


class ConfiguracaoInvalida(Exception):
    """URL, token ou fase incompatíveis com a operação (nada foi enviado)."""


class ContratoInvalido(Exception):
    """O payload não passa no contrato v1 (API-01). Nada foi enviado."""

    def __init__(self, erros: list[dict]):
        self.erros = erros
        super().__init__("payload fora do contrato v1: " + "; ".join(f"{e['campo']}: {e['detalhe']}" for e in erros[:5]))


class EscopoLocalInsuficiente(ConfiguracaoInvalida):
    """Faltou token de escopo publish ou a fase não permite publicar (checagem local)."""


class SemAutorizacao(ErroSite):  # 401: interrompe a execução e alerta
    pass


class EscopoInsuficiente(ErroSite):  # 403 scope_insufficient
    pass


class PublicacaoBloqueada(ErroSite):  # 403 publishing_disabled | phase_not_allowed
    pass


class RejeitadoPeloSite(ErroSite):  # 400, 413 e 422: não reenviar o mesmo JSON
    pass


class ConteudoGrande(RejeitadoPeloSite):  # 413
    pass


class LimiteDiarioAtingido(ErroSite):  # 429 daily_cap_reached: encerra a execução
    pass


class LimiteDeRequisicoes(ErroSite):  # 429 rate_limited depois das tentativas
    pass


class ErroServidor(ErroSite):  # 5xx depois das tentativas
    pass


class ErroDeRede(ErroSite):  # timeout ou falha de transporte depois das tentativas
    pass


class ConflitoDeSlug(ErroSite):  # 409 sem conteúdo da pauta no site: o slug é de outro conteúdo
    pass


class EndpointBloqueado(ErroSite):
    """O endpoint correspondente não foi confirmado como implantado."""


# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------


@dataclass
class RespostaCriacao:
    # "criado" (201) | "repetido" (replay da mesma chave) | "confirmado_apos_409" |
    # "duplicada" (a pauta já existe de OUTRA execução; nada foi reenviado) | "dry_run"
    situacao: str
    http_status: int = 0
    id: Optional[str] = None
    slug: Optional[str] = None
    status: Optional[str] = None
    url: Optional[str] = None
    request_ids: list[str] = field(default_factory=list)
    tentativas: int = 0
    payload: Optional[dict] = None  # só em dry_run
    cabecalhos: Optional[dict] = None  # só em dry_run, com o token mascarado


def chave_idempotencia(content_type: str, topic_slug: str, run_id: str) -> str:
    """Hash estável de content_type, topic_slug e run_id (docs/06 §6.1)."""
    return hashlib.sha256(f"{content_type}|{topic_slug}|{run_id}".encode("utf-8")).hexdigest()


def formatar_dry_run(resposta: RespostaCriacao) -> str:
    """Texto para --dry-run: payload e cabeçalhos (token mascarado). Não envia nada."""
    return json.dumps(
        {"cabecalhos": resposta.cabecalhos, "payload": resposta.payload}, ensure_ascii=False, indent=2
    )


# --------------------------------------------------------------------------
# Cliente
# --------------------------------------------------------------------------


class ClienteSite:
    def __init__(
        self,
        base_url: str,
        *,
        token_draft: Optional[str] = None,
        token_publish: Optional[str] = None,
        fase: int = 0,
        contract_version: str = CONTRACT_VERSION,
        dry_run: bool = False,
        cliente: Optional[httpx.Client] = None,
        espera: Callable[[float], None] = time.sleep,
        timeout: float = TIMEOUT_PADRAO,
        max_tentativas: int = MAX_TENTATIVAS,
        base_espera: float = 1.0,
        gerar_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        allow_local_http: bool = False,
        allow_production: bool = False,
        articles_enabled: bool = False,
        contract: str = "v1",
        upload_images: bool = False,
    ):
        partes = urlparse(base_url or "")
        host = (partes.hostname or "").lower().rstrip(".")
        if host in {"chocolicia.site", "www.chocolicia.site"} or host.endswith(".chocolicia.site"):
            if not allow_production or host != "www.chocolicia.site" or partes.scheme.lower() != "https":
                raise ConfiguracaoInvalida(
                    "produção exige opt-in explícito e https://www.chocolicia.site"
                )
        elif allow_production:
            raise ConfiguracaoInvalida("opt-in de produção só aceita www.chocolicia.site")
        if partes.scheme.lower() == "http":
            if not allow_local_http or host not in {"localhost", "127.0.0.1"}:
                raise ConfiguracaoInvalida("HTTP só é permitido para loopback em ambiente de teste")
        elif partes.scheme.lower() != "https" or not host:
            raise ConfiguracaoInvalida("SITE_BASE_URL deve usar HTTPS, exceto loopback em teste")
        if partes.path not in ("", "/") or partes.query or partes.fragment or partes.username or partes.password:
            raise ConfiguracaoInvalida("SITE_BASE_URL deve conter somente a origem")
        if fase not in (0, 1, 2, 3):
            raise ConfiguracaoInvalida(f"fase inválida: {fase}")
        if contract not in {"v1", "legacy"}:
            raise ConfiguracaoInvalida("contrato do site inválido")
        self._base = base_url.rstrip("/")
        self._tokens = {"draft": token_draft or None, "publish": token_publish or None}
        self.fase, self.contract_version, self.dry_run = fase, str(contract_version), dry_run
        self.contract = contract
        self.upload_images = upload_images
        self.articles_enabled = articles_enabled
        self._espera, self._timeout, self._max, self._base_espera = espera, timeout, max(1, max_tentativas), base_espera
        self._gerar_id = gerar_id
        self._http = cliente or httpx.Client(timeout=timeout)

    def __repr__(self) -> str:  # sem tokens
        return f"ClienteSite(base={urlparse(self._base).hostname!r}, fase={self.fase}, dry_run={self.dry_run})"

    # ---- escopo e token ---------------------------------------------------------

    def _token_para(self, status: str) -> str:
        if status == "published":
            if self.contract == "legacy":
                # O endpoint atual aceita status=published no próprio POST /api/recipes,
                # autenticado pelo RECIPES_AGENT_TOKEN (um único escopo).
                if self.fase < 1:
                    raise EscopoLocalInsuficiente("a Fase 0 não publica")
                if not self._tokens["publish"]:
                    raise EscopoLocalInsuficiente("falta RECIPES_AGENT_TOKEN")
                return self._tokens["publish"]
            if self.fase < 1:
                raise EscopoLocalInsuficiente("a Fase 0 não publica: use status 'draft' (docs/01 §7.4)")
            if not self._tokens["publish"]:
                raise EscopoLocalInsuficiente("falta o token de escopo publish (SITE_TOKEN_PUBLISH)")
            return self._tokens["publish"]
        token = self._tokens["draft"]
        if not token:
            raise EscopoLocalInsuficiente("falta token (SITE_TOKEN_DRAFT)")
        return token

    def _token_leitura(self) -> str:
        token = self._tokens["draft"]
        if not token:
            raise EscopoLocalInsuficiente("falta token (SITE_TOKEN_DRAFT)")
        return token

    # ---- HTTP ---------------------------------------------------------------------

    @staticmethod
    def _erro_do_corpo(resp: httpx.Response) -> tuple[str, str, Any]:
        """(code, message, details). Aceita {"error": {...}} (contrato) e {"error": "texto"} (site atual)."""
        try:
            corpo = resp.json()
        except Exception:
            return "", "", []
        erro = corpo.get("error") if isinstance(corpo, dict) else None
        if isinstance(erro, dict):
            return str(erro.get("code", "")), str(erro.get("message", "")), erro.get("details", [])
        if isinstance(erro, str):
            return f"legacy_http_{resp.status_code}", erro, (corpo.get("details") if isinstance(corpo, dict) else [])
        return "", "", []

    def _requisitar(
        self, metodo: str, caminho: str, *, token: str, corpo: Optional[dict] = None,
        params: Optional[dict] = None, chave: Optional[str] = None,
    ) -> tuple[httpx.Response, list[str]]:
        ids: list[str] = []
        ultimo: Optional[ErroSite] = None
        for tentativa in range(1, self._max + 1):
            rid = self._gerar_id()
            ids.append(rid)
            cab = {"Authorization": f"Bearer {token}", "Accept": "application/json", "X-Request-Id": rid}
            # Token OIDC efêmero emitido pelo GitHub Actions para Trusted Sources da Vercel.
            # Nunca registrar nem persistir este cabeçalho.
            vercel_oidc = os.getenv("VERCEL_TRUSTED_OIDC_TOKEN", "").strip()
            if vercel_oidc:
                cab["x-vercel-trusted-oidc-idp-token"] = vercel_oidc
            if self.contract != "legacy":
                cab["X-Contract-Version"] = self.contract_version
            if corpo is not None:
                cab["Content-Type"] = "application/json"
            if chave:
                cab["Idempotency-Key"] = chave
            try:
                resp = self._http.request(metodo, self._base + caminho, headers=cab, params=params, timeout=self._timeout,
                                          content=json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else None)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                log.warning("site %s %s: %s (request_id=%s, tentativa %s)", metodo, caminho, type(exc).__name__, rid, tentativa)
                ultimo = ErroDeRede(f"falha de rede ({type(exc).__name__})", request_id=rid)
                if tentativa < self._max:
                    self._espera(self._base_espera * 2 ** (tentativa - 1))
                    continue
                raise ultimo from None

            log.info("site %s %s -> %s (request_id=%s)", metodo, caminho, resp.status_code, rid)
            if resp.status_code >= 500:
                codigo, msg, det = self._erro_do_corpo(resp)
                ultimo = ErroServidor(msg or "erro no servidor do site", codigo=codigo or "server_error",
                                      http_status=resp.status_code, detalhes=det, request_id=rid)
                if tentativa < self._max:
                    self._espera(self._base_espera * 2 ** (tentativa - 1))
                    continue
                raise ultimo
            if resp.status_code == 429:
                codigo, msg, det = self._erro_do_corpo(resp)
                if codigo == "daily_cap_reached":
                    raise LimiteDiarioAtingido(msg or "limite diário atingido", codigo=codigo, http_status=429, detalhes=det, request_id=rid)
                ultimo = LimiteDeRequisicoes(msg or "limite de requisições", codigo=codigo or "rate_limited",
                                             http_status=429, detalhes=det, request_id=rid)
                if tentativa < self._max:
                    try:
                        espera = float(resp.headers.get("retry-after", ""))
                    except ValueError:
                        espera = self._base_espera
                    self._espera(min(max(espera, 0.0), MAX_ESPERA_429))
                    continue
                raise ultimo
            return resp, ids
        raise ultimo or ErroDeRede("sem resposta", request_id=ids[-1])  # pragma: no cover

    def _levantar(self, resp: httpx.Response, ids: list[str]) -> None:
        """Converte respostas de erro (4xx) em exceções. 2xx passa."""
        s = resp.status_code
        if s < 400:
            return
        codigo, msg, det = self._erro_do_corpo(resp)
        kw = dict(codigo=codigo, http_status=s, detalhes=det, request_id=ids[-1])
        if s == 401:
            raise SemAutorizacao(msg or "não autorizado", **kw)
        if s == 403:
            if codigo in ("publishing_disabled", "phase_not_allowed"):
                raise PublicacaoBloqueada(msg or "publicação bloqueada", **kw)
            raise EscopoInsuficiente(msg or "escopo insuficiente", **kw)
        if s == 413:
            raise ConteudoGrande(msg or "conteúdo acima do limite", **kw)
        if s in (400, 422):
            raise RejeitadoPeloSite(msg or "conteúdo rejeitado pelo site", **kw)
        raise ErroSite(msg or f"HTTP {s}", **kw)

    # ---- escrita -------------------------------------------------------------------

    def upload_imagem(self, conteudo: bytes, *, content_type: str, alt: str, nome: str) -> str:
        """Envia bytes validados ao storage público do site e devolve URL HTTPS."""
        if not conteudo:
            raise ContratoInvalido([{"campo": "imagem", "detalhe": "conteúdo vazio"}])
        if not content_type.startswith("image/"):
            raise ContratoInvalido([{"campo": "contentType", "detalhe": "tipo de imagem inválido"}])
        token = self._token_para("draft")
        chave = hashlib.sha256(b"image|" + hashlib.sha256(conteudo).digest()).hexdigest()
        corpo = {
            "fileName": nome[:180], "contentType": content_type,
            "dataBase64": base64.b64encode(conteudo).decode("ascii"),
            "alt": alt[:180],
        }
        if self.dry_run:
            return "https://dry-run.invalid/images/" + chave
        resp, ids = self._requisitar("POST", "/api/uploads", token=token, corpo=corpo, chave=chave)
        self._levantar(resp, ids)
        try:
            dados = resp.json()
        except Exception:
            raise ErroSite("resposta de upload sem JSON válido", http_status=resp.status_code, request_id=ids[-1]) from None
        url = dados.get("url") if isinstance(dados, dict) else None
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ErroSite("upload não devolveu URL HTTPS pública", http_status=resp.status_code, request_id=ids[-1])
        return url

    def criar_receita(
        self, payload: dict | ReceitaV1, *, run_id: str,
        idempotency_key: Optional[str] = None,
        reduzir: Optional[Callable[[dict], dict]] = None,
    ) -> RespostaCriacao:
        if self.contract == "legacy":
            return self._criar_receita_legada(
                payload, idempotency_key=idempotency_key, run_id=run_id
            )
        return self._criar("/api/recipes", "recipe", ReceitaV1, payload, run_id, reduzir)

    def publicar_receita(self, slug: str) -> RespostaCriacao:
        if self.contract == "legacy":
            raise EscopoLocalInsuficiente(
                "publicação bloqueada: o endpoint atual não oferece escopo publish"
            )
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ContratoInvalido([{"campo": "slug", "detalhe": "slug inválido"}])
        token = self._tokens["publish"]
        if self.fase < 1:
            raise EscopoLocalInsuficiente("a Fase 0 não publica")
        if not token:
            raise EscopoLocalInsuficiente("falta o token de escopo publish (SITE_TOKEN_PUBLISH)")
        chave = hashlib.sha256(f"publish|{slug}".encode("utf-8")).hexdigest()
        resp, ids = self._requisitar(
            "POST", f"/api/recipes/{slug}/publish", token=token, chave=chave
        )
        self._levantar(resp, ids)
        try:
            dados = resp.json()
        except Exception:
            raise ErroSite(
                "resposta de publicação sem JSON válido",
                http_status=resp.status_code,
                request_id=ids[-1],
            ) from None
        if (
            not isinstance(dados, dict)
            or dados.get("id") is None
            or dados.get("slug") != slug
            or dados.get("status") != "published"
        ):
            raise ErroSite(
                "API não confirmou publicação do rascunho",
                http_status=resp.status_code,
                request_id=ids[-1],
            )
        replay = resp.headers.get("idempotent-replay", "").lower() == "true"
        return RespostaCriacao(
            "repetido" if replay else "publicado", resp.status_code,
            dados["id"], dados["slug"], dados["status"], dados.get("url"),
            ids, len(ids),
        )

    def criar_artigo(self, payload: dict | ArtigoV1, *, run_id: str, reduzir: Optional[Callable[[dict], dict]] = None) -> RespostaCriacao:
        if not self.articles_enabled:
            raise EndpointBloqueado(
                "publicação de dicas/artigos bloqueada: POST /api/articles não está implantado",
                codigo="article_endpoint_not_deployed",
            )
        tipo = payload.type if isinstance(payload, ArtigoV1) else (payload or {}).get("type")
        if tipo not in ("article", "tip", "technique"):
            raise ContratoInvalido([{"campo": "type", "detalhe": "técnica, dica ou matéria"}])
        return self._criar("/api/articles", tipo, ArtigoV1, payload, run_id, reduzir)

    def _criar_receita_legada(
        self, payload, *, idempotency_key: Optional[str], run_id: str
    ) -> RespostaCriacao:
        if isinstance(payload, ReceitaLegada):
            validado = payload
        else:
            try:
                validado = ReceitaLegada.model_validate(payload)
            except ValidationError as exc:
                raise ContratoInvalido(
                    [{"campo": ".".join(map(str, e["loc"])), "detalhe": e["msg"]} for e in exc.errors()]
                ) from None
        token = self._token_para(validado.status)
        corpo = validado.model_dump(mode="json", exclude_none=True)
        chave = hashlib.sha256(
            f"recipe|{idempotency_key or run_id}".encode("utf-8")
        ).hexdigest()
        if self.dry_run:
            return RespostaCriacao(
                "dry_run", payload=corpo,
                cabecalhos={"Authorization": "Bearer ***", "Content-Type": "application/json",
                            "Idempotency-Key": chave, "alvo": "POST /api/recipes"},
            )
        try:
            resp, ids = self._requisitar(
                "POST", "/api/recipes", token=token, corpo=corpo, chave=chave
            )
        except ErroDeRede as exc:
            raise ErroDeRede(
                "resultado do envio incerto; a mesma chave idempotente pode ser reenviada",
                codigo="legacy_outcome_uncertain",
                request_id=exc.request_id,
            ) from None
        self._levantar(resp, ids)
        try:
            dados = resp.json()
        except Exception:
            raise ErroSite(
                "resposta de criação sem JSON válido", http_status=resp.status_code, request_id=ids[-1]
            ) from None
        if not isinstance(dados, dict) or dados.get("id") is None or not dados.get("slug"):
            raise ErroSite(
                "resposta de criação sem identificador e slug", http_status=resp.status_code, request_id=ids[-1]
            )
        if dados.get("status") != validado.status:
            raise ErroSite(
                f"API não confirmou status {validado.status}", http_status=resp.status_code, request_id=ids[-1]
            )
        replay = resp.headers.get("idempotent-replay", "").lower() == "true"
        return RespostaCriacao(
            "repetido" if replay else "criado", resp.status_code, dados.get("id"), dados.get("slug"),
            dados.get("status"), dados.get("url"), ids, len(ids),
        )

    def _criar(self, caminho, content_type, modelo, payload, run_id, reduzir) -> RespostaCriacao:
        try:
            validado = payload if isinstance(payload, modelo) else modelo.model_validate(payload)
        except ValidationError as exc:
            raise ContratoInvalido([{"campo": ".".join(map(str, e["loc"])), "detalhe": e["msg"]} for e in exc.errors()]) from None
        corpo = validado.model_dump(mode="json", exclude_none=True)
        topic_slug = validado.generationMeta.topic_slug
        token = self._token_para(validado.status)  # falha antes de qualquer rede
        chave = chave_idempotencia(content_type, topic_slug, run_id)

        if self.dry_run:
            return RespostaCriacao(
                "dry_run", payload=corpo,
                cabecalhos={"Authorization": "Bearer ***", "Content-Type": "application/json",
                            "Idempotency-Key": chave, "X-Contract-Version": self.contract_version,
                            "X-Request-Id": "<gerado a cada requisição>", "alvo": f"POST {caminho}"},
            )

        todos_ids: list[str] = []
        reduzido = False
        while True:
            resp, ids = self._requisitar("POST", caminho, token=token, corpo=corpo, chave=chave)
            todos_ids += ids
            if resp.status_code == 413 and reduzir is not None and not reduzido:
                corpo = reduzir(dict(corpo))  # "reduz o conteúdo e reenvia uma vez" (06 §11)
                reduzido = True
                continue
            break

        if resp.status_code == 409:
            return self._confirmar_apos_409(content_type, topic_slug, run_id, todos_ids, resp)
        self._levantar(resp, todos_ids)
        try:
            dados = resp.json()
        except Exception:
            raise ErroSite("resposta de criação sem JSON válido", http_status=resp.status_code, request_id=todos_ids[-1]) from None
        if (
            not isinstance(dados, dict)
            or dados.get("id") is None
            or not isinstance(dados.get("slug"), str)
            or dados.get("status") != validado.status
        ):
            raise ErroSite(
                "resposta de criação fora do contrato v1",
                http_status=resp.status_code,
                request_id=todos_ids[-1],
            )

        replay = resp.headers.get("idempotent-replay", "").lower() == "true"
        return RespostaCriacao(
            "repetido" if replay else "criado", resp.status_code, dados.get("id"), dados.get("slug"),
            dados.get("status"), dados.get("url"), todos_ids, len(todos_ids),
        )

    def _confirmar_apos_409(self, content_type, topic_slug, run_id, ids, resp_409) -> RespostaCriacao:
        """docs/06 §10 item 3: compara generation_meta.run_id; nunca reenvia nem muda o título."""
        codigo, msg, det = self._erro_do_corpo(resp_409)
        itens = self.lookup(topic_slug=topic_slug)
        if not itens:
            raise ConflitoDeSlug(msg or "slug já existe em outro conteúdo", codigo=codigo or "slug_conflict",
                                 http_status=409, detalhes=det, request_id=ids[-1])
        for item in itens:
            meta = item.get("generation_meta") or item.get("generationMeta") or {}
            if meta.get("run_id") == run_id:
                return RespostaCriacao("confirmado_apos_409", 409, item.get("id"), item.get("slug"),
                                       item.get("status"), item.get("url"), ids, len(ids))
        primeiro = itens[0]
        return RespostaCriacao("duplicada", 409, primeiro.get("id"), primeiro.get("slug"),
                               primeiro.get("status"), primeiro.get("url"), ids, len(ids))

    # ---- leitura (docs/06 §9) ----------------------------------------------------------

    def _ler(self, caminho: str, params: Optional[dict] = None) -> Any:
        resp, ids = self._requisitar("GET", caminho, token=self._token_leitura(), params=params)
        self._levantar(resp, ids)
        try:
            return resp.json()
        except Exception:
            raise ErroSite("resposta de leitura sem JSON válido", http_status=resp.status_code, request_id=ids[-1]) from None

    def taxonomia(self) -> Any:
        return self._ler("/api/taxonomy")

    def catalogo_ingredientes(self) -> Any:
        return self._ler("/api/catalog/ingredients")

    def cobertura(self) -> Any:
        return self._ler("/api/coverage")

    def lookup(self, *, topic_slug: Optional[str] = None, slug: Optional[str] = None, title: Optional[str] = None) -> list[dict]:
        params = {k: v for k, v in (("topic_slug", topic_slug), ("slug", slug), ("title", title)) if v}
        if not params:
            raise ValueError("informe topic_slug, slug ou title")
        dados = self._ler("/api/content/lookup", params)
        itens = dados.get("items", []) if isinstance(dados, dict) else dados
        return [i for i in itens if isinstance(i, dict)]

    def status_receita(self, slug: str) -> dict:
        dados = self._ler(f"/api/recipes/{slug}/status")
        return dados if isinstance(dados, dict) else {}

    def aguardar_estado(self, slug: str, *, tentativas: int = 10, intervalo: float = 5.0) -> dict:
        """Consulta o estado enquanto for 'processing' (docs/06 §2 e §7.3). Devolve o último estado visto."""
        estado: dict = {}
        for i in range(max(1, tentativas)):
            estado = self.status_receita(slug)
            if estado.get("status") != "processing":
                return estado
            if i < tentativas - 1:
                self._espera(intervalo)
        return estado
