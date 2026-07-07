"""Tests del match SharePoint por asunto del correo (punto 5)."""
from app.main import _doc_tokens, _subject_tokens


def test_subject_tokens_drop_email_noise():
    toks = _subject_tokens("FW: [EXTERNAL] Second Notice of Non-Compliance - Loan Number 402111226")
    assert "fw" not in toks and "external" not in toks
    assert "notice" not in toks and "loan" not in toks
    assert "402111226" in toks


def test_subject_tokens_keep_property_names():
    toks = _subject_tokens("RE: 202041800 - Burnam Woods Apartments - Acento Real Estate Partners, LLC")
    assert "burnam" in toks and "woods" in toks and "202041800" in toks
    assert "llc" not in toks and "re" not in toks


def test_subject_tokens_empty():
    assert _subject_tokens("") == []
    assert _subject_tokens("FW: RE: external") == []


# --- criterio de match (replica la semantica de _match_subject_documents) -----

def _matches(subject: str, filename: str) -> bool:
    tokens = set(_subject_tokens(subject))
    ftoks = set(_doc_tokens(filename))
    hits = tokens & ftoks
    if not hits:
        return False
    strong = any(t.isdigit() and len(t) >= 5 for t in hits)
    return len(hits) >= 2 or strong


def test_loan_number_alone_is_strong_match():
    assert _matches(
        "FW: Insurance coverage deficiency identified for Loan # 010293383",
        "Loan 010293383 - Evidence of Property.pdf",
    )


def test_property_name_two_tokens_match():
    assert _matches(
        "RE: Burnam Woods Apartments - waiver",
        "Burnam Woods - SOV 2026.xlsx",
    )


def test_single_weak_token_is_not_enough():
    assert not _matches(
        "RE: Apartments waiver",
        "Maple Ridge Apartments - ACORD 25.pdf",
    )


def test_unrelated_file_no_match():
    assert not _matches(
        "FW: Hunters Crossing Carlyle Landing PROP GL AUTO",
        "Sunset Gardens - Equipment Breakdown.pdf",
    )
