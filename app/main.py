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

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.database import async_session, engine, init_db
from app.db.models import (
    DomainLenderMap,
    EmailClassification,
    EmailReview,
    LenderWaiverDocument,
    LenderWaiverMatrix,
    ProductionEmail,
)
from app.services import lender_approval
from app.services.llm_classifier import classifier


# ---------------------------------------------------------------------------
# Cuerpos de peticion (Pydantic)
# ---------------------------------------------------------------------------

class CorrectionIn(BaseModel):
    corrected_lender: str
    corrected_waiver_type: str
    reviewed_by: str = "operator"
    notes: Optional[str] = None


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


def _review_to_dict(row: EmailReview) -> dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "case_id": row.case_id,
        "stage": row.stage,
        "reason": row.reason,
        "detected_original_sender": row.detected_original_sender,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
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
    }


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
        raise HTTPException(404, f"Dominio no encontrado en domain_lender_map: {domain}")
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
        raise HTTPException(404, "Correo no encontrado")
    return _email_detail_dict(row)


# ---------------------------------------------------------------------------
# Cola de revision manual (email_reviews)
# ---------------------------------------------------------------------------

@app.get("/api/v1/reviews")
async def list_reviews(
    stage: Optional[str] = None,
    status: str = Query(default="PENDIENTE", description="PENDIENTE|GESTIONADO"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(EmailReview).order_by(EmailReview.created_at.desc().nullslast())
    if status:
        stmt = stmt.where(EmailReview.status == status.upper())
    if stage:
        stmt = stmt.where(EmailReview.stage == stage)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.limit(limit).offset(offset))).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_review_to_dict(r) for r in rows]}


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
        raise HTTPException(404, "Clasificacion no encontrada")

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
        raise HTTPException(404, "Clasificacion no encontrada")
    row.status = "reviewed"
    row.reviewed_by = reviewed_by
    row.updated_at = datetime.now(timezone.utc)
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
        raise HTTPException(404, "Clasificacion no encontrada")

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

    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return _classification_to_dict(row)


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
        raise HTTPException(409, "Ya existe un waiver con ese lender + waiver_type")
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
        raise HTTPException(404, "Waiver no encontrado")
    conflict = await session.scalar(
        select(LenderWaiverMatrix.id)
        .where(LenderWaiverMatrix.lender == body.lender.strip())
        .where(LenderWaiverMatrix.waiver_type == body.waiver_type.strip())
        .where(LenderWaiverMatrix.id != waiver_id)
    )
    if conflict:
        raise HTTPException(409, "Otro waiver ya usa ese lender + waiver_type")
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
        raise HTTPException(404, "Waiver no encontrado")
    await session.delete(row)
    await session.commit()
