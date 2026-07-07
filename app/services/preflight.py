"""
preflight.py -- Pipeline de pre-filtrado antes del LLM.

Gates puros y sin estado: reciben un EmailData (+ contexto) y devuelven un
PreflightResult. Los efectos de BD (auto-alta de lender, escritura de reviews)
los hace la capa de integracion en llm_classifier.py, no estos gates.

Orden de evaluacion (v2):
  1. blacklist        -> dominio NO_APROBADO: DESCARTADO directo.
  2. dedup            -> solo el ULTIMO correo del hilo clasifica; los
                         anteriores: DESCARTADO.
  3. lender           -> remitente de dominio APROBADO pasa. Reenvios /
                         internos pasan SOLO si mencionan un lender aprobado
                         (dominio o alias en subject/body); si no: DESCARTADO.
                         Dominios directos nuevos conservan el flujo de
                         aprobacion (review PENDIENTE).
  4. security         -> contenido bloqueado/cifrado: review PENDIENTE.

Cada rechazo lleva `disposition`: "DESCARTADO" (terminal, sin revision humana)
o "PENDIENTE" (cola de revision).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.schemas import EmailData

DISPOSITION_PENDIENTE = "PENDIENTE"
DISPOSITION_DESCARTADO = "DESCARTADO"


@dataclass
class PreflightResult:
    passed: bool
    stage: Optional[str] = None
    reason: str = ""
    detected_original_sender: Optional[str] = None
    disposition: str = DISPOSITION_PENDIENTE


def _sender_domain(email: EmailData) -> str:
    return (email.sender_domain or "").lower()


def _domain_status(email: EmailData, kb: dict[str, Any]) -> Optional[str]:
    return kb["domain_status"].get(_sender_domain(email))


def _infer_lender_name(domain: str) -> str:
    base = (domain or "").split(".")[0]
    return base.capitalize()


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def gate_blacklist(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    domain = _sender_domain(email)
    if _domain_status(email, kb) == "NO_APROBADO":
        lender = kb.get("domain_name", {}).get(domain, domain)
        reason = f"Lender/domain in blacklist (NOT APPROVED): {lender} <{domain}>"
        return PreflightResult(False, "blacklist", reason,
                               disposition=DISPOSITION_DESCARTADO)
    return None


_FORWARD_SUBJECT = re.compile(r"^\s*(fw|fwd|rv|enc)\s*:", re.IGNORECASE)
_ORIGINAL_SENDER = re.compile(
    r"(?im)^(?:de|from)\s*:\s*.*?([\w.\-+%]+@[\w.\-]+\.\w+)"
)
_EMAIL_ADDR = re.compile(r"[\w.\-+%]+@([\w.\-]+\.\w+)")


def _is_forward(email: EmailData) -> bool:
    if _FORWARD_SUBJECT.search(email.subject or ""):
        return True
    return bool(_ORIGINAL_SENDER.search(email.body_text or ""))


def _extract_original_sender(body: str | None) -> Optional[str]:
    m = _ORIGINAL_SENDER.search(body or "")
    return m.group(1).lower() if m else None


def mentioned_lender(email: EmailData, kb: dict[str, Any]) -> Optional[str]:
    """Lender aprobado mencionado en el correo (subject + body).

    Dos senales, de mas fuerte a mas debil:
      1. Direccion de correo con dominio APROBADO citada en el texto
         (cabeceras reenviadas, firmas). kb["domain_map"] solo contiene
         dominios APROBADO.
      2. Nombre del lender o alias (de la matriz de waivers) como palabra
         completa en el texto normalizado.
    """
    raw = f"{email.subject or ''} {email.body_text or ''}"
    domain_map = kb.get("domain_map", {})
    internal = set(settings.internal_domains)
    for match in _EMAIL_ADDR.finditer(raw):
        domain = match.group(1).lower()
        if domain in domain_map and domain not in internal:
            return domain_map[domain]

    text = _normalize(raw)
    if not text:
        return None
    for entry in kb.get("entries", []):
        candidates = [entry.get("lender"), *entry.get("lender_aliases", [])]
        for candidate in candidates:
            cand = _normalize(candidate)
            if len(cand) < 3:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(cand)}(?![a-z0-9])", text):
                return entry["lender"]
    return None


def gate_lender(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    """Identidad del lender: aprobado directo pasa; reenvio/interno pasa solo
    con mencion de lender aprobado; dominio directo nuevo va a aprobacion."""
    domain = _sender_domain(email)
    status = _domain_status(email, kb)
    internal = domain in settings.internal_domains

    if status == "APROBADO" and not internal:
        return None

    if internal or _is_forward(email):
        lender = mentioned_lender(email, kb)
        if lender:
            return None  # menciona lender aprobado -> continua clasificacion
        orig = _extract_original_sender(email.body_text)
        origin = "internal" if internal else "forwarded"
        reason = (
            f"No approved lender mentioned: the email is {origin} and neither an "
            "approved lender domain nor a known lender name/alias appears in the "
            "subject or body, so there is no lender to classify against."
        )
        return PreflightResult(False, "sin_lender", reason,
                               detected_original_sender=orig,
                               disposition=DISPOSITION_DESCARTADO)

    # Correo directo de un dominio no aprobado: flujo de aprobacion de lenders.
    if status == "POR_APROBAR":
        return PreflightResult(False, "lender_por_aprobar",
                               f"Domain pending approval: {domain}")
    return PreflightResult(False, "lender_nuevo",
                           f"New domain, requires approval: {domain}")


def _is_body_blocked(email: EmailData) -> bool:
    body = (email.body_text or "").strip()
    if len(body) < settings.security_min_body_len:
        return True
    low = body.lower()
    return any(marker in low for marker in settings.security_block_markers)


def gate_security(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    if _is_body_blocked(email):
        return PreflightResult(False, "seguridad_bloqueo",
                               "Contenido bloqueado o incompleto (cifrado/truncado).")
    return None


_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _sort_key(e: EmailData):
    # received_date puede ser None; los nulos pierden. Desempate por message_id.
    dt = e.received_date
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt is not None, dt or _EPOCH, e.message_id or "")


def _is_primary(email: EmailData, group: list[EmailData]) -> bool:
    """Primario = el correo MAS RECIENTE del hilo (v2: antes era el primero)."""
    if not group:
        return True
    primary = max(group, key=_sort_key)
    return (email.message_id or "") == (primary.message_id or "")


def gate_dedup(email: EmailData, group: list[EmailData]) -> Optional[PreflightResult]:
    if _is_primary(email, group):
        return None
    return PreflightResult(
        False, "duplicado",
        "Superseded: a newer email exists in this conversation; only the latest "
        "email of a thread is classified.",
        disposition=DISPOSITION_DESCARTADO,
    )


def evaluate(email: EmailData, kb: dict[str, Any], group: list[EmailData]) -> PreflightResult:
    for gate in (
        lambda: gate_blacklist(email, kb),
        lambda: gate_dedup(email, group),
        lambda: gate_lender(email, kb),
        lambda: gate_security(email, kb),
    ):
        result = gate()
        if result is not None:
            return result
    return PreflightResult(True)
