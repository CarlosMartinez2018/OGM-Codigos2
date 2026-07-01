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
from typing import Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session, engine, init_db
from models import (
    DomainLenderMap,
    EmailClassification,
    EmailReview,
    ProductionEmail,
)
import lender_approval
from llm_classifier import classifier


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
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(EmailClassification).order_by(EmailClassification.updated_at.desc().nullslast())
    if lender:
        stmt = stmt.where(EmailClassification.lender.ilike(f"%{lender}%"))
    if confidence_level:
        stmt = stmt.where(EmailClassification.confidence_level == confidence_level)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.limit(limit).offset(offset))).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_classification_to_dict(r) for r in rows]}


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
