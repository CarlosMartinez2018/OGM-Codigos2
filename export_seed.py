"""
export_seed.py -- Exporta la configuracion de negocio desde PostgreSQL a JSON.

Genera los archivos semilla que consume seed_db.py, de modo que la matriz de
reglas (lender_waiver_matrix) y el mapeo de dominios (domain_lender_map) puedan
recargarse en un entorno limpio (produccion) sin perder informacion.

Salida:
    lender_waiver_matrix.json   (documents_expected como lista)
    domain_lender_map.json      (dict domain -> lender_name)

Uso:
    python export_seed.py
"""
import asyncio
import json
from pathlib import Path

from rich.console import Console
from sqlalchemy import text

from database import engine

console = Console()
BASE_DIR = Path(__file__).parent


def _split_documents(raw: str | None) -> list[str]:
    """Parte el texto de documentos por ';' en una lista limpia."""
    if not raw:
        return []
    parts = [piece.strip(" -\t") for piece in raw.split(";")]
    return [p for p in parts if p]


async def _export_matrix() -> int:
    rows = await _fetch(
        "SELECT lender, lender_aliases, waiver_type, triggers, "
        "evidence_required_ops, evidence_required_insurance, documents_expected, "
        "actions_to_automate, waiver_pack "
        "FROM lender_waiver_matrix ORDER BY id"
    )
    entries = []
    for r in rows:
        aliases = r["lender_aliases"]
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except Exception:
                aliases = []
        entries.append({
            "lender": r["lender"],
            "lender_aliases": aliases or [],
            "waiver_type": r["waiver_type"],
            "triggers": r["triggers"] or "",
            "evidence_required_ops": r["evidence_required_ops"] or "",
            "evidence_required_insurance": r["evidence_required_insurance"] or "",
            "documents_expected": _split_documents(r["documents_expected"]),
            "actions_to_automate": r["actions_to_automate"] or "",
            "waiver_pack": r["waiver_pack"] or "",
        })
    path = BASE_DIR / "lender_waiver_matrix.json"
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(entries)


async def _export_domain_map() -> int:
    rows = await _fetch("SELECT domain, lender_name FROM domain_lender_map ORDER BY id")
    data = {r["domain"]: r["lender_name"] for r in rows}
    path = BASE_DIR / "domain_lender_map.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(data)


async def _fetch(sql: str) -> list[dict]:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        keys = result.keys()
        return [dict(zip(keys, row)) for row in result]


async def main():
    console.print("\n[bold]export_seed.py -- Exportando configuracion BD -> JSON[/bold]\n")
    matrix_count = await _export_matrix()
    console.print(f"[green]OK - lender_waiver_matrix.json: {matrix_count} entradas[/green]")
    domain_count = await _export_domain_map()
    console.print(f"[green]OK - domain_lender_map.json: {domain_count} dominios[/green]")
    console.print("\n[bold green]LISTO. Archivos semilla regenerados.[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
