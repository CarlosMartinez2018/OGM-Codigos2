"""
normalize_documents.py -- Normaliza documents_expected a filas atomicas.

Reescribe lender_waiver_documents en la BD (in-place, sin borrar correos) y
normaliza data/lender_waiver_matrix.json (fuente para prod limpia). Idempotente.

Uso (desde la raiz):
    python -m scripts.normalize_documents
"""
import asyncio
import json
from pathlib import Path

from rich.console import Console
from sqlalchemy import select

from app.db.database import async_session, engine
from app.db.models import LenderWaiverMatrix, LenderWaiverDocument
from app.services.doc_normalize import normalize_documents

console = Console()
JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "lender_waiver_matrix.json"


async def _normalize_db() -> tuple[int, int]:
    before = after = 0
    async with async_session() as session:
        from sqlalchemy.orm import selectinload
        rows = (await session.scalars(
            select(LenderWaiverMatrix).options(selectinload(LenderWaiverMatrix.documents))
        )).all()
        for lw in rows:
            docs = [d.document_name for d in sorted(lw.documents, key=lambda d: d.position)]
            before += len(docs)
            norm = normalize_documents(docs)
            after += len(norm)
            # reemplaza las filas hijas
            lw.documents = [
                LenderWaiverDocument(document_name=name, position=i)
                for i, name in enumerate(norm)
            ]
        await session.commit()
    return before, after


def _normalize_json() -> None:
    if not JSON_PATH.exists():
        console.print(f"[yellow]JSON no encontrado: {JSON_PATH}[/yellow]")
        return
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    for entry in data:
        docs = entry.get("documents_expected") or []
        if isinstance(docs, str):
            docs = [docs]
        entry["documents_expected"] = normalize_documents(docs)
    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def main() -> None:
    console.print("\n[bold]normalize_documents[/bold]\n")
    before, after = await _normalize_db()
    console.print(f"[green]OK BD - lender_waiver_documents: {before} -> {after} filas[/green]")
    _normalize_json()
    console.print("[green]OK JSON - data/lender_waiver_matrix.json normalizado[/green]")
    console.print("\n[bold green]LISTO.[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
