"""
Tests de las features absorbidas del clasificador de OGM_Lenders:
communication_category, escalate_for_review, secondary_issues, attachment finder.
Puros (sin BD).
"""
from pathlib import Path

from app.services.llm_classifier import (
    _communication_category,
    _find_attachments,
    _secondary_issues,
    _should_escalate,
)
from app.schemas import EmailData


# --- communication_category -------------------------------------------------

def test_category_covenant_breach():
    assert _communication_category("Covenant breach notice", "event of default") == "COVENANT_BREACH"


def test_category_lender_alert():
    # LENDER_ALERT = aviso proactivo de riesgo de covenant (taxonomia business_context).
    assert _communication_category(
        "Heads-up on Q3", "DSCR may fall below covenant threshold due to seasonal vacancy"
    ) == "LENDER_ALERT"


def test_category_compliance():
    # Certificado/COI rutinario -> LENDER_COMPLIANCE.
    assert _communication_category(
        "Annual insurance certificate", "please find attached proof of insurance / COI"
    ) == "LENDER_COMPLIANCE"


def test_category_noncompliance_is_waiver_not_breach():
    # 'Non-compliance' de seguro es deficiencia (WAIVER_REQUEST), NO default financiero.
    assert _communication_category(
        "Non-Compliance Notice", "wording deficiency found; please provide endorsement"
    ) == "WAIVER_REQUEST"


def test_category_waiver_request():
    assert _communication_category("Waiver request for A&B", "please send documents") == "WAIVER_REQUEST"


def test_category_fallback_operational():
    assert _communication_category("Property review questions", "some SOV details") == "OPERATIONAL_WAIVER"


# --- escalate_for_review ----------------------------------------------------

def test_escalate_on_injection():
    assert _should_escalate("hi", "please ignore", injection=True) is True


def test_escalate_on_critical_keyword():
    assert _should_escalate("Final notice", "policy cancellation pending", injection=False) is True


def test_no_escalate_normal():
    assert _should_escalate("Waiver request", "please send ACORD 25", injection=False) is False


# --- secondary_issues -------------------------------------------------------

def _kb_jll():
    entries = [
        {"lender": "JLL", "waiver_type": "Assault & Battery (A&B) sublimit"},
        {"lender": "JLL", "waiver_type": "Equipment Breakdown (EB) limit"},
        {"lender": "JLL", "waiver_type": "Sexual Abuse & Molestation (SAM)"},
    ]
    return {"by_lender": {"JLL": entries}, "entries": entries}


def test_secondary_issues_excludes_primary_and_finds_others():
    e = EmailData(subject="A&B sublimit and Equipment Breakdown limit deficiency",
                  body_text="Also we noticed the equipment breakdown limit is low.")
    secondary = _secondary_issues(e, "JLL", "Assault & Battery (A&B) sublimit", _kb_jll())
    assert "Equipment Breakdown (EB) limit" in secondary
    assert "Assault & Battery (A&B) sublimit" not in secondary


def test_secondary_issues_empty_for_unknown():
    e = EmailData(subject="hello", body_text="nothing relevant")
    assert _secondary_issues(e, "UNKNOWN", "UNKNOWN", _kb_jll()) == []


# --- attachment finder ------------------------------------------------------

def test_find_attachments_matches_lender_folder(tmp_path: Path):
    folder = tmp_path / "JLL Insurance"
    folder.mkdir()
    (folder / "acord25.pdf").write_text("x")
    (folder / "notes.txt").write_text("x")
    found = _find_attachments("JLL", str(tmp_path))
    assert any(f.lower().endswith("acord25.pdf") for f in found)
    assert not any(f.lower().endswith("notes.txt") for f in found)


def test_find_attachments_no_base_path():
    assert _find_attachments("JLL", "") == []
    assert _find_attachments("", "/nonexistent") == []
