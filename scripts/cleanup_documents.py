"""
cleanup_documents.py -- Deja solo nombres de documento en lender_waiver_documents.

Curado aprobado por negocio: borra filas que son accion/descripcion (no documento),
limpia coletillas ("(if applicable)", "if requested"...) y fusiona duplicados.
Aplica a la BD (in-place) y a data/lender_waiver_matrix.json. Idempotente.

Uso:  python -m scripts.cleanup_documents
"""
import asyncio
import json
from pathlib import Path

from rich.console import Console
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import async_session, engine
from app.db.models import LenderWaiverMatrix, LenderWaiverDocument

console = Console()
JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "lender_waiver_matrix.json"

# Filas que NO son documentos (accion/descripcion) -> borrar.
DROP = {
    "ai clause fix",
    "copy of standalone sam policy or specimen",
    "evidence of change if wording was wrong",
    "explanation mapping lender ask to policy design",
    "note of correction",
    "split gl vs umbrella on invoice",
    "statement that full policies will be delivered within 90 days",
}

# Limpieza de coletillas / fusion de duplicados (clave en minuscula -> nombre canonico).
RENAME = {
    "eb endorsement (if eb deficiency)": "EB endorsement",
    "master program questionnaire (if applicable)": "Master Program Questionnaire",
    "paid receipt if requested": "paid receipt",
    "underwriter correspondence if available": "underwriter correspondence",
    "corrected cois": "COI",
    "sov address excerpt": "SOV",
    "sov excerpt": "SOV",
    "declination list": "declination letters",
    "acord 28 (property)": "ACORD 28",
}


def _clean(docs: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for d in docs:
        k = d.strip().lower()
        if k in DROP:
            continue
        name = RENAME.get(k, d.strip())
        kk = name.lower()
        if kk not in seen:
            seen.add(kk)
            out.append(name)
    return out


async def main() -> None:
    console.print("\n[bold]cleanup_documents[/bold]\n")
    before = after = 0
    async with async_session() as session:
        rows = (await session.scalars(
            select(LenderWaiverMatrix).options(selectinload(LenderWaiverMatrix.documents))
        )).all()
        for lw in rows:
            docs = [d.document_name for d in sorted(lw.documents, key=lambda d: d.position)]
            before += len(docs)
            clean = _clean(docs)
            after += len(clean)
            lw.documents = [LenderWaiverDocument(document_name=n, position=i)
                            for i, n in enumerate(clean)]
        await session.commit()
    console.print(f"[green]OK BD - {before} -> {after} filas[/green]")

    if JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for entry in data:
            entry["documents_expected"] = _clean(entry.get("documents_expected") or [])
        JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print("[green]OK JSON - data/lender_waiver_matrix.json[/green]")

    console.print("\n[bold green]LISTO.[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
