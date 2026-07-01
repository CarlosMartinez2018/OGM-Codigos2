"""
migrate_documents.py -- Migracion in-place para normalizar documents_expected.

Pensado para una BD de desarrollo que YA tiene datos (production_emails,
training_emails, matriz, etc.) y que NO debe vaciarse. A diferencia de
seed_db.py, este script no hace DROP de las tablas: solo aplica los cambios
de esquema necesarios.

Pasos:
  1. Crea la tabla lender_waiver_documents (si no existe).
  2. Rellena lender_waiver_documents partiendo lender_waiver_matrix.documents_expected
     (texto separado por ';') -- solo si la tabla hija esta vacia.
  3. Elimina la columna lender_waiver_matrix.documents_expected (ya normalizada).
  4. Convierte email_classifications.documents_expected de TEXT a JSON.

Es idempotente: puede correrse varias veces sin romper nada.

Uso:
    python migrate_documents.py
"""
import asyncio

from rich.console import Console
from sqlalchemy import text

from database import engine, init_db
import models  # noqa: F401 -- registra las tablas en Base.metadata para create_all

console = Console()


async def _column_exists(conn, table: str, column: str) -> bool:
    row = await conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return row.first() is not None


async def _column_type(conn, table: str, column: str) -> str | None:
    row = await conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    found = row.first()
    return found[0] if found else None


async def main():
    console.print("\n[bold]migrate_documents.py -- Normalizando documents_expected[/bold]\n")

    # 1. Crear tablas faltantes (incluye lender_waiver_documents). No borra nada.
    await init_db()
    console.print("[green]OK - lender_waiver_documents asegurada (create_all)[/green]")

    async with engine.begin() as conn:
        # 2. Backfill desde el texto actual, solo si la hija esta vacia
        #    y la columna origen aun existe.
        child_count = (await conn.execute(
            text("SELECT count(*) FROM lender_waiver_documents")
        )).scalar()
        has_old_col = await _column_exists(conn, "lender_waiver_matrix", "documents_expected")

        if child_count == 0 and has_old_col:
            matrix = await conn.execute(text(
                "SELECT id, documents_expected FROM lender_waiver_matrix ORDER BY id"
            ))
            inserted = 0
            for row in matrix:
                raw = row[1] or ""
                docs = [d.strip(" -\t") for d in raw.split(";") if d.strip()]
                for idx, doc in enumerate(docs):
                    await conn.execute(text(
                        "INSERT INTO lender_waiver_documents "
                        "(lender_waiver_id, document_name, position) "
                        "VALUES (:lw, :doc, :pos)"
                    ), {"lw": row[0], "doc": doc, "pos": idx})
                    inserted += 1
            console.print(f"[green]OK - backfill: {inserted} documentos insertados[/green]")
        else:
            console.print(
                f"[yellow]Backfill omitido (hija tiene {child_count} filas, "
                f"columna origen existe={has_old_col})[/yellow]"
            )

        # 3. Eliminar la columna ya normalizada en la matriz.
        if has_old_col:
            await conn.execute(text(
                "ALTER TABLE lender_waiver_matrix DROP COLUMN documents_expected"
            ))
            console.print("[green]OK - columna lender_waiver_matrix.documents_expected eliminada[/green]")

        # 4. email_classifications.documents_expected TEXT -> JSON.
        ec_type = await _column_type(conn, "email_classifications", "documents_expected")
        if ec_type and ec_type != "json":
            await conn.execute(text(
                "ALTER TABLE email_classifications "
                "ALTER COLUMN documents_expected TYPE json "
                "USING to_json(COALESCE("
                "string_to_array(NULLIF(documents_expected, ''), '; '), "
                "ARRAY[]::text[]))"
            ))
            await conn.execute(text(
                "ALTER TABLE email_classifications "
                "ALTER COLUMN documents_expected SET DEFAULT '[]'::json"
            ))
            console.print("[green]OK - email_classifications.documents_expected -> JSON[/green]")
        else:
            console.print(f"[yellow]email_classifications.documents_expected ya es JSON ({ec_type})[/yellow]")

    console.print("\n[bold green]LISTO. Migracion aplicada (correos preservados).[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
