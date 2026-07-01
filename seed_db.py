"""
seed_db.py — Limpia PostgreSQL y siembra datos iniciales desde los archivos JSON.

Uso:
    python seed_db.py
"""
import asyncio
import json
from pathlib import Path

from rich.console import Console
from sqlalchemy import text, select, func

from database import engine, async_session, Base, drop_all, init_db
from models import LenderWaiverMatrix, LenderWaiverDocument, DomainLenderMap

console = Console()
BASE_DIR = Path(__file__).parent


async def _clean_postgres():
    """Elimina TODAS las tablas y objetos del schema public."""
    console.print("[bold red]Limpiando PostgreSQL...[/bold red]")
    async with engine.begin() as conn:
        # Drop all known model tables
        await conn.run_sync(Base.metadata.drop_all)
        # Also drop any other leftover tables
        await conn.execute(text(
            "DO $$ DECLARE r RECORD; "
            "BEGIN FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') "
            "LOOP EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE'; "
            "END LOOP; END $$;"
        ))
    console.print("[green]OK - Base de datos limpia[/green]")


async def _create_tables():
    """Crea todas las tablas definidas en models.py."""
    console.print("[bold blue]Creando tablas...[/bold blue]")
    await init_db()
    console.print("[green]OK - Tablas creadas: lender_waiver_matrix, domain_lender_map, production_emails, training_emails[/green]")


async def _seed_lender_waiver_matrix():
    """Carga lender_waiver_matrix.json en la tabla correspondiente."""
    json_path = BASE_DIR / "lender_waiver_matrix.json"
    if not json_path.exists():
        console.print(f"[yellow]WARN - No se encontró {json_path.name}, saltando...[/yellow]")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session() as session:
        for entry in data:
            row = LenderWaiverMatrix(
                lender=entry["lender"],
                lender_aliases=entry.get("lender_aliases", []),
                waiver_type=entry["waiver_type"],
                triggers=entry.get("triggers", ""),
                evidence_required_ops=entry.get("evidence_required_ops", ""),
                evidence_required_insurance=entry.get("evidence_required_insurance", ""),
                actions_to_automate=entry.get("actions_to_automate", ""),
                waiver_pack=entry.get("waiver_pack", ""),
            )
            # documents_expected: lista normalizada (1 -> muchos).
            documents = entry.get("documents_expected") or []
            if isinstance(documents, str):
                documents = [d.strip(" -\t") for d in documents.split(";") if d.strip()]
            row.documents = [
                LenderWaiverDocument(document_name=doc, position=idx)
                for idx, doc in enumerate(documents)
                if doc
            ]
            session.add(row)
        await session.commit()

        count = await session.scalar(select(func.count()).select_from(LenderWaiverMatrix))
        doc_count = await session.scalar(select(func.count()).select_from(LenderWaiverDocument))
        console.print(
            f"[green]OK - lender_waiver_matrix: {count} registros, "
            f"lender_waiver_documents: {doc_count} documentos[/green]"
        )


async def _seed_domain_lender_map():
    """Carga domain_lender_map.json en la tabla correspondiente."""
    json_path = BASE_DIR / "domain_lender_map.json"
    if not json_path.exists():
        console.print(f"[yellow]WARN - No se encontró {json_path.name}, saltando...[/yellow]")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session() as session:
        for domain, lender_name in data.items():
            row = DomainLenderMap(domain=domain, lender_name=lender_name)
            session.add(row)
        await session.commit()

        count = await session.scalar(select(func.count()).select_from(DomainLenderMap))
        console.print(f"[green]OK - domain_lender_map: {count} registros insertados[/green]")


async def main():
    console.print("\n[bold]seed_db.py — Inicialización de PostgreSQL[/bold]\n")

    await _clean_postgres()
    await _create_tables()
    await _seed_lender_waiver_matrix()
    await _seed_domain_lender_map()

    console.print("\n[bold green]LISTO. Base de datos lista.[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
