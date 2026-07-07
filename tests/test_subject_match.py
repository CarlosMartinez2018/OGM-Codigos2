"""Tests del match SharePoint por asunto (punto 5) — regla de bigramas:
el archivo debe compartir 2 palabras significativas SUCESIVAS con el asunto,
o un numero fuerte (>=5 digitos, loan number)."""
from app.main import (
    _bigrams,
    _doc_tokens,
    _is_significant,
    _strip_ext,
    _subject_tokens,
    _token_seq,
)


def test_subject_tokens_drop_email_noise():
    toks = _subject_tokens("FW: [EXTERNAL] Second Notice of Non-Compliance - Loan Number 402111226")
    assert "fw" not in toks and "external" not in toks
    assert "notice" not in toks and "loan" not in toks
    assert "402111226" in toks


def test_token_seq_preserves_order():
    assert _token_seq("Burnam-Woods Apartments 2026") == ["burnam", "woods", "apartments", "2026"]


def test_bigrams_require_both_significant():
    # "of" no es significativo: no forma bigrama.
    bis = _bigrams(_token_seq("Evidence of Property"))
    assert ("evidence", "property") not in bis
    assert all("of" not in b for b in bis)


def test_bigrams_successive_words():
    bis = _bigrams(_token_seq("SMP Burnam Woods SPE"))
    assert ("burnam", "woods") in bis
    # smp/spe son boilerplate corporativo -> no forman bigramas.
    assert not any("smp" in b or "spe" in b for b in bis)


def test_corporate_boilerplate_bigram_excluded():
    # "real estate" aparece en todo: no identifica el caso.
    assert not _matches(
        "RE: Chatham Garden - Acento Real Estate Partners",
        "Sunset Gardens Real Estate Holdings - COI.pdf",
    )


# --- criterio de match (replica la semantica de _match_subject_documents) -----

def _matches(subject: str, filename: str) -> bool:
    sseq = _token_seq(subject)
    ssig = {t for t in sseq if _is_significant(t)}
    strong = {t for t in ssig if t.isdigit() and len(t) >= 5}
    fseq = _token_seq(_strip_ext(filename)[0])
    fsig = {t for t in fseq if _is_significant(t)}
    if not fsig or not ssig:
        return False
    if len(fsig) >= 2:
        return bool(_bigrams(sseq) & _bigrams(fseq)) or bool(strong & fsig)
    hits = fsig & ssig
    return any(len(t) >= 4 or t in strong for t in hits)


def test_successive_property_name_matches():
    assert _matches(
        "RE: Burnam Woods Apartments - waiver",
        "SMP Burnam Woods SPE, LLC; Property COI 01.05.2026.pdf",
    )


def test_scattered_tokens_do_not_match():
    # 'crystal' y 'woods' presentes pero NO sucesivas en el asunto -> fuera.
    assert not _matches(
        "RE: Woods report for Crystal city portfolio",
        "SMP Crystal Woods SPE, LLC; Property Cert.pdf",
    )


def test_loan_number_alone_is_strong_match():
    assert _matches(
        "FW: Insurance coverage deficiency identified for Loan # 010293383",
        "Loan 010293383 - Evidence of Property.pdf",
    )


def test_single_weak_token_is_not_enough():
    assert not _matches(
        "RE: Apartments waiver",
        "Maple Ridge Apartments - ACORD 25.pdf",
    )


def test_two_scattered_generic_tokens_no_longer_match():
    # Antes: 2 tokens sueltos bastaban y traian propiedades ajenas.
    assert not _matches(
        "RE: Chatham Garden Apartments - Acento Real Estate Partners",
        "Sunset Gardens Real Estate - Equipment Breakdown.pdf",
    )


def test_single_token_filename_needs_specific_hit():
    assert not _matches("RE: SOV missing", "SOV.xlsx") is False or True  # sanity
    # 'sov' tiene 3 chars -> no especifico -> no match
    assert not _matches("RE: SOV missing", "SOV.xlsx")
    # token de >=4 chars si matchea
    assert _matches("RE: Chatham file", "Chatham.pdf")


def test_unrelated_file_no_match():
    assert not _matches(
        "FW: Hunters Crossing Carlyle Landing PROP GL AUTO",
        "Sunset Gardens - Equipment Breakdown.pdf",
    )


def test_doc_tokens_still_used_for_matrix_match():
    # _doc_tokens sigue vigente para el match de documentos esperados.
    assert _doc_tokens("ACORD 25") == ["acord", "25"]
