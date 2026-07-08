"""
migrate_db.py — Copia la BD local completa a otra instancia Postgres.

Uso:
    python -m scripts.migrate_db --target "postgresql+asyncpg://user:pass@host:5432/acento?ssl=require"

- Crea el esquema en destino (create_all, no destructivo).
- Copia todas las tablas en orden de dependencias, preservando ids.
- Ajusta las secuencias de PK enteras al max(id) copiado.
- Idempotente por tabla: si el destino ya tiene filas, la tabla se salta
  (para forzar recopia, vaciar la tabla destino primero).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base, engine as source_engine
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
    TrainingEmail,
)

sys.stdout.reconfigure(encoding="utf-8")

# Orden respeta FKs: matriz antes que documentos; correos antes que
# clasificaciones/reviews.
TABLES = [
    DomainLenderMap,
    LenderWaiverMatrix,
    LenderWaiverDocument,
    ProductionEmail,
    TrainingEmail,
    EmailClassification,
    EmailReview,
    SharePointFile,
    AppSetting,
    ClassifierQaExample,
]

BATCH = 200


def _row_dict(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


async def migrate(target_url: str) -> int:
    target_engine = create_async_engine(target_url, echo=False)
    source_session = async_sessionmaker(source_engine, expire_on_commit=False)
    target_session = async_sessionmaker(target_engine, expire_on_commit=False)

    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Esquema creado/verificado en destino.")

    total = 0
    for model in TABLES:
        name = model.__tablename__
        async with source_session() as src, target_session() as dst:
            existing = await dst.scalar(select(func.count()).select_from(model))
            if existing:
                print(f"  {name:28} SKIP (destino ya tiene {existing} filas)")
                continue
            rows = (await src.scalars(select(model))).all()
            if not rows:
                print(f"  {name:28} 0 filas")
                continue
            for i in range(0, len(rows), BATCH):
                dst.add_all(model(**_row_dict(r)) for r in rows[i:i + BATCH])
                await dst.flush()
            await dst.commit()
            print(f"  {name:28} {len(rows)} filas copiadas")
            total += len(rows)

            # Reajustar secuencia si la PK es entera autoincremental.
            pk = list(model.__table__.primary_key.columns)[0]
            if pk.autoincrement is True or (
                pk.type.python_type is int and pk.name == "id"
            ):
                async with target_engine.begin() as conn:
                    await conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{name}', '{pk.name}'), "
                        f"(SELECT COALESCE(MAX({pk.name}), 1) FROM {name}))"
                    ))

    await target_engine.dispose()
    await source_engine.dispose()
    print(f"\nMigracion completa: {total} filas.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="URL SQLAlchemy asyncpg del Postgres destino")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(migrate(args.target)))
