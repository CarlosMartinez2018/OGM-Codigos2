"""
migrate_preflight.py -- Migracion in-place para el pipeline de pre-filtrado.

NO borra datos (a diferencia de seed_db.py). Agrega columnas a domain_lender_map
y production_emails, crea email_reviews, y siembra estados iniciales.
Idempotente.

Uso:
    python migrate_preflight.py
"""
import asyncio

from rich.console import Console
from sqlalchemy import text

from database import engine, init_db
import models  # noqa: F401 -- registra tablas en Base.metadata

console = Console()

NOISE_DOMAINS = ["teams.mail.microsoft", "proofpointessentials.com", "microsoft.com"]


async def _col_exists(conn, table, column):
    r = await conn.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return r.first() is not None


async def main():
    console.print("\n[bold]migrate_preflight.py[/bold]\n")

    # Crea tablas faltantes (email_reviews). No borra nada.
    await init_db()
    console.print("[green]OK - email_reviews asegurada[/green]")

    async with engine.begin() as conn:
        # domain_lender_map.status / created_at
        if not await _col_exists(conn, "domain_lender_map", "status"):
            await conn.execute(text(
                "ALTER TABLE domain_lender_map ADD COLUMN status VARCHAR(20) "
                "NOT NULL DEFAULT 'POR_APROBAR'"
            ))
        if not await _col_exists(conn, "domain_lender_map", "created_at"):
            await conn.execute(text(
                "ALTER TABLE domain_lender_map ADD COLUMN created_at TIMESTAMPTZ "
                "NOT NULL DEFAULT now()"
            ))
        # Los dominios ya existentes son lenders validos (el ruido no esta aun
        # en la tabla; se inserta como NO_APROBADO en el paso siguiente).
        await conn.execute(text(
            "UPDATE domain_lender_map SET status='APROBADO' WHERE status='POR_APROBAR'"
        ))
        # Dominios ruido -> blacklist. Upsert (sobrescribe a NO_APROBADO si existieran).
        for d in NOISE_DOMAINS:
            await conn.execute(text(
                "INSERT INTO domain_lender_map (domain, lender_name, status, created_at) "
                "VALUES (:d, :n, 'NO_APROBADO', now()) "
                "ON CONFLICT (domain) DO UPDATE SET status='NO_APROBADO'"
            ), {"d": d, "n": d})
        console.print("[green]OK - domain_lender_map: status/created_at + ruido[/green]")

        # production_emails.case_id
        if not await _col_exists(conn, "production_emails", "case_id"):
            await conn.execute(text(
                "ALTER TABLE production_emails ADD COLUMN case_id VARCHAR(500) DEFAULT ''"
            ))
        await conn.execute(text(
            "UPDATE production_emails SET case_id = conversation_id "
            "WHERE case_id IS NULL OR case_id = ''"
        ))
        console.print("[green]OK - production_emails.case_id relleno[/green]")

    console.print("\n[bold green]LISTO. Migracion aplicada (correos preservados).[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
