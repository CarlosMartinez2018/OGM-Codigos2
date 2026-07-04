"""
llm_classifier.py -- Clasificador hibrido para correos en production_emails.

El flujo usa reglas de negocio como fuente de verdad:
  - domain_lender_map para identificar y validar lenders.
  - lender_waiver_matrix para detectar waivers, triggers y documentos.
  - training_emails como ejemplos historicos para contexto del LLM.

El LLM es opcional. Si USE_LLM_CLASSIFIER=false, el clasificador funciona
solo con reglas deterministicas y aun genera respuesta sugerida.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import httpx
from app.services import preflight
from rich.console import Console
from rich.table import Table
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import business_context as bc
from app.core.config import settings
from app.services import feedback_context
from app.db.database import async_session, engine, init_db
from app.db.models import (
    DomainLenderMap,
    EmailClassification,
    EmailReview,
    LenderWaiverDocument,
    LenderWaiverMatrix,
    ProductionEmail,
    TrainingEmail,
)
from app.schemas import ClassificationResult, EmailData

logger = logging.getLogger(__name__)
console = Console()

INTERNAL_DOMAINS = {"acentopartners.com", "captiveadvisorypartners.com"}

# --- Cableado a business_context.json --------------------------------------
# Estas listas y la taxonomia de categorias vienen del activo de negocio
# (data/business_context.json). Se cargan una vez al importar el modulo con
# fallback a valores minimos si el JSON no esta. Escalar de mas es seguro
# (lo revisa un humano); escalar de menos no lo es -> unimos criticos+elevados.

# Prioridad de evaluacion de categorias: riesgo primero, luego la mas comun.
_CATEGORY_PRIORITY = [
    "COVENANT_BREACH", "WAIVER_REQUEST", "LENDER_ALERT",
    "LENDER_COMPLIANCE", "OPERATIONAL_WAIVER",
]

_FALLBACK_INJECTION = [
    "ignore previous instructions", "forget your instructions",
    "system prompt", "developer message", "you are now", "new role",
    "override", "jailbreak",
]
_FALLBACK_CRITICAL = [
    "legal action", "default", "cancellation", "cancel", "penalty",
    "past due", "overdue", "non-compliance", "noncompliance",
    "final notice", "deadline", "urgent", "termination",
]
_FALLBACK_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("COVENANT_BREACH", ["covenant", "breach", "event of default"]),
    ("LENDER_ALERT", ["urgent", "final notice", "past due", "overdue"]),
    ("LENDER_COMPLIANCE", ["non-compliance", "noncompliance", "compliance",
                           "deficiency", "notice", "required"]),
    ("WAIVER_REQUEST", ["waiver", "request"]),
]


def _build_injection_patterns() -> list[str]:
    bc_patterns = [p.lower() for p in bc.injection_patterns() if p]
    # Union preservando orden; los del JSON son mas ricos.
    seen: set[str] = set()
    out: list[str] = []
    for p in bc_patterns + _FALLBACK_INJECTION:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _build_critical_keywords() -> list[str]:
    esc = bc.load_business_context().get("risk_escalation", {})
    kws = [k.lower() for k in esc.get("critical_keywords", [])]
    kws += [k.lower() for k in esc.get("elevated_keywords", [])]
    kws += _FALLBACK_CRITICAL
    seen: set[str] = set()
    return [k for k in kws if not (k in seen or seen.add(k))]


def _build_category_keywords() -> list[tuple[str, list[str]]]:
    cats = {c["id"]: c for c in bc.communication_categories() if c.get("id")}
    if not cats:
        return _FALLBACK_CATEGORY_KEYWORDS
    ordered: list[tuple[str, list[str]]] = []
    ids = _CATEGORY_PRIORITY + [cid for cid in cats if cid not in _CATEGORY_PRIORITY]
    for cid in ids:
        c = cats.get(cid)
        if c:
            ordered.append((cid, [s.lower() for s in c.get("trigger_signals", [])]))
    return ordered


def _build_escalation_categories() -> set[str]:
    return {
        c["id"] for c in bc.communication_categories()
        if c.get("id") and (c.get("escalate_for_review") or c.get("human_review_required"))
    }


PROMPT_INJECTION_PATTERNS = _build_injection_patterns()
_CRITICAL_KEYWORDS = _build_critical_keywords()
_CATEGORY_KEYWORDS = _build_category_keywords()
_ESCALATION_CATEGORIES = _build_escalation_categories()

_TOKEN_STOPWORDS = {"and", "or", "the", "of", "for", "to", "a", "de", "la", "el", "y"}


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _communication_category(subject: str, body: str) -> str:
    """Clasifica la naturaleza del correo por trigger_signals (prioridad por orden)."""
    text = _normalize(f"{subject} {body}")
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in text for kw in keywords):
            return category
    return "OPERATIONAL_WAIVER"


def _should_escalate(subject: str, body: str, injection: bool,
                     category: str | None = None) -> bool:
    """True cuando hay inyeccion, riesgo critico o categoria de revision -> humano."""
    if injection:
        return True
    if category and category in _ESCALATION_CATEGORIES:
        return True
    text = _normalize(f"{subject} {body}")
    return any(kw in text for kw in _CRITICAL_KEYWORDS)


def _overlap_tokens(name: str, haystack: str) -> int:
    tokens = [t for t in re.findall(r"[a-z0-9]+", _normalize(name))
              if len(t) > 2 and t not in _TOKEN_STOPWORDS]
    return sum(1 for t in tokens if t in haystack)


def _secondary_issues(email: EmailData, lender: str, primary_waiver: str,
                      kb: dict[str, Any]) -> list[str]:
    """Waivers adicionales del mismo lender presentes en el correo (excluye el primario)."""
    if lender == "UNKNOWN":
        return []
    entries = kb.get("by_lender", {}).get(lender) or []
    haystack = _normalize(f"{email.subject} {email.body_text}")
    out: list[str] = []
    for entry in entries:
        waiver = entry["waiver_type"]
        if waiver == primary_waiver or waiver in out:
            continue
        name = _normalize(waiver)
        if (name and name in haystack) or _overlap_tokens(waiver, haystack) >= 2:
            out.append(waiver)
    return out


def _find_attachments(lender: str, base_path: str) -> list[str]:
    """Busca PDFs bajo base_path en carpetas cuyo path contiene el nombre del lender."""
    if not lender or not base_path:
        return []
    root = Path(base_path)
    if not root.exists():
        return []
    lender_lower = lender.lower()
    found: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        if lender_lower in dirpath.lower():
            for f in files:
                if f.lower().endswith(".pdf"):
                    found.append(os.path.join(dirpath, f))
    return found


def _sender_email(sender: str | None) -> str:
    if not sender:
        return ""
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).strip().lower()
    match = re.search(r"[\w.\-+%]+@[\w.\-]+\.\w+", sender)
    return match.group(0).lower() if match else sender.strip().lower()


def _domain_from_email(value: str | None) -> str:
    email = _sender_email(value)
    return email.split("@", 1)[1].lower() if "@" in email else ""


def _domains(values: list[str] | None) -> list[str]:
    seen: list[str] = []
    for value in values or []:
        domain = _domain_from_email(value)
        if domain and domain not in seen:
            seen.append(domain)
    return seen


def _split_triggers(raw: str | None) -> list[str]:
    if not raw:
        return []
    pieces = re.split(r"[,;\n\r|]+", raw)
    triggers = []
    for piece in pieces:
        cleaned = piece.strip(" -:\t").strip()
        if len(cleaned) >= 3:
            triggers.append(cleaned)
    return triggers


def _confidence_level(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


class EmailClassifier:
    """Clasifica production_emails combinando reglas y LLM opcional."""

    async def classify_production_email(
        self,
        production_email: ProductionEmail,
        session: AsyncSession,
        kb: dict[str, Any] | None = None,
        training_rows: list[TrainingEmail] | None = None,
    ) -> ClassificationResult:
        email = self._production_to_email_data(production_email)
        return await self.classify(email, session, kb=kb, training_rows=training_rows)

    async def classify(
        self,
        email: EmailData,
        session: AsyncSession,
        kb: dict[str, Any] | None = None,
        training_rows: list[TrainingEmail] | None = None,
    ) -> ClassificationResult:
        if kb is None:
            kb = await self._load_business_data(session)

        lender, lender_evidence = self._identify_lender(email, kb)
        waiver_entry, waiver_evidence = self._identify_waiver(email, lender, kb)

        validation = self._validate(email, lender, waiver_entry, lender_evidence, waiver_evidence, kb)
        result = self._build_rule_result(email, lender, waiver_entry, validation)

        # La validacion de reglas de negocio se aplica SIEMPRE (con o sin LLM).
        result = self._enforce_validation(result, kb)

        # El LLM solo aporta cuando hay un lender valido con waivers configurados;
        # para correos internos/ruido/UNKNOWN se salta (evita llamadas inutiles y lentas).
        if settings.use_llm_classifier and self._llm_is_useful(result, kb):
            result = await self._enhance_with_llm(email, result, kb)
            result = self._enforce_validation(result, kb)

        # Features derivadas del lender/waiver finales (post-validacion).
        result.secondary_issues = _secondary_issues(email, result.lender, result.waiver_type, kb)
        result.suggested_attachments = _find_attachments(result.lender, settings.document_base_path)

        return result

    def _llm_is_useful(self, result: ClassificationResult, kb: dict[str, Any]) -> bool:
        if result.lender == "UNKNOWN":
            return False
        return bool(kb["by_lender"].get(result.lender))

    async def classify_pending_production_emails(
        self,
        session: AsyncSession,
        limit: int = 100,
        reclassify: bool = False,
    ) -> list[tuple[ProductionEmail, ClassificationResult]]:
        stmt = select(ProductionEmail).order_by(ProductionEmail.received_date.desc().nullslast())
        if limit > 0:
            stmt = stmt.limit(limit)
        emails = (await session.scalars(stmt)).all()

        # Cargar conocimiento de negocio una sola vez por lote.
        kb = await self._load_business_data(session)

        # Agrupar por case_id (conversation_id) para el gate de dedup.
        groups: dict[str, list[EmailData]] = defaultdict(list)
        email_data_by_id: dict[int, EmailData] = {}
        for pe in emails:
            ed = self._production_to_email_data(pe)
            email_data_by_id[pe.id] = ed
            groups[pe.case_id or pe.conversation_id or ed.conversation_id].append(ed)

        results: list[tuple[ProductionEmail, ClassificationResult]] = []
        for production_email in emails:
            if not reclassify:
                existing = await session.scalar(
                    select(EmailClassification.id)
                    .where(EmailClassification.message_id == production_email.message_id)
                    .limit(1)
                )
                if existing:
                    continue

            email = email_data_by_id[production_email.id]
            case_id = production_email.case_id or production_email.conversation_id or email.conversation_id
            pre = preflight.evaluate(email, kb, groups[case_id])
            if not pre.passed:
                if pre.stage == "lender_nuevo":
                    await self._ensure_pending_lender(session, email.sender_domain)
                await self._save_review(session, production_email, pre, case_id)
                await self._delete_classification(session, production_email.message_id)
                continue

            result = await self.classify(email, session, kb=kb)
            await self.save_classification(session, production_email, result)
            await self._resolve_reviews(session, production_email.message_id)
            results.append((production_email, result))

        await session.commit()
        return results

    async def save_classification(
        self,
        session: AsyncSession,
        production_email: ProductionEmail,
        result: ClassificationResult,
    ) -> None:
        stmt = pg_insert(EmailClassification).values(
            production_email_id=production_email.id,
            message_id=production_email.message_id,
            lender=result.lender,
            waiver_type=result.waiver_type,
            confidence_score=result.confidence_score,
            confidence_level=result.confidence_level,
            trigger_description=result.trigger_description,
            suggested_response=result.suggested_response,
            documents_expected=result.documents_expected,
            validation_details=result.validation_details,
            raw_llm_response=result.raw_llm_response,
            secondary_issues=result.secondary_issues,
            communication_category=result.communication_category,
            escalate_for_review=result.escalate_for_review,
            suggested_attachments=result.suggested_attachments,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "production_email_id": stmt.excluded.production_email_id,
                "lender": stmt.excluded.lender,
                "waiver_type": stmt.excluded.waiver_type,
                "confidence_score": stmt.excluded.confidence_score,
                "confidence_level": stmt.excluded.confidence_level,
                "trigger_description": stmt.excluded.trigger_description,
                "suggested_response": stmt.excluded.suggested_response,
                "documents_expected": stmt.excluded.documents_expected,
                "validation_details": stmt.excluded.validation_details,
                "raw_llm_response": stmt.excluded.raw_llm_response,
                "secondary_issues": stmt.excluded.secondary_issues,
                "communication_category": stmt.excluded.communication_category,
                "escalate_for_review": stmt.excluded.escalate_for_review,
                "suggested_attachments": stmt.excluded.suggested_attachments,
            },
        )
        await session.execute(stmt)

    async def _ensure_pending_lender(self, session: AsyncSession, domain: str) -> None:
        domain = (domain or "").lower()
        if not domain:
            return
        stmt = pg_insert(DomainLenderMap).values(
            domain=domain,
            lender_name=preflight._infer_lender_name(domain),
            status="POR_APROBAR",
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["domain"])
        await session.execute(stmt)

    async def _resolve_reviews(self, session: AsyncSession, message_id: str) -> None:
        """Marca GESTIONADO cualquier review PENDIENTE de un correo ya clasificado."""
        await session.execute(
            update(EmailReview)
            .where(EmailReview.message_id == message_id)
            .where(EmailReview.status == "PENDIENTE")
            .values(status="GESTIONADO", resolved_at=datetime.now(timezone.utc))
        )

    async def _delete_classification(self, session: AsyncSession, message_id: str) -> None:
        await session.execute(
            delete(EmailClassification).where(EmailClassification.message_id == message_id)
        )

    async def _save_review(
        self,
        session: AsyncSession,
        production_email: ProductionEmail,
        result: "preflight.PreflightResult",
        case_id: str,
    ) -> None:
        stmt = pg_insert(EmailReview).values(
            production_email_id=production_email.id,
            message_id=production_email.message_id,
            conversation_id=production_email.conversation_id or "",
            case_id=case_id,
            stage=result.stage,
            reason=result.reason,
            detected_original_sender=result.detected_original_sender,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id", "stage"],
            set_={
                "reason": stmt.excluded.reason,
                "detected_original_sender": stmt.excluded.detected_original_sender,
                "case_id": stmt.excluded.case_id,
            },
        )
        await session.execute(stmt)

    async def _load_business_data(self, session: AsyncSession) -> dict[str, Any]:
        domain_rows = (await session.scalars(select(DomainLenderMap))).all()
        matrix_rows = (await session.scalars(select(LenderWaiverMatrix))).all()
        document_rows = (
            await session.scalars(
                select(LenderWaiverDocument).order_by(LenderWaiverDocument.position)
            )
        ).all()

        domain_map = {}
        domain_status = {}
        domain_name = {}
        for row in domain_rows:
            d = row.domain.lower()
            domain_status[d] = row.status
            domain_name[d] = row.lender_name
            if row.status == "APROBADO":
                domain_map[d] = row.lender_name
        authorized_lenders = set(domain_map.values())

        docs_by_matrix_id: dict[int, list[str]] = {}
        for doc in document_rows:
            docs_by_matrix_id.setdefault(doc.lender_waiver_id, []).append(doc.document_name)

        entries = []
        for row in matrix_rows:
            entry = {
                "id": row.id,
                "lender": row.lender,
                "lender_aliases": row.lender_aliases or [],
                "waiver_type": row.waiver_type,
                "triggers": row.triggers or "",
                "trigger_list": _split_triggers(row.triggers),
                "evidence_required_ops": row.evidence_required_ops or "",
                "evidence_required_insurance": row.evidence_required_insurance or "",
                "documents_expected": docs_by_matrix_id.get(row.id, []),
                "actions_to_automate": row.actions_to_automate or "",
                "waiver_pack": row.waiver_pack or "",
            }
            entries.append(entry)
            authorized_lenders.add(row.lender)

        by_lender: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            by_lender.setdefault(entry["lender"], []).append(entry)

        return {
            "domain_map": domain_map,
            "authorized_lenders": authorized_lenders,
            "entries": entries,
            "by_lender": by_lender,
            "domain_status": domain_status,
            "domain_name": domain_name,
        }

    async def _load_training_examples(
        self,
        session: AsyncSession,
        email: EmailData,
        limit: int = 5,
        rows: list[TrainingEmail] | None = None,
    ) -> list[dict[str, str]]:
        text = _normalize(f"{email.subject} {email.body_text[:1000]}")
        if rows is None:
            rows = (await session.scalars(select(TrainingEmail).limit(200))).all()
        scored = []
        for row in rows:
            candidate = _normalize(f"{row.subject} {row.body_text[:1000]}")
            score = _similarity(text[:1000], candidate[:1000])
            if row.sender_domain and row.sender_domain == email.sender_domain:
                score += 0.15
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        examples = []
        for score, row in scored[:limit]:
            examples.append({
                "subject": row.subject or "",
                "sender_domain": row.sender_domain or "",
                "body_preview": row.body_preview or (row.body_text or "")[:250],
                "similarity": f"{score:.2f}",
            })
        return examples

    def _production_to_email_data(self, row: ProductionEmail) -> EmailData:
        sender_domain = row.sender_domain or _domain_from_email(row.sender)
        return EmailData(
            message_id=row.message_id,
            conversation_id=row.conversation_id or "",
            sender=row.sender or "",
            sender_domain=sender_domain,
            to_recipients=row.to_recipients or [],
            to_domains=_domains(row.to_recipients),
            cc_recipients=row.cc_recipients or [],
            cc_domains=_domains(row.cc_recipients),
            subject=row.subject or "",
            received_date=row.received_date,
            body_text=row.body_text or "",
            body_preview=row.body_preview,
            has_attachments=row.has_attachments,
            attachment_names=row.attachment_names or [],
        )

    def _identify_lender(self, email: EmailData, kb: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        domain_map = kb["domain_map"]
        sender_domain = (email.sender_domain or _domain_from_email(email.sender)).lower()
        evidence = {
            "sender": email.sender,
            "sender_domain": sender_domain,
            "matched_domain": None,
            "matched_by": None,
            "authorized": False,
        }

        if sender_domain in domain_map and sender_domain not in INTERNAL_DOMAINS:
            lender = domain_map[sender_domain]
            evidence.update({"matched_domain": sender_domain, "matched_by": "sender_domain", "authorized": True})
            return lender, evidence

        for domain in [*email.to_domains, *email.cc_domains]:
            if domain in domain_map and domain not in INTERNAL_DOMAINS:
                lender = domain_map[domain]
                evidence.update({"matched_domain": domain, "matched_by": "recipient_domain", "authorized": True})
                return lender, evidence

        text = _normalize(f"{email.sender} {email.subject} {email.body_text[:3000]}")
        for entry in kb["entries"]:
            candidates = [entry["lender"], *entry.get("lender_aliases", [])]
            for candidate in candidates:
                if candidate and _normalize(candidate) in text:
                    lender = entry["lender"]
                    evidence.update({"matched_by": "content_alias", "authorized": lender in kb["authorized_lenders"]})
                    return lender, evidence

        return "UNKNOWN", evidence

    def _identify_waiver(
        self,
        email: EmailData,
        lender: str,
        kb: dict[str, Any],
    ) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
        subject = _normalize(email.subject)
        body = _normalize(email.body_text)
        haystack = f"{subject} {body}"
        candidates = kb["by_lender"].get(lender) if lender != "UNKNOWN" else kb["entries"]
        candidates = candidates or []

        best_entry: Optional[dict[str, Any]] = None
        best_score = 0.0
        best_matches: list[str] = []

        for entry in candidates:
            score = 0.0
            matches: list[str] = []

            waiver_name = _normalize(entry["waiver_type"])
            if waiver_name and waiver_name in subject:
                score += 0.35
                matches.append(f"subject waiver name: {entry['waiver_type']}")
            elif waiver_name and waiver_name in body:
                score += 0.20
                matches.append(f"body waiver name: {entry['waiver_type']}")

            for trigger in entry.get("trigger_list", []):
                normalized_trigger = _normalize(trigger)
                if not normalized_trigger:
                    continue
                if normalized_trigger in subject:
                    score += 0.25
                    matches.append(f"subject trigger: {trigger}")
                elif normalized_trigger in body:
                    score += 0.15
                    matches.append(f"body trigger: {trigger}")

            token_hits = self._token_overlap(waiver_name, haystack)
            if token_hits:
                score += min(0.20, token_hits * 0.04)
                matches.append(f"waiver token hits: {token_hits}")

            if score > best_score:
                best_entry = entry
                best_score = score
                best_matches = matches

        return best_entry, {
            "score": round(best_score, 3),
            "matches": best_matches,
            "candidate_count": len(candidates),
        }

    def _token_overlap(self, waiver_name: str, haystack: str) -> int:
        stopwords = {"and", "or", "the", "of", "for", "to", "a", "de", "la", "el", "y"}
        tokens = [t for t in re.findall(r"[a-z0-9]+", waiver_name) if len(t) > 2 and t not in stopwords]
        return sum(1 for token in tokens if token in haystack)

    def _validate(
        self,
        email: EmailData,
        lender: str,
        waiver_entry: Optional[dict[str, Any]],
        lender_evidence: dict[str, Any],
        waiver_evidence: dict[str, Any],
        kb: dict[str, Any],
    ) -> dict[str, Any]:
        lender_in_domain_map = lender in set(kb["domain_map"].values())
        waiver_valid_for_lender = bool(
            waiver_entry and waiver_entry["lender"] == lender and lender != "UNKNOWN"
        )
        text = _normalize(f"{email.subject} {email.body_text}")
        injection_detected = any(pattern in text for pattern in PROMPT_INJECTION_PATTERNS)

        return {
            "lender_in_domain_map": lender_in_domain_map,
            "waiver_valid_for_lender": waiver_valid_for_lender,
            "sender_checked": bool(email.sender),
            "domain_checked": bool(lender_evidence.get("sender_domain")),
            "subject_checked": bool(email.subject),
            "body_checked": bool(email.body_text),
            "trigger_matches": waiver_evidence.get("matches", []),
            "lender_evidence": lender_evidence,
            "waiver_evidence": waiver_evidence,
            "prompt_injection_detected": injection_detected,
        }

    def _build_rule_result(
        self,
        email: EmailData,
        lender: str,
        waiver_entry: Optional[dict[str, Any]],
        validation: dict[str, Any],
    ) -> ClassificationResult:
        waiver_type = waiver_entry["waiver_type"] if waiver_entry else "UNKNOWN"
        documents_expected = waiver_entry["documents_expected"] if waiver_entry else []

        lender_score = 0.45 if validation["lender_in_domain_map"] else (0.20 if lender != "UNKNOWN" else 0.0)
        waiver_score = min(0.45, float(validation["waiver_evidence"].get("score", 0.0)))
        validation_bonus = 0.10 if validation["waiver_valid_for_lender"] else 0.0
        confidence = max(0.0, min(1.0, lender_score + waiver_score + validation_bonus))
        if validation["prompt_injection_detected"]:
            confidence = min(confidence, 0.20)

        trigger_description = "; ".join(validation["trigger_matches"]) or "No configured trigger matched."
        category = _communication_category(email.subject, email.body_text)

        result = ClassificationResult(
            lender=lender,
            waiver_type=waiver_type,
            confidence_score=round(confidence, 3),
            confidence_level=_confidence_level(confidence),
            trigger_description=trigger_description,
            suggested_response=self._draft_response(email, lender, waiver_entry),
            documents_expected=documents_expected,
            required_evidence_ops=waiver_entry["evidence_required_ops"] if waiver_entry else "",
            required_evidence_insurance=waiver_entry["evidence_required_insurance"] if waiver_entry else "",
            waiver_pack=waiver_entry["waiver_pack"] if waiver_entry else "",
            actions_to_automate=waiver_entry["actions_to_automate"] if waiver_entry else "",
            validation_details=validation,
            communication_category=category,
            escalate_for_review=_should_escalate(
                email.subject, email.body_text,
                validation.get("prompt_injection_detected", False),
                category=category,
            ),
        )
        return result

    def _draft_response(
        self,
        email: EmailData,
        lender: str,
        waiver_entry: Optional[dict[str, Any]],
    ) -> str:
        greeting = "Hello,"
        if lender and lender != "UNKNOWN":
            greeting = f"Hello {lender} team,"

        if not waiver_entry:
            return (
                f"{greeting}\n\n"
                "Thank you for your message. We are reviewing the request and will confirm the applicable "
                "insurance documentation shortly.\n\n"
                "Best regards,\nAcentoPartners Insurance Team"
            )

        doc_list = waiver_entry.get("documents_expected") or []
        docs = "; ".join(doc_list) if doc_list else "the applicable supporting documentation"
        waiver_type = waiver_entry.get("waiver_type") or "insurance compliance request"
        evidence = waiver_entry.get("evidence_required_insurance") or waiver_entry.get("evidence_required_ops") or ""

        extra = f"\n\nWe will also validate: {evidence}" if evidence else ""
        return (
            f"{greeting}\n\n"
            f"Thank you for the note regarding {waiver_type}. Based on our review, the expected documents are: "
            f"{docs}.{extra}\n\n"
            "We will gather the applicable materials and follow up with the complete package.\n\n"
            "Best regards,\nAcentoPartners Insurance Team"
        )

    async def _enhance_with_llm(
        self,
        email: EmailData,
        rule_result: ClassificationResult,
        kb: dict[str, Any],
    ) -> ClassificationResult:
        lender_entries = kb["by_lender"].get(rule_result.lender, [])
        valid_waivers = [entry["waiver_type"] for entry in lender_entries]
        # Prompt LEAN: solo desambiguar el waiver. NO se pide redactar respuesta
        # (texto libre = generacion larga = minutos en CPU). La respuesta la
        # construyen las reglas. Se entregan los triggers como senal de match.
        prompt = {
            "task": "Pick the single most likely waiver_type for this email from valid_waivers. Return JSON only.",
            "rules": [
                "Choose only from valid_waivers, or 'UNKNOWN' if none fits.",
                "Prefer rule_suggestion unless the email clearly indicates another waiver.",
            ],
            "lender": rule_result.lender,
            "valid_waivers": [
                {"waiver_type": e["waiver_type"], "triggers": e["triggers"][:300]}
                for e in lender_entries
            ],
            "rule_suggestion": {
                "waiver_type": rule_result.waiver_type,
                "confidence_score": rule_result.confidence_score,
            },
            # Aprendizaje continuo: correcciones/rechazos humanos previos.
            "operator_feedback": feedback_context.read_context()[-1500:],
            "email": {
                "subject": email.subject,
                "body_text": email.body_text[:1500],
            },
            "output_schema": {
                "waiver_type": "one of valid_waivers or UNKNOWN",
                "confidence_score": "0.0-1.0",
                "trigger_description": "brief evidence (max 1 sentence)",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
                response = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": [{"role": "user", "content": json.dumps(prompt)}],
                        "stream": False,
                        "format": "json",
                        "keep_alive": "10m",
                        "options": {"temperature": 0.1, "num_predict": 200},
                    },
                )
                response.raise_for_status()
                payload = response.json()
                raw = payload.get("message", {}).get("content", "")
                data = json.loads(raw)
        except Exception as exc:
            logger.warning("LLM enhancement failed; using rule result: %r", exc)
            return rule_result

        enhanced = rule_result
        enhanced.raw_llm_response = raw

        rule_waiver = rule_result.waiver_type
        llm_waiver = data.get("waiver_type")

        if llm_waiver in valid_waivers:
            matching = next(
                entry for entry in kb["by_lender"][rule_result.lender]
                if entry["waiver_type"] == llm_waiver
            )
            enhanced.waiver_type = matching["waiver_type"]
            enhanced.documents_expected = matching["documents_expected"]
            enhanced.required_evidence_ops = matching["evidence_required_ops"]
            enhanced.required_evidence_insurance = matching["evidence_required_insurance"]
            enhanced.waiver_pack = matching["waiver_pack"]
            enhanced.actions_to_automate = matching["actions_to_automate"]
            # Acuerdo LLM <-> reglas: senal fuerte, sube la confianza.
            if llm_waiver == rule_waiver:
                enhanced.confidence_score = round(min(1.0, rule_result.confidence_score + 0.15), 3)
            # Si el LLM cambia a otro waiver valido, se conserva el score de reglas.
        elif str(llm_waiver or "").upper() == "UNKNOWN" and rule_waiver != "UNKNOWN":
            # El LLM no ve waiver donde las reglas si: se suaviza (no se trusta el numero del LLM).
            enhanced.confidence_score = round(min(rule_result.confidence_score, 0.5), 3)

        # El score lo gobiernan las reglas; el confidence_score del LLM (poco fiable
        # en un modelo pequeno en CPU) NO se usa. La respuesta la redactan las reglas.
        if data.get("trigger_description"):
            enhanced.trigger_description = str(data["trigger_description"])[:300]
        enhanced.confidence_level = _confidence_level(enhanced.confidence_score)

        return enhanced

    def _enforce_validation(self, result: ClassificationResult, kb: dict[str, Any]) -> ClassificationResult:
        if result.lender not in kb["authorized_lenders"]:
            result.lender = "UNKNOWN"
            result.waiver_type = "UNKNOWN"
            result.documents_expected = []
            result.confidence_score = min(result.confidence_score, 0.2)
            result.confidence_level = _confidence_level(result.confidence_score)
            return result

        valid_waivers = {entry["waiver_type"] for entry in kb["by_lender"].get(result.lender, [])}
        if result.waiver_type not in valid_waivers:
            result.waiver_type = "UNKNOWN"
            result.documents_expected = []
            result.confidence_score = min(result.confidence_score, 0.45)
            result.confidence_level = _confidence_level(result.confidence_score)
        return result


classifier = EmailClassifier()


def _print_results(rows: list[tuple[ProductionEmail, ClassificationResult]]) -> None:
    def safe(value: str | None, limit: int) -> str:
        text = value or ""
        text = text.encode("cp1252", errors="replace").decode("cp1252")
        return text[:limit]

    table = Table(title="Production Email Classifications", show_header=True)
    table.add_column("ID", justify="right")
    table.add_column("Subject", max_width=42)
    table.add_column("Lender", max_width=24)
    table.add_column("Waiver", max_width=28)
    table.add_column("Conf.", justify="right")
    table.add_column("Docs", max_width=36)

    for email, result in rows:
        table.add_row(
            str(email.id),
            safe(email.subject, 42),
            safe(result.lender, 24),
            safe(result.waiver_type, 28),
            f"{result.confidence_score:.2f}",
            safe("; ".join(result.documents_expected), 36),
        )
    console.print(table)


async def _main(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    await init_db()
    async with async_session() as session:
        rows = await classifier.classify_pending_production_emails(
            session,
            limit=args.limit,
            reclassify=args.reclassify,
        )
    if rows:
        _print_results(rows)
        console.print(f"[green]Clasificados/actualizados:[/green] {len(rows)}")
    else:
        console.print("[yellow]No hay correos pendientes para clasificar.[/yellow]")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clasifica correos desde production_emails usando matriz de negocio y LLM opcional."
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximo de correos. 0 = todos.")
    parser.add_argument(
        "--reclassify",
        action="store_true",
        help="Recalcula tambien correos que ya tienen clasificacion.",
    )
    asyncio.run(_main(parser.parse_args()))
