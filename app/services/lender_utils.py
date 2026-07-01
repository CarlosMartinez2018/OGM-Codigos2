"""
lender_utils.py — Utilidades para identificar prestamistas y consultar la knowledge base.

Todas las funciones que necesitan datos los obtienen de PostgreSQL.
"""
from sqlalchemy import select

from app.db.database import async_session
from app.db.models import LenderWaiverMatrix, DomainLenderMap


# Dominios internos que no son prestamistas
_INTERNAL_DOMAINS = {
    "acentopartners.com",
    "captiveadvisorypartners.com",
}


async def get_domain_lender_map() -> dict[str, str]:
    """Carga el mapa dominio -> prestamista desde PostgreSQL."""
    async with async_session() as session:
        result = await session.execute(select(DomainLenderMap))
        rows = result.scalars().all()
        return {r.domain: r.lender_name for r in rows}


async def get_lender_waiver_matrix() -> list[dict]:
    """Carga la matriz completa desde PostgreSQL como lista de dicts."""
    async with async_session() as session:
        result = await session.execute(select(LenderWaiverMatrix))
        rows = result.scalars().all()
        return [
            {
                "lender": r.lender,
                "lender_aliases": r.lender_aliases or [],
                "waiver_type": r.waiver_type,
                "triggers": r.triggers,
                "evidence_required_ops": r.evidence_required_ops,
                "evidence_required_insurance": r.evidence_required_insurance,
                "documents_expected": r.documents_expected,
                "actions_to_automate": r.actions_to_automate,
                "waiver_pack": r.waiver_pack,
            }
            for r in rows
        ]


async def identify_lender_from_domains(
    from_domain: str,
    to_domains: list[str],
    cc_domains: list[str],
) -> tuple[str | None, str]:
    """
    Identify the lender from email domains.
    Priority: TO domain > CC domain > FROM domain.
    Returns (lender_name, source_hint).
    """
    domain_map = await get_domain_lender_map()

    # Check TO domains first (highest priority for response emails)
    for d in to_domains:
        if d in _INTERNAL_DOMAINS:
            continue
        if d in domain_map:
            return domain_map[d], f"TO domain: {d}"

    # Check CC domains
    for d in cc_domains:
        if d in _INTERNAL_DOMAINS:
            continue
        if d in domain_map:
            return domain_map[d], f"CC domain: {d}"

    # Check FROM domain last
    if from_domain and from_domain not in _INTERNAL_DOMAINS:
        if from_domain in domain_map:
            return domain_map[from_domain], f"FROM domain: {from_domain}"

    return None, "no domain match"


async def get_knowledge_base_text() -> str:
    """Generate a formatted knowledge base text for the LLM prompt."""
    matrix = await get_lender_waiver_matrix()
    lines = ["=== LENDER/WAIVER CLASSIFICATION KNOWLEDGE BASE ===\n"]

    for i, entry in enumerate(matrix, 1):
        lines.append(f"--- Entry {i} ---")
        lines.append(f"Lender: {entry['lender']}")
        lines.append(f"Also known as: {', '.join(entry['lender_aliases'])}")
        lines.append(f"Waiver Type: {entry['waiver_type']}")
        lines.append(f"Triggers: {entry['triggers']}")
        lines.append(f"Evidence Required (Ops): {entry['evidence_required_ops']}")
        lines.append(f"Evidence Required (Insurance): {entry['evidence_required_insurance']}")
        lines.append(f"Documents Expected: {entry['documents_expected']}")
        lines.append(f"WaiverPack: {entry['waiver_pack']}")
        lines.append(f"Actions to Automate: {entry['actions_to_automate']}")
        lines.append("")

    return "\n".join(lines)


async def get_lender_names() -> list[str]:
    """Return unique lender names."""
    matrix = await get_lender_waiver_matrix()
    return list({e["lender"] for e in matrix})


async def get_waiver_types() -> list[str]:
    """Return unique waiver types."""
    matrix = await get_lender_waiver_matrix()
    return [e["waiver_type"] for e in matrix]


async def find_matching_entry(lender: str, waiver_type: str) -> dict | None:
    """Find the knowledge base entry matching a lender and waiver type."""
    matrix = await get_lender_waiver_matrix()
    lender_lower = lender.lower()
    waiver_lower = waiver_type.lower()

    for entry in matrix:
        lender_match = (
            lender_lower in entry["lender"].lower()
            or any(lender_lower in alias.lower() for alias in entry["lender_aliases"])
        )
        waiver_match = waiver_lower in entry["waiver_type"].lower()

        if lender_match and waiver_match:
            return entry

    # Partial match: try lender only
    for entry in matrix:
        lender_match = (
            lender_lower in entry["lender"].lower()
            or any(lender_lower in alias.lower() for alias in entry["lender_aliases"])
        )
        if lender_match:
            return entry

    return None
