"""
lender_approval.py -- Aprobar/rechazar lenders y re-clasificar su ventana.

Sin UI: funciones invocables desde codigo/tests. La UI (futura) las expone con
los botones aprobar/rechazar.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from app.services import preflight
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DomainLenderMap, EmailReview, ProductionEmail
from app.services.llm_classifier import classifier


async def reject_domain(session: AsyncSession, domain: str) -> None:
    domain = (domain or "").lower()
    await session.execute(
        update(DomainLenderMap)
        .where(DomainLenderMap.domain == domain)
        .values(status="NO_APROBADO")
    )
    await session.commit()


async def approve_domain(session: AsyncSession, domain: str) -> dict:
    domain = (domain or "").lower()
    row = await session.scalar(
        select(DomainLenderMap).where(DomainLenderMap.domain == domain)
    )
    if row is None:
        return {"domain": domain, "found": False, "reclassified": 0}

    await session.execute(
        update(DomainLenderMap)
        .where(DomainLenderMap.domain == domain)
        .values(status="APROBADO")
    )
    await session.commit()

    # Reprocesar TODOS los correos del dominio (sin ventana de fecha).
    emails = (await session.scalars(
        select(ProductionEmail).where(ProductionEmail.sender_domain == domain)
    )).all()

    # Marca sus reviews lender_* como gestionadas (solo si hay correos).
    if emails:
        await session.execute(
            update(EmailReview)
            .where(EmailReview.stage.in_(["lender_nuevo", "lender_por_aprobar"]))
            .where(EmailReview.message_id.in_([e.message_id for e in emails]))
            .values(status="GESTIONADO", resolved_at=datetime.now(timezone.utc))
        )
        await session.commit()

    # Re-clasifica esos correos con la KB actualizada (dominio ya APROBADO).
    kb = await classifier._load_business_data(session)
    groups = defaultdict(list)
    ed_by_id = {}
    for pe in emails:
        ed = classifier._production_to_email_data(pe)
        ed_by_id[pe.id] = ed
        groups[pe.case_id or pe.conversation_id or ed.conversation_id].append(ed)

    reclassified = 0
    for pe in emails:
        ed = ed_by_id[pe.id]
        case_id = pe.case_id or pe.conversation_id or ed.conversation_id
        pre = preflight.evaluate(ed, kb, groups[case_id])
        if not pre.passed:
            await classifier._save_review(session, pe, pre, case_id)
            await classifier._delete_classification(session, pe.message_id)
            continue
        result = await classifier.classify(ed, session, kb=kb)
        await classifier.save_classification(session, pe, result)
        await classifier._resolve_reviews(session, pe.message_id)
        reclassified += 1
    await session.commit()
    return {"domain": domain, "found": True, "reclassified": reclassified}
