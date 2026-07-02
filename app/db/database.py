"""
database.py — Motor async de SQLAlchemy para PostgreSQL.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Columnas agregadas despues de la creacion inicial de la tabla. create_all NO
# altera tablas existentes; las aplicamos idempotentemente para que la BD dev
# existente se auto-migre al arrancar (prod limpia ya las tiene via models.py).
_ADDITIVE_COLUMNS = [
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'classified'",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(200)",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS corrected_lender VARCHAR(200)",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS corrected_waiver_type VARCHAR(200)",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS correction_notes TEXT",
]


async def init_db():
    """Crea todas las tablas y aplica columnas aditivas idempotentes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in _ADDITIVE_COLUMNS:
            await conn.execute(text(sql))


async def drop_all():
    """Elimina TODAS las tablas de la base de datos."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
