"""
api.py -- Capa API REST (FastAPI) sobre el pipeline de clasificacion.

Expone el backend existente (preflight + aprobacion de lenders + clasificacion)
como endpoints HTTP para que el frontend React lo consuma. No reimplementa
logica de negocio: envuelve las funciones ya probadas de:
  - llm_classifier.classifier   (clasificar lote pendiente)
  - lender_approval             (aprobar / rechazar dominios)
  - models                      (lecturas de production_emails, reviews, etc.)

Correr:
    ./venv/Scripts/python.exe -m uvicorn api:app --reload --port 8000

El router usa prefijo /api/v1 y nombres de recurso alineados con el frontend
de OGM_Lenders para minimizar retrabajo de UI.
"""
from __future__ import annotations

import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.database import async_session, engine, init_db
from app.db.models import (
    AppSetting,
    ClassifierQaExample,
    DomainLenderMap,
    EmailClassification,
    EmailReview,
    LenderWaiverDocument,
    LenderWaiverMatrix,
    ProductionEmail,
    SharePointFile,
)
from app.services import feedback_context, lender_approval, qa_examples
from app.services.llm_classifier import classifier
from app.services.sharepoint.connector import sharepoint


# ---------------------------------------------------------------------------
# Cuerpos de peticion (Pydantic)
# ---------------------------------------------------------------------------

class CorrectionIn(BaseModel):
    corrected_lender: str
    corrected_waiver_type: str
    reviewed_by: str = "operator"
    notes: Optional[str] = None


class RejectionIn(BaseModel):
    comment: str
    reviewed_by: str = "operator"


class SignatureIn(BaseModel):
    signature: str


class ReviewActionIn(BaseModel):
    note: Optional[str] = None


class WaiverIn(BaseModel):
    lender: str
    waiver_type: str
    lender_aliases: list[str] = []
    triggers: str = ""
    evidence_required_ops: str = ""
    evidence_required_insurance: str = ""
    actions_to_automate: str = ""
    waiver_pack: str = ""
    documents: list[str] = []


# ---------------------------------------------------------------------------
# App + ciclo de vida
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Asegura que las tablas existan (no destructivo).
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="API del clasificador de correos lender/waiver (pipeline preflight + aprobacion).",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev; en prod restringir a origen del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Serializadores (modelos SQLAlchemy -> dict JSON)
# ---------------------------------------------------------------------------

def _lender_to_dict(row: DomainLenderMap) -> dict[str, Any]:
    return {
        "id": row.id,
        "domain": row.domain,
        "lender_name": row.lender_name,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _email_to_dict(row: ProductionEmail) -> dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "conversation_id": row.conversation_id,
        "case_id": row.case_id,
        "sender": row.sender,
        "sender_domain": row.sender_domain,
        "subject": row.subject,
        "received_date": row.received_date.isoformat() if row.received_date else None,
        "body_preview": row.body_preview,
        "has_attachments": row.has_attachments,
        "attachment_names": row.attachment_names or [],
    }


def _email_detail_dict(row: ProductionEmail) -> dict[str, Any]:
    """Detalle completo: incluye cuerpo y destinatarios."""
    return {
        **_email_to_dict(row),
        "to_recipients": row.to_recipients or [],
        "cc_recipients": row.cc_recipients or [],
        "body_text": row.body_text or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _waiver_to_dict(row: LenderWaiverMatrix) -> dict[str, Any]:
    docs = sorted(row.documents, key=lambda d: d.position)
    return {
        "id": row.id,
        "lender": row.lender,
        "lender_aliases": row.lender_aliases or [],
        "waiver_type": row.waiver_type,
        "triggers": row.triggers or "",
        "evidence_required_ops": row.evidence_required_ops or "",
        "evidence_required_insurance": row.evidence_required_insurance or "",
        "actions_to_automate": row.actions_to_automate or "",
        "waiver_pack": row.waiver_pack or "",
        "documents": [d.document_name for d in docs],
    }


# Etiqueta friendly por stage (unifica lender_nuevo + lender_por_aprobar).
_STAGE_LABELS = {
    "blacklist": "Blacklist",
    "lender_nuevo": "Lender por aprobar",
    "lender_por_aprobar": "Lender por aprobar",
    "hilo_incompleto": "Hilo incompleto",
    "reenvio": "Reenvío",
    "seguridad_bloqueo": "Seguridad / bloqueo",
    "duplicado": "Hilo: hay correo más reciente",
    "sin_lender": "Sin lender aprobado",
}


def _review_dict(row: EmailReview, email: Optional[ProductionEmail]) -> dict[str, Any]:
    domain = (email.sender_domain if email else "") or ""
    internal = domain.lower() in {d.lower() for d in settings.internal_domains}
    stage_label = _STAGE_LABELS.get(row.stage, row.stage)
    if row.stage == "reenvio" and internal:
        stage_label = "Reenvío interno"
    return {
        "id": row.id,
        "message_id": row.message_id,
        "conversation_id": row.conversation_id,
        "case_id": row.case_id,
        "stage": row.stage,
        "stage_label": stage_label,
        "reason": row.reason,
        "detected_original_sender": row.detected_original_sender,
        "status": row.status,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        # Metadatos del correo (join) — dominio siempre aunque falte remitente.
        "sender": email.sender if email else None,
        "sender_domain": domain or None,
        "subject": email.subject if email else None,
        "received_date": (email.received_date.isoformat() if email and email.received_date else None),
        "internal_forward": internal,
        "production_email_id": row.production_email_id,
    }


def _classification_to_dict(row: EmailClassification) -> dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "lender": row.lender,
        "waiver_type": row.waiver_type,
        "confidence_score": row.confidence_score,
        "confidence_level": row.confidence_level,
        "trigger_description": row.trigger_description,
        "suggested_response": row.suggested_response,
        "documents_expected": row.documents_expected or [],
        "validation_details": row.validation_details or {},
        "secondary_issues": row.secondary_issues or [],
        "communication_category": row.communication_category,
        "escalate_for_review": row.escalate_for_review,
        "suggested_attachments": row.suggested_attachments or [],
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "corrected_lender": row.corrected_lender,
        "corrected_waiver_type": row.corrected_waiver_type,
        "correction_notes": row.correction_notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "api_base": "/api/v1",
    }


@app.get("/api/v1/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    db_ok = True
    try:
        await session.scalar(select(func.count(ProductionEmail.id)))
    except Exception:  # noqa: BLE001 - health no debe romper
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": {"connected": db_ok},
        "llm": {
            "enabled": settings.use_llm_classifier,
            "model": settings.ollama_model,
            "base_url": settings.ollama_base_url,
        },
        "sharepoint": {"configured": sharepoint.is_configured},
    }


@app.get("/api/v1/business-context")
async def business_context() -> dict[str, Any]:
    """Contexto de negocio de Acento (activo; aun no cableado al clasificador)."""
    from app.core.business_context import load_business_context
    return load_business_context()


@app.get("/api/v1/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    total_emails = await session.scalar(select(func.count(ProductionEmail.id))) or 0
    total_cls = await session.scalar(select(func.count(EmailClassification.id))) or 0
    avg_conf = await session.scalar(select(func.avg(EmailClassification.confidence_score)))

    by_lender = {
        row[0]: row[1]
        for row in (await session.execute(
            select(EmailClassification.lender, func.count(EmailClassification.id))
            .group_by(EmailClassification.lender)
        )).all()
    }
    by_level = {
        row[0]: row[1]
        for row in (await session.execute(
            select(EmailClassification.confidence_level, func.count(EmailClassification.id))
            .group_by(EmailClassification.confidence_level)
        )).all()
    }
    reviews_by_stage = {
        row[0]: row[1]
        for row in (await session.execute(
            select(EmailReview.stage, func.count(EmailReview.id))
            .where(EmailReview.status == "PENDIENTE")
            .group_by(EmailReview.stage)
        )).all()
    }
    lenders_by_status = {
        row[0]: row[1]
        for row in (await session.execute(
            select(DomainLenderMap.status, func.count(DomainLenderMap.id))
            .group_by(DomainLenderMap.status)
        )).all()
    }

    return {
        "total_emails": total_emails,
        "total_classified": total_cls,
        "avg_confidence": round(avg_conf or 0.0, 3),
        "classifications_by_lender": by_lender,
        "classifications_by_confidence": by_level,
        "pending_reviews_by_stage": reviews_by_stage,
        "lenders_by_status": lenders_by_status,
    }


# ---------------------------------------------------------------------------
# Lenders (domain_lender_map) + aprobacion
# ---------------------------------------------------------------------------

@app.get("/api/v1/lenders")
async def list_lenders(
    status: Optional[str] = Query(default=None, description="APROBADO|POR_APROBAR|NO_APROBADO"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(DomainLenderMap).order_by(DomainLenderMap.created_at.desc().nullslast())
    if status:
        stmt = stmt.where(DomainLenderMap.status == status.upper())
    rows = (await session.scalars(stmt)).all()
    return {"total": len(rows), "items": [_lender_to_dict(r) for r in rows]}


@app.post("/api/v1/lenders/{domain}/approve")
async def approve_lender(
    domain: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await lender_approval.approve_domain(session, domain)
    if not result.get("found"):
        raise HTTPException(404, f"Domain not found in domain_lender_map: {domain}")
    return result


@app.post("/api/v1/lenders/{domain}/reject")
async def reject_lender(
    domain: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await lender_approval.reject_domain(session, domain)
    return {"domain": domain.lower(), "status": "NO_APROBADO"}


# ---------------------------------------------------------------------------
# Emails de produccion
# ---------------------------------------------------------------------------

@app.get("/api/v1/emails")
async def list_emails(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sender_domain: Optional[str] = None,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(ProductionEmail).order_by(ProductionEmail.received_date.desc().nullslast())
    if sender_domain:
        stmt = stmt.where(ProductionEmail.sender_domain == sender_domain.lower())
    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            ProductionEmail.subject.ilike(term) | ProductionEmail.sender.ilike(term)
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.limit(limit).offset(offset))).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_email_to_dict(r) for r in rows]}


@app.get("/api/v1/emails/{email_id}")
async def get_email(
    email_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(ProductionEmail, email_id)
    if row is None:
        raise HTTPException(404, "Email not found")
    return _email_detail_dict(row)


@app.get("/api/v1/emails/{email_id}/thread")
async def email_thread(
    email_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Hilo de conversacion (iteraciones) al que pertenece el correo.

    Agrupa por conversation_id, ordenado del mas viejo al mas nuevo, con la
    fecha de cada iteracion (estilo Outlook).
    """
    row = await session.get(ProductionEmail, email_id)
    if row is None:
        raise HTTPException(404, "Email not found")
    conv = row.conversation_id
    if conv:
        emails = (await session.scalars(
            select(ProductionEmail)
            .where(ProductionEmail.conversation_id == conv)
            .order_by(ProductionEmail.received_date.asc().nullsfirst())
        )).all()
    else:
        emails = [row]
    return {
        "conversation_id": conv,
        "count": len(emails),
        "items": [{
            "id": e.id,
            "subject": e.subject,
            "sender": e.sender,
            "sender_domain": e.sender_domain,
            "received_date": e.received_date.isoformat() if e.received_date else None,
            "has_attachments": e.has_attachments,
            "is_current": e.id == email_id,
        } for e in emails],
    }


# ---------------------------------------------------------------------------
# Bandeja unificada: correo + estado derivado (clasificacion + revision)
# ---------------------------------------------------------------------------

# Prioridad de estado y a que tab pertenece. Particion: cada correo cae en
# exactamente una tab (fuera de "general"), asi las tarjetas SUMAN al total.
_INBOX_TABS = {
    "general": None,  # todos
    "clasificados": {"clasificada", "aprobado", "rechazado"},
    "por_revisar": {"por_revisar"},
    "descartado": {"descartado"},
    "contestado": {"contestado"},
}


def _derive_estado(cls, reviews: list) -> str:
    """Estado unificado del correo a partir de su clasificacion y revisiones.

    Prioridad: revision humana pendiente > respuesta humana > clasificacion
    viva > descarte. GESTIONADO es solo un cierre automatico (el correo se
    clasifico despues); no cuenta como contestado ni tapa la clasificacion.
    Una review DESCARTADO residual de una corrida vieja tampoco esconde una
    clasificacion vigente.
    """
    statuses = {r.status for r in reviews}
    if "PENDIENTE" in statuses:
        return "por_revisar"
    if "CONTESTADO" in statuses:
        return "contestado"
    if cls is not None:
        if cls.status in ("reviewed", "corrected"):
            return "aprobado"
        if cls.status == "rejected":
            return "rechazado"
        return "clasificada"
    if "DESCARTADO" in statuses:
        return "descartado"
    return "sin_procesar"


@app.get("/api/v1/inbox")
async def inbox(
    tab: str = Query(default="general"),
    search: Optional[str] = None,
    from_date: Optional[str] = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    to_date: Optional[str] = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Bandeja estilo Outlook: cada correo con su estado (clasificada IA /
    por revisar / descartado / contestado / aprobado). Filtra por tab.

    Volumen actual (~cientos) permite computar el estado en Python.
    """
    tab = (tab or "general").lower()
    wanted = _INBOX_TABS.get(tab, None)

    emails = (await session.scalars(
        select(ProductionEmail).order_by(ProductionEmail.received_date.desc().nullslast())
    )).all()

    cls_rows = (await session.scalars(select(EmailClassification))).all()
    cls_by_mid = {c.message_id: c for c in cls_rows}
    rev_rows = (await session.scalars(select(EmailReview))).all()
    rev_by_mid: dict[str, list] = {}
    for r in rev_rows:
        rev_by_mid.setdefault(r.message_id, []).append(r)

    term = (search or "").lower().strip()
    dfrom = (from_date or "").strip() or None
    dto = (to_date or "").strip() or None
    counts = {"general": 0, "clasificados": 0, "por_revisar": 0,
              "descartado": 0, "contestado": 0}
    items: list[dict[str, Any]] = []
    for e in emails:
        if term and term not in (e.subject or "").lower() and term not in (e.sender or "").lower():
            continue
        if dfrom or dto:
            d = e.received_date.date().isoformat() if e.received_date else None
            if d is None:
                continue
            if dfrom and d < dfrom:
                continue
            if dto and d > dto:
                continue
        cls = cls_by_mid.get(e.message_id)
        revs = rev_by_mid.get(e.message_id, [])
        estado = _derive_estado(cls, revs)
        # Conteo por tab (sobre el universo filtrado por search).
        counts["general"] += 1
        for tname, tset in _INBOX_TABS.items():
            if tset is not None and estado in tset:
                counts[tname] += 1
        if wanted is not None and estado not in wanted:
            continue
        pend = next((r for r in revs if r.status == "PENDIENTE"), None)
        rev = pend or (revs[0] if revs else None)
        items.append({
            "id": e.id,
            "message_id": e.message_id,
            "subject": e.subject,
            "sender": e.sender,
            "sender_domain": e.sender_domain,
            "received_date": e.received_date.isoformat() if e.received_date else None,
            "has_attachments": e.has_attachments,
            "estado": estado,
            "classification": None if cls is None else {
                "id": cls.id, "lender": cls.lender, "waiver_type": cls.waiver_type,
                "confidence_level": cls.confidence_level, "status": cls.status,
            },
            "review": None if rev is None else {
                "id": rev.id, "stage": rev.stage, "reason": rev.reason, "status": rev.status,
            },
        })

    total = len(items)
    page = items[offset:offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "items": page, "counts": counts}


# ---------------------------------------------------------------------------
# Cola de revision manual (email_reviews)
# ---------------------------------------------------------------------------

@app.get("/api/v1/reviews")
async def list_reviews(
    stage: Optional[str] = Query(default=None, description="uno o varios stages, separados por coma"),
    status: str = Query(default="PENDIENTE", description="uno o varios, separados por coma"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(EmailReview, ProductionEmail)
        .join(ProductionEmail, EmailReview.production_email_id == ProductionEmail.id, isouter=True)
        .order_by(EmailReview.created_at.desc().nullslast())
    )
    if status:
        statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
        stmt = stmt.where(EmailReview.status.in_(statuses))
    if stage:
        stages = [s.strip() for s in stage.split(",") if s.strip()]
        stmt = stmt.where(EmailReview.stage.in_(stages))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.execute(stmt.limit(limit).offset(offset))).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_review_dict(rev, pe) for rev, pe in rows]}


@app.get("/api/v1/reviews/{review_id}")
async def get_review(
    review_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rev = await session.get(EmailReview, review_id)
    if rev is None:
        raise HTTPException(404, "Review not found")
    pe = await session.get(ProductionEmail, rev.production_email_id) if rev.production_email_id else None
    data = _review_dict(rev, pe)
    if pe is not None:
        data["email"] = _email_detail_dict(pe)

    # Hilo de la conversacion: todos los correos con el mismo case_id/conversation_id.
    key = rev.case_id or rev.conversation_id or (pe.case_id if pe else "") or (pe.conversation_id if pe else "")
    thread: list[dict[str, Any]] = []
    if key:
        t_rows = (await session.scalars(
            select(ProductionEmail)
            .where((ProductionEmail.case_id == key) | (ProductionEmail.conversation_id == key))
            .order_by(ProductionEmail.received_date.asc().nullsfirst())
        )).all()
        thread = [
            {
                "id": e.id,
                "sender": e.sender,
                "sender_domain": e.sender_domain,
                "subject": e.subject,
                "received_date": e.received_date.isoformat() if e.received_date else None,
                "body_preview": e.body_preview,
                "is_current": pe is not None and e.id == pe.id,
            }
            for e in t_rows
        ]
    data["thread"] = thread
    return data


async def _resolve_review(session: AsyncSession, review_id: int, status: str, note: Optional[str]) -> dict[str, Any]:
    rev = await session.get(EmailReview, review_id)
    if rev is None:
        raise HTTPException(404, "Review not found")
    rev.status = status
    rev.note = note
    rev.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    pe = await session.get(ProductionEmail, rev.production_email_id) if rev.production_email_id else None
    return _review_dict(rev, pe)


@app.post("/api/v1/reviews/{review_id}/discard")
async def discard_review(
    review_id: int,
    body: ReviewActionIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await _resolve_review(session, review_id, "DESCARTADO", body.note)


@app.post("/api/v1/reviews/{review_id}/answer")
async def answer_review(
    review_id: int,
    body: ReviewActionIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await _resolve_review(session, review_id, "CONTESTADO", body.note)


# ---------------------------------------------------------------------------
# Clasificaciones
# ---------------------------------------------------------------------------

@app.get("/api/v1/classifications")
async def list_classifications(
    lender: Optional[str] = None,
    confidence_level: Optional[str] = None,
    status: Optional[str] = Query(default=None, description="classified|reviewed|corrected"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(EmailClassification).order_by(EmailClassification.updated_at.desc().nullslast())
    if lender:
        stmt = stmt.where(EmailClassification.lender.ilike(f"%{lender}%"))
    if confidence_level:
        stmt = stmt.where(EmailClassification.confidence_level == confidence_level)
    if status:
        stmt = stmt.where(EmailClassification.status == status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.limit(limit).offset(offset))).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_classification_to_dict(r) for r in rows]}


@app.get("/api/v1/classifications/{classification_id}")
async def get_classification(
    classification_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(EmailClassification, classification_id)
    if row is None:
        raise HTTPException(404, "Classification not found")

    data = _classification_to_dict(row)

    # Enriquecer con la entrada de la matriz (el "por que": evidencia, waiver_pack, acciones).
    matrix = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.lender == row.lender)
        .where(LenderWaiverMatrix.waiver_type == row.waiver_type)
    )
    if matrix is not None:
        data["matrix"] = _waiver_to_dict(matrix)

    # Adjuntar metadatos y cuerpo del correo original.
    if row.production_email_id is not None:
        pe = await session.get(ProductionEmail, row.production_email_id)
        if pe is not None:
            data["email"] = _email_detail_dict(pe)

    return data


@app.post("/api/v1/classifications/{classification_id}/approve")
async def approve_classification(
    classification_id: int,
    reviewed_by: str = Query(default="operator"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(EmailClassification, classification_id)
    if row is None:
        raise HTTPException(404, "Classification not found")
    row.status = "reviewed"
    row.reviewed_by = reviewed_by
    row.updated_at = datetime.now(timezone.utc)

    # Q&A training: la aprobacion confirma el par lender/waiver como ejemplo.
    await qa_examples.record_example(
        session, row.message_id, row.lender, row.waiver_type, source="approve",
    )

    await session.commit()
    await session.refresh(row)
    return _classification_to_dict(row)


@app.post("/api/v1/classifications/{classification_id}/correct")
async def correct_classification(
    classification_id: int,
    body: CorrectionIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(EmailClassification, classification_id)
    if row is None:
        raise HTTPException(404, "Classification not found")

    # Registrar en el contexto de feedback ANTES de sobrescribir el par original.
    feedback_context.append_correction(
        row.lender, row.waiver_type,
        body.corrected_lender, body.corrected_waiver_type, body.notes,
    )

    row.corrected_lender = body.corrected_lender
    row.corrected_waiver_type = body.corrected_waiver_type
    row.reviewed_by = body.reviewed_by
    row.correction_notes = body.notes
    row.status = "corrected"
    row.lender = body.corrected_lender
    row.waiver_type = body.corrected_waiver_type

    # Re-enriquecer documents_expected desde la matriz para el par corregido.
    matrix = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.lender == body.corrected_lender)
        .where(LenderWaiverMatrix.waiver_type == body.corrected_waiver_type)
    )
    if matrix is not None:
        row.documents_expected = [d.document_name for d in sorted(matrix.documents, key=lambda d: d.position)]

    # Q&A training: la correccion es el ejemplo mas valioso (verdad del operador).
    await qa_examples.record_example(
        session, row.message_id, body.corrected_lender, body.corrected_waiver_type,
        source="correct", notes=body.notes,
    )

    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return _classification_to_dict(row)


@app.post("/api/v1/classifications/{classification_id}/reject")
async def reject_classification(
    classification_id: int,
    body: RejectionIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Rechaza una clasificacion con comentario; alimenta el contexto de feedback."""
    row = await session.get(EmailClassification, classification_id)
    if row is None:
        raise HTTPException(404, "Classification not found")

    feedback_context.append_rejection(row.lender, row.waiver_type, body.comment)

    row.status = "rejected"
    row.reviewed_by = body.reviewed_by
    row.correction_notes = body.comment
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return _classification_to_dict(row)


@app.get("/api/v1/qa-examples")
async def list_qa_examples(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Ejemplos Q&A confirmados por el operador (training del clasificador)."""
    rows = (await session.scalars(
        select(ClassifierQaExample)
        .order_by(ClassifierQaExample.updated_at.desc())
        .limit(limit)
    )).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": r.id,
                "message_id": r.message_id,
                "subject": r.subject,
                "sender_domain": r.sender_domain,
                "lender": r.lender,
                "waiver_type": r.waiver_type,
                "source": r.source,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ],
    }


@app.get("/api/v1/feedback-context")
async def get_feedback_context() -> dict[str, Any]:
    """Devuelve el contexto de feedback acumulado (correcciones + rechazos)."""
    return {"content": feedback_context.read_context()}


@app.get("/api/v1/settings/signature")
async def get_signature(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Firma del operador (para el composer de respuesta manual)."""
    row = await session.get(AppSetting, "signature")
    return {"signature": row.value if row else ""}


@app.put("/api/v1/settings/signature")
async def put_signature(
    body: SignatureIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(AppSetting, "signature")
    if row is None:
        session.add(AppSetting(key="signature", value=body.signature))
    else:
        row.value = body.signature
        row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"signature": body.signature}


@app.post("/api/v1/classify/run")
async def run_classification(
    limit: int = Query(default=100, ge=0, le=1000,
                       description="0 = todos los pendientes"),
    reclassify: bool = Query(default=False,
                            description="True = reprocesa incluso los ya clasificados"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    results = await classifier.classify_pending_production_emails(
        session, limit=limit, reclassify=reclassify
    )
    return {
        "classified": len(results),
        "items": [
            {
                "message_id": pe.message_id,
                "lender": res.lender,
                "waiver_type": res.waiver_type,
                "confidence_score": res.confidence_score,
                "confidence_level": res.confidence_level,
            }
            for pe, res in results
        ],
    }


@app.post("/api/v1/emails/reload")
async def reload_emails(
    reclassify: bool = Query(default=False, description="reprocesa incluso los ya clasificados"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Ingesta correos de Outlook (todas las fechas) y clasifica los pendientes.

    Es el 'Recargar' de la Bandeja: trae el buzon completo y corre el pipeline.
    """
    from app.services.read_emails import read_outlook_emails, save_to_db

    try:
        emails = await read_outlook_emails(filter_today=False)
    except ValueError as exc:  # Outlook no configurado
        raise HTTPException(400, str(exc))
    except ConnectionError as exc:  # error de Graph
        raise HTTPException(502, str(exc))

    processed, total = await save_to_db(emails)
    results = await classifier.classify_pending_production_emails(
        session, limit=0, reclassify=reclassify
    )
    return {
        "ingested": processed,
        "total_emails": total,
        "classified": len(results),
    }


# ---------------------------------------------------------------------------
# Matriz lender-waiver (knowledge base editable)
# ---------------------------------------------------------------------------

@app.get("/api/v1/lenders-and-waivers")
async def lenders_and_waivers(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Lenders y sus waivers validos, para los dropdowns de correccion."""
    rows = (await session.scalars(
        select(LenderWaiverMatrix).order_by(LenderWaiverMatrix.lender, LenderWaiverMatrix.waiver_type)
    )).all()
    by_lender: dict[str, list[str]] = {}
    for r in rows:
        by_lender.setdefault(r.lender, []).append(r.waiver_type)
    return {
        "lenders": [{"name": name, "waivers": waivers} for name, waivers in by_lender.items()],
        "combinations": [{"lender": r.lender, "waiver_type": r.waiver_type} for r in rows],
    }


@app.get("/api/v1/waivers")
async def list_waivers(
    lender: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .order_by(LenderWaiverMatrix.lender, LenderWaiverMatrix.waiver_type)
    )
    if lender:
        stmt = stmt.where(LenderWaiverMatrix.lender.ilike(f"%{lender}%"))
    rows = (await session.scalars(stmt)).all()
    return {"total": len(rows), "items": [_waiver_to_dict(r) for r in rows]}


async def _apply_waiver_payload(row: LenderWaiverMatrix, body: WaiverIn) -> None:
    row.lender = body.lender.strip()
    row.waiver_type = body.waiver_type.strip()
    row.lender_aliases = body.lender_aliases
    row.triggers = body.triggers
    row.evidence_required_ops = body.evidence_required_ops
    row.evidence_required_insurance = body.evidence_required_insurance
    row.actions_to_automate = body.actions_to_automate
    row.waiver_pack = body.waiver_pack
    row.documents = [
        LenderWaiverDocument(document_name=doc.strip(), position=i)
        for i, doc in enumerate(body.documents)
        if doc.strip()
    ]


@app.post("/api/v1/waivers", status_code=201)
async def create_waiver(
    body: WaiverIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    exists = await session.scalar(
        select(LenderWaiverMatrix.id)
        .where(LenderWaiverMatrix.lender == body.lender.strip())
        .where(LenderWaiverMatrix.waiver_type == body.waiver_type.strip())
    )
    if exists:
        raise HTTPException(409, "A waiver with that lender + waiver_type already exists")
    row = LenderWaiverMatrix()
    await _apply_waiver_payload(row, body)
    session.add(row)
    await session.commit()
    row = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.id == row.id)
    )
    return _waiver_to_dict(row)


@app.put("/api/v1/waivers/{waiver_id}")
async def update_waiver(
    waiver_id: int,
    body: WaiverIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.id == waiver_id)
    )
    if row is None:
        raise HTTPException(404, "Waiver not found")
    conflict = await session.scalar(
        select(LenderWaiverMatrix.id)
        .where(LenderWaiverMatrix.lender == body.lender.strip())
        .where(LenderWaiverMatrix.waiver_type == body.waiver_type.strip())
        .where(LenderWaiverMatrix.id != waiver_id)
    )
    if conflict:
        raise HTTPException(409, "Another waiver already uses that lender + waiver_type")
    await _apply_waiver_payload(row, body)
    await session.commit()
    row = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.id == waiver_id)
    )
    return _waiver_to_dict(row)


@app.delete("/api/v1/waivers/{waiver_id}", status_code=204)
async def delete_waiver(
    waiver_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(LenderWaiverMatrix, waiver_id)
    if row is None:
        raise HTTPException(404, "Waiver not found")
    await session.delete(row)
    await session.commit()


# ---------------------------------------------------------------------------
# SharePoint (inventario de archivos via Microsoft Graph)
# ---------------------------------------------------------------------------

def _sp_file_to_dict(row: SharePointFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "drive_name": row.drive_name,
        "name": row.name,
        "path": row.path,
        "is_folder": row.is_folder,
        "size": row.size,
        "file_extension": row.file_extension,
        "web_url": row.web_url,
        "sp_modified_at": row.sp_modified_at.isoformat() if row.sp_modified_at else None,
        "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
    }


@app.get("/api/v1/sharepoint/status")
async def sharepoint_status() -> dict[str, Any]:
    return await sharepoint.test_connection()


@app.post("/api/v1/sharepoint/sync")
async def sharepoint_sync(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Recorre cada drive del sitio configurado y hace upsert de metadatos."""
    if not sharepoint.is_configured:
        raise HTTPException(400, "SharePoint not configured. Set AZURE_* and SHAREPOINT_* in .env")

    start = time.perf_counter()
    seen = added = updated = 0
    drive_names: list[str] = []
    async with httpx.AsyncClient() as client:
        try:
            drives = await sharepoint.list_drives(client)
        except ConnectionError as e:
            raise HTTPException(502, str(e))
        for d in drives:
            drive_id, drive_name = d["id"], d.get("name", "(sin nombre)")
            drive_names.append(drive_name)
            async for sp in sharepoint.walk_drive(client, drive_id, drive_name):
                seen += 1
                existed = await session.get(SharePointFile, sp.id)
                if existed is None:
                    session.add(SharePointFile(
                        id=sp.id, drive_id=sp.drive_id, drive_name=sp.drive_name,
                        name=sp.name, path=sp.path, parent_path=sp.parent_path,
                        is_folder=sp.is_folder, size=sp.size, mime_type=sp.mime_type,
                        file_extension=sp.file_extension, web_url=sp.web_url,
                        sp_created_at=sp.sp_created_at, sp_modified_at=sp.sp_modified_at,
                    ))
                    added += 1
                else:
                    for attr in ("drive_name", "name", "path", "parent_path", "is_folder",
                                 "size", "mime_type", "file_extension", "web_url",
                                 "sp_created_at", "sp_modified_at"):
                        setattr(existed, attr, getattr(sp, attr))
                    updated += 1
                if seen % 200 == 0:
                    await session.commit()
    await session.commit()
    return {"drives": drive_names, "items_seen": seen, "files_added": added,
            "files_updated": updated, "took_seconds": round(time.perf_counter() - start, 2)}


@app.get("/api/v1/sharepoint/drives")
async def sharepoint_drives(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    names = [r[0] for r in (await session.execute(
        select(SharePointFile.drive_name).group_by(SharePointFile.drive_name)
        .order_by(SharePointFile.drive_name)
    )).all()]
    out = []
    for n in names:
        files = await session.scalar(select(func.count(SharePointFile.id)).where(
            SharePointFile.drive_name == n, SharePointFile.is_folder.is_(False)))
        out.append({"drive_name": n, "files": files or 0})
    return {"total": len(out), "items": out}


@app.get("/api/v1/sharepoint/files")
async def sharepoint_files(
    q: Optional[str] = Query(None, description="filtra por nombre o ruta (ILIKE)"),
    drive: Optional[str] = None,
    only_files: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(SharePointFile)
    if only_files:
        stmt = stmt.where(SharePointFile.is_folder.is_(False))
    if drive:
        stmt = stmt.where(SharePointFile.drive_name == drive)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(SharePointFile.name.ilike(like) | SharePointFile.path.ilike(like))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(
        stmt.order_by(SharePointFile.drive_name, SharePointFile.path).limit(limit).offset(offset)
    )).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_sp_file_to_dict(r) for r in rows]}


@app.get("/api/v1/sharepoint/files/{file_id}/content")
async def sharepoint_file_content(
    file_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Descarga el archivo real desde SharePoint (proxy) para verlo en el visor.

    Trae los bytes via Graph al vuelo (sin duplicar storage) y los sirve inline.
    """
    row = await session.get(SharePointFile, file_id)
    if row is None:
        raise HTTPException(404, "File not found in the inventory")
    if row.is_folder:
        raise HTTPException(400, "The item is a folder, not a file")
    if not sharepoint.is_configured:
        raise HTTPException(503, "SharePoint not configured")
    try:
        content, ctype = await sharepoint.download_item(row.drive_id, row.id)
    except ConnectionError as exc:
        raise HTTPException(502, str(exc))
    ascii_name = (row.name or "archivo").encode("ascii", "ignore").decode() or "archivo"
    return Response(
        content=content,
        media_type=row.mime_type or ctype,
        headers={"Content-Disposition": f'inline; filename="{ascii_name}"'},
    )


# ---------------------------------------------------------------------------
# Comparacion: documentos esperados (BD) vs archivos en SharePoint
# ---------------------------------------------------------------------------

# Tokens de relleno que no aportan al match (demasiado genericos).
_DOC_STOPWORDS = frozenset({
    "of", "the", "and", "for", "to", "a", "an", "with",
    "page", "pages", "form", "forms", "section", "copy", "final", "sample",
    "letter", "letters", "doc", "document", "documents", "file", "files",
})
# Archivos que son correspondencia, no el entregable en si.
_EMAIL_EXTS = frozenset({"eml", "msg"})


def _doc_tokens(text: str) -> list[str]:
    """Normaliza a tokens significativos: minusculas, alfanumericos, sin relleno.

    Mantiene numeros (p.ej. '101', '25') y tokens de >=2 caracteres. Descarta
    tokens de una sola letra (a/b de 'A&B') porque generan falsos positivos.
    """
    raw = re.split(r"[^a-z0-9]+", (text or "").lower())
    return [
        t for t in raw
        if t and t not in _DOC_STOPWORDS and (t.isdigit() or len(t) >= 2)
    ]


def _strip_ext(name: str) -> tuple[str, str]:
    """Devuelve (nombre_sin_ext, ext_minuscula)."""
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        return stem, ext.lower()
    return name, ""


async def _match_documents(session: AsyncSession, docs: list[str]) -> list[dict[str, Any]]:
    """Para cada documento esperado busca coincidencias en SharePoint.

    Estrategia en dos niveles (de mas fuerte a mas debil):
      1. EXACTO  -- el nombre del archivo (sin extension) == nombre del documento.
      2. TOKENS  -- todos los tokens significativos del documento aparecen en el
                    nombre del archivo (subconjunto). P.ej. 'ACORD 101' machea
                    'ACENTO - ... - ACORD FORM 101 - GL 01.06.26.pdf'.

    Los archivos de correo (.eml/.msg) solo cuentan para match exacto: son
    correspondencia, no el entregable de cumplimiento. found=False si nada
    coincide. Los matches se ordenan por match_type (exacto primero) y por
    cuan ajustado es (menos tokens sobrantes = mas relevante).
    """
    # Cargar el inventario una sola vez (cientos de filas, barato) y puntuar en Python.
    files = (await session.scalars(
        select(SharePointFile).where(SharePointFile.is_folder.is_(False))
    )).all()

    # Precomputar tokens y stem por archivo.
    catalog: list[tuple[SharePointFile, str, str, set[str]]] = []
    for f in files:
        stem, ext = _strip_ext(f.name)
        catalog.append((f, stem.lower(), ext, set(_doc_tokens(f.name))))

    result: list[dict[str, Any]] = []
    for doc in docs:
        d = (doc or "").strip()
        if not d:
            continue
        low = d.lower()
        expected = set(_doc_tokens(d))
        matches: list[tuple[int, int, dict[str, Any]]] = []
        for f, stem_low, ext, ftoks in catalog:
            is_email = ext in _EMAIL_EXTS
            if stem_low == low:
                match_type, rank, extra = "exact", 0, 0
            elif not is_email and expected and expected <= ftoks:
                match_type, rank, extra = "tokens", 1, len(ftoks - expected)
            else:
                continue
            matches.append((rank, extra, {
                "id": f.id,
                "name": f.name,
                "drive_name": f.drive_name,
                "web_url": f.web_url,
                "file_extension": f.file_extension,
                "match_type": match_type,
            }))
        matches.sort(key=lambda m: (m[0], m[1]))
        top = [m[2] for m in matches[:10]]
        result.append({
            "document": d,
            "found": len(top) > 0,
            "match_type": top[0]["match_type"] if top else None,
            "matches": top,
        })
    return result


# Ruido tipico de asuntos de correo que no identifica al caso.
_SUBJECT_STOPWORDS = frozenset({
    "fw", "fwd", "re", "rv", "external", "urgent", "reminder", "important",
    "notice", "notification", "first", "second", "third", "final",
    "request", "review", "questions", "insurance", "loan", "number",
    "borrower", "name", "llc", "inc", "email", "mail", "coverage",
    "compliance", "non", "identified", "required", "please",
})


def _subject_tokens(subject: str) -> list[str]:
    return [t for t in _doc_tokens(subject) if t not in _SUBJECT_STOPWORDS]


async def _match_subject_documents(
    session: AsyncSession, subject: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Archivos de SharePoint cuyo nombre comparte tokens significativos con el
    asunto del correo (propiedad, prestatario, numero de loan).

    Criterio: >=2 tokens en comun, o 1 token fuerte (numero de >=5 digitos,
    tipicamente el loan number). Los .eml/.msg se excluyen: son correspondencia,
    no evidencia. Ordena por cantidad de tokens coincidentes (fuertes pesan
    doble) y por nombre mas ajustado.
    """
    tokens = set(_subject_tokens(subject or ""))
    if not tokens:
        return []
    files = (await session.scalars(
        select(SharePointFile).where(SharePointFile.is_folder.is_(False))
    )).all()

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for f in files:
        _stem, ext = _strip_ext(f.name)
        if ext in _EMAIL_EXTS:
            continue
        ftoks = set(_doc_tokens(f.name))
        hits = tokens & ftoks
        if not hits:
            continue
        strong = any(t.isdigit() and len(t) >= 5 for t in hits)
        if len(hits) < 2 and not strong:
            continue
        rank = -(len(hits) + (2 if strong else 0))
        scored.append((rank, len(ftoks - tokens), {
            "id": f.id,
            "name": f.name,
            "drive_name": f.drive_name,
            "web_url": f.web_url,
            "file_extension": f.file_extension,
            "matched_tokens": sorted(hits),
        }))
    scored.sort(key=lambda m: (m[0], m[1]))
    return [m[2] for m in scored[:limit]]


@app.get("/api/v1/classifications/{classification_id}/documents")
async def classification_documents(
    classification_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(EmailClassification, classification_id)
    if row is None:
        raise HTTPException(404, "Classification not found")

    # Docs esperados: de la matriz actual (autoritativa/normalizada); fallback al guardado.
    matrix = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.lender == row.lender)
        .where(LenderWaiverMatrix.waiver_type == row.waiver_type)
    )
    if matrix is not None:
        docs = [d.document_name for d in sorted(matrix.documents, key=lambda d: d.position)]
    else:
        docs = list(row.documents_expected or [])

    items = await _match_documents(session, docs)
    found = sum(1 for it in items if it["found"])

    # Punto 5: evidencia adicional — archivos SharePoint relacionados con el
    # asunto del correo (propiedad / loan number), independiente de la matriz.
    email_row = None
    if row.production_email_id is not None:
        email_row = await session.get(ProductionEmail, row.production_email_id)
    if email_row is None:
        email_row = await session.scalar(
            select(ProductionEmail).where(ProductionEmail.message_id == row.message_id)
        )
    subject_matches = await _match_subject_documents(
        session, email_row.subject if email_row else ""
    )

    return {
        "lender": row.lender,
        "waiver_type": row.waiver_type,
        "total": len(items),
        "found": found,
        "missing": len(items) - found,
        "documents": items,
        "subject_matches": subject_matches,
    }


@app.get("/api/v1/documents/match")
async def documents_match(
    lender: str = Query(...),
    waiver_type: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    matrix = await session.scalar(
        select(LenderWaiverMatrix)
        .options(selectinload(LenderWaiverMatrix.documents))
        .where(LenderWaiverMatrix.lender == lender)
        .where(LenderWaiverMatrix.waiver_type == waiver_type)
    )
    if matrix is None:
        raise HTTPException(404, "No lender+waiver combination in the matrix")
    docs = [d.document_name for d in sorted(matrix.documents, key=lambda d: d.position)]
    items = await _match_documents(session, docs)
    found = sum(1 for it in items if it["found"])
    return {"lender": lender, "waiver_type": waiver_type, "total": len(items),
            "found": found, "missing": len(items) - found, "documents": items}


@app.get("/api/v1/documents/match-subject")
async def documents_match_subject(
    subject: str = Query(..., min_length=3),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Archivos SharePoint relacionados con un asunto de correo (punto 5)."""
    items = await _match_subject_documents(session, subject)
    return {"subject": subject, "total": len(items), "documents": items}
