"""
migrate_classifier_features.py -- Migracion in-place: columnas de features del
clasificador absorbidas de OGM_Lenders.

Agrega a email_classifications:
  secondary_issues (JSON), communication_category (VARCHAR),
  escalate_for_review (BOOL), suggested_attachments (JSON).

NO borra datos. Idempotente.

Uso:
    python -m scripts.migrate_classifier_features
"""
import asyncio

from rich.console import Console
from sqlalchemy import text

from app.db.database import engine

console = Console()

_ALTERS = [
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS secondary_issues JSON DEFAULT '[]'::json",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS communication_category VARCHAR(50) DEFAULT 'OPERATIONAL_WAIVER'",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS escalate_for_review BOOLEAN DEFAULT FALSE",
    "ALTER TABLE email_classifications ADD COLUMN IF NOT EXISTS suggested_attachments JSON DEFAULT '[]'::json",
]


async def main() -> None:
    console.print("\n[bold]migrate_classifier_features.py[/bold]\n")
    async with engine.begin() as conn:
        for sql in _ALTERS:
            await conn.execute(text(sql))
    console.print("[green]OK - 4 columnas aseguradas en email_classifications[/green]")
    console.print("\n[bold green]LISTO. Migracion aplicada (datos preservados).[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
