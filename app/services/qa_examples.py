"""
qa_examples.py -- Entrenamiento continuo con preguntas y respuestas del operador.

Cada aprobacion o correccion de una clasificacion en la UI se persiste como un
ejemplo verificado (correo -> lender/waiver correcto). El clasificador los usa
de dos formas:
  1. Retrieval por similitud (modo reglas): si el correo nuevo se parece mucho
     a un ejemplo confirmado y las reglas estan inseguras, se adopta el waiver
     del ejemplo (validado despues contra la matriz).
  2. Few-shot en el prompt del LLM: los N ejemplos mas parecidos van al prompt.

Honesto por diseno: esto NO es fine-tuning del modelo; es aprendizaje por
recuperacion de casos confirmados. Mejora con cada aprobacion/correccion.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClassifierQaExample, ProductionEmail
from app.schemas import EmailData

# Cuanto cuerpo se guarda por ejemplo (suficiente contexto, poco peso en BD/prompt).
_EXCERPT_LEN = 1200


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


async def record_example(
    session: AsyncSession,
    message_id: str,
    lender: str,
    waiver_type: str,
    source: str,
    notes: Optional[str] = None,
    email: Optional[ProductionEmail] = None,
) -> None:
    """Upsert del ejemplo confirmado. Un correo = un ejemplo (el ultimo gana:
    una correccion posterior pisa la aprobacion previa)."""
    if not message_id or not lender or lender == "UNKNOWN":
        return
    if email is None:
        email = await session.scalar(
            select(ProductionEmail).where(ProductionEmail.message_id == message_id)
        )
    stmt = pg_insert(ClassifierQaExample).values(
        message_id=message_id,
        subject=(email.subject if email else "") or "",
        body_excerpt=((email.body_text if email else "") or "")[:_EXCERPT_LEN],
        sender_domain=(email.sender_domain if email else "") or "",
        lender=lender,
        waiver_type=waiver_type,
        source=source,
        notes=notes,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["message_id"],
        set_={
            "lender": stmt.excluded.lender,
            "waiver_type": stmt.excluded.waiver_type,
            "source": stmt.excluded.source,
            "notes": stmt.excluded.notes,
        },
    )
    await session.execute(stmt)


def rank_examples(
    email: EmailData,
    rows: list[ClassifierQaExample],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Ejemplos ordenados por similitud con el correo (subject+body, bonus dominio)."""
    text = _normalize(f"{email.subject} {(email.body_text or '')[:_EXCERPT_LEN]}")
    scored: list[tuple[float, ClassifierQaExample]] = []
    for row in rows:
        candidate = _normalize(f"{row.subject} {row.body_excerpt}")
        score = _similarity(text[:1200], candidate[:1200])
        if row.sender_domain and row.sender_domain == email.sender_domain:
            score += 0.10
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "message_id": row.message_id,
            "subject": row.subject,
            "lender": row.lender,
            "waiver_type": row.waiver_type,
            "source": row.source,
            "similarity": round(score, 3),
        }
        for score, row in scored[:limit]
        if score > 0.0
    ]


async def similar_examples(
    session: AsyncSession,
    email: EmailData,
    limit: int = 5,
    rows: Optional[list[ClassifierQaExample]] = None,
) -> list[dict[str, Any]]:
    if rows is None:
        rows = (await session.scalars(
            select(ClassifierQaExample)
            .order_by(ClassifierQaExample.updated_at.desc())
            .limit(500)
        )).all()
    return rank_examples(email, list(rows), limit=limit)
