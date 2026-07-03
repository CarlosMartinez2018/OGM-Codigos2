"""
doc_normalize.py -- Normaliza nombres de documentos esperados a filas atomicas.

Reglas (pedidas por negocio):
- "ACORD 25 + ACORD 101"   -> ["ACORD 25", "ACORD 101"]
- "ACORD 25/28"            -> ["ACORD 25", "ACORD 28"]
- "ACORD 25 + 28 + 101"    -> ["ACORD 25", "ACORD 28", "ACORD 101"]
Cada ACORD queda en su propia fila. El "+" separa documentos. Las listas de
numeros ACORD (separadas por / , o 'and') se expanden con el prefijo "ACORD".
NO se parte "/" fuera de contexto ACORD (p.ej. "GL/Umbrella" se conserva).
"""
from __future__ import annotations

import re

_ACORD_HEAD = re.compile(r"^ACORD\b\s*(.*)$", re.IGNORECASE)
_BARE_NUMS = re.compile(r"^[\d/,\s]+(?:and[\d/,\s]+)*$", re.IGNORECASE)
# Encuentra "ACORD <numeros>" DENTRO de una frase (mid-string), con listas /,.
_ACORD_IN = re.compile(
    r"ACORD\s+(\d+(?:\s*\([^)]*\))?(?:\s*[/,]\s*\d+(?:\s*\([^)]*\))?)*)",
    re.IGNORECASE,
)


def _strip(s: str) -> str:
    return s.strip().strip(".,;").strip()


def _expand_acord(rest: str) -> list[str]:
    tokens = re.split(r"\s*[/,]\s*|\s+and\s+", rest, flags=re.IGNORECASE)
    out = [f"ACORD {t.strip()}" for t in tokens if t.strip()]
    return out or ["ACORD"]


def split_document(raw: str | None) -> list[str]:
    """Convierte un texto de documento(s) en una lista de documentos atomicos."""
    raw = (raw or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s*\+\s*", raw)
    out: list[str] = []
    acord_mode = False
    for p in parts:
        p = _strip(p)
        if not p:
            continue
        # ACORD embebido en la frase (p.ej. "Bundle ACORD 25/28 with every invoice"):
        # emite solo los ACORD y descarta el texto descriptivo alrededor.
        acord_hits = _ACORD_IN.findall(p)
        if acord_hits:
            acord_mode = True
            for grp in acord_hits:
                out.extend(_expand_acord(grp))
            continue
        if acord_mode and _BARE_NUMS.match(p):
            out.extend(_expand_acord(p))
            continue
        acord_mode = False
        out.append(p)
    # dedup preservando orden (case-insensitive)
    seen: set[str] = set()
    res: list[str] = []
    for d in out:
        k = d.lower()
        if k not in seen:
            seen.add(k)
            res.append(d)
    return res


def normalize_documents(docs: list[str]) -> list[str]:
    """Aplica split_document a una lista y aplana + dedup preservando orden."""
    out: list[str] = []
    seen: set[str] = set()
    for d in docs:
        for atom in split_document(d):
            k = atom.lower()
            if k not in seen:
                seen.add(k)
                out.append(atom)
    return out
