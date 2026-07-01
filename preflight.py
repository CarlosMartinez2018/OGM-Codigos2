"""
preflight.py -- Pipeline de pre-filtrado antes del LLM.

Gates puros y sin estado: reciben un EmailData (+ contexto) y devuelven un
PreflightResult. Los efectos de BD (auto-alta de lender, escritura de reviews)
los hace la capa de integracion en llm_classifier.py, no estos gates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from config import settings
from schemas import EmailData


@dataclass
class PreflightResult:
    passed: bool
    stage: Optional[str] = None
    reason: str = ""
    detected_original_sender: Optional[str] = None


def _sender_domain(email: EmailData) -> str:
    return (email.sender_domain or "").lower()


def _domain_status(email: EmailData, kb: dict[str, Any]) -> Optional[str]:
    return kb["domain_status"].get(_sender_domain(email))


def _infer_lender_name(domain: str) -> str:
    base = (domain or "").split(".")[0]
    return base.capitalize()


def gate_blacklist(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    domain = _sender_domain(email)
    if _domain_status(email, kb) == "NO_APROBADO":
        lender = kb.get("domain_name", {}).get(domain, domain)
        reason = f"Lender/dominio en blacklist (NO_APROBADO): {lender} <{domain}>"
        return PreflightResult(False, "blacklist", reason)
    return None


def gate_domain(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    domain = _sender_domain(email)
    if domain in settings.internal_domains:
        return None  # remitente interno: lo maneja el gate de hilos
    status = _domain_status(email, kb)
    if status == "APROBADO":
        return None
    if status == "POR_APROBAR":
        return PreflightResult(False, "lender_por_aprobar",
                               f"Dominio pendiente de aprobacion: {domain}")
    # No esta en el mapa -> nuevo lender por aprobar
    return PreflightResult(False, "lender_nuevo",
                           f"Dominio nuevo, requiere aprobacion: {domain}")


_FORWARD_SUBJECT = re.compile(r"^\s*(fw|fwd|rv|enc)\s*:", re.IGNORECASE)
_ORIGINAL_SENDER = re.compile(
    r"(?im)^(?:de|from)\s*:\s*.*?([\w.\-+%]+@[\w.\-]+\.\w+)"
)


def _is_forward(email: EmailData) -> bool:
    if _FORWARD_SUBJECT.search(email.subject or ""):
        return True
    return bool(_ORIGINAL_SENDER.search(email.body_text or ""))


def _extract_original_sender(body: str | None) -> Optional[str]:
    m = _ORIGINAL_SENDER.search(body or "")
    return m.group(1).lower() if m else None


def gate_threads(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    # Un correo directo de un lender aprobado es un hilo valido.
    if _domain_status(email, kb) == "APROBADO":
        return None
    # Remitente interno / no-lender que llego hasta aca -> revision.
    orig = _extract_original_sender(email.body_text)
    if _is_forward(email):
        reason = "Reenvio: la solicitud no llega directa del lender al buzon."
        return PreflightResult(False, "reenvio", reason, detected_original_sender=orig)
    reason = "Hilo sin origen de lender en el buzon."
    return PreflightResult(False, "hilo_incompleto", reason, detected_original_sender=orig)
