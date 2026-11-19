from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from agents.editor import Falha

_ROOT = Path(__file__).resolve().parents[1]
_BLOCKED = re.compile(
    r"\b(?:marca|modelo|loja|pre[cç]o|lucro|faturamento|garantido|infal[ií]vel|cura|emagrece|detox|testamos|testada)\b",
    re.IGNORECASE,
)
_SAFETY = re.compile(
    r"\b(?:conserva[cç][aã]o|seguran[cç]a|temperatura|validade|armazenar|armazenamento)\b",
    re.IGNORECASE,
)
_WORDS = re.compile(r"[a-záéíóúàâêôãõç0-9]+", re.IGNORECASE)


def _words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _WORDS.findall(normalized)


class ValidadorDica:
    ids_cobertos = frozenset({"SCH-01", "SCH-02", "SCH-03", "SCH-04", "HON-01", "SIM-01"})

    def validar(self, conteudo: dict, contexto: dict) -> list[Falha]:
        failures: list[Falha] = []
        body = conteudo.get("corpo", "")
        title = conteudo.get("titulo", "")
        excerpt = conteudo.get("descricao_curta", "")
        if not isinstance(body, str) or not 150 <= len(body.split()) <= 400:
            failures.append(Falha("SCH-03", "o corpo deve ter de 150 a 400 palavras", campo="corpo"))
        if not isinstance(body, str) or re.search(r"<\s*\/?\s*[a-z][^>]*>", body, re.IGNORECASE):
            failures.append(Falha("SCH-05", "HTML não é permitido no corpo", campo="corpo"))
        if any(_BLOCKED.search(value) for value in (body, title, excerpt) if isinstance(value, str)):
            failures.append(Falha("HON-01", "alegação comercial ou de saúde proibida"))

        ficha = contexto.get("ficha") or {}
        references = ficha.get("referencias_registro", [])
        domains = {
            str(item.get("dominio", "")).lower()
            for item in references if isinstance(item, dict) and item.get("dominio")
        }
        if len(domains) < 2:
            failures.append(Falha("GATE-DICA-01", "são necessárias fontes em dois domínios distintos"))
        if _SAFETY.search(f"{title} {excerpt} {body}") and int(ficha.get("fontes_tecnicas", 0) or 0) < 1:
            failures.append(Falha("GATE-DICA-02", "segurança/conservação exige fonte técnica aprovada"))

        forbidden = _ROOT / "config" / "frases_proibidas.json"
        if forbidden.exists():
            items = json.loads(forbidden.read_text(encoding="utf-8")).get("itens", [])
            text = f"{title}\n{excerpt}\n{body}".casefold()
            for item in items:
                term = item.get("termo", "") if isinstance(item, dict) else str(item)
                if term and term.casefold() in text:
                    failures.append(Falha("HON-01", "frase proibida", campo="corpo"))
                    break

        body_words = _words(f"{title}\n{excerpt}\n{body}")
        shingles = {
            tuple(body_words[index:index + 10])
            for index in range(max(0, len(body_words) - 9))
        }
        for source in contexto.get("fontes_texto", []):
            source_words = _words(source if isinstance(source, str) else "")
            if any(
                tuple(source_words[index:index + 10]) in shingles
                for index in range(max(0, len(source_words) - 9))
            ):
                failures.append(Falha("SIM-01", "sequência idêntica de 10 palavras à fonte"))
                break
        return failures
