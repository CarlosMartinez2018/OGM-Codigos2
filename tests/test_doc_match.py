"""Tests del match difuso de documentos esperados vs archivos SharePoint.

Cubre los helpers puros de app.main que rigen la logica de coincidencia:
tokenizacion significativa, extension y semantica de subconjunto.
"""
from app.main import _doc_tokens, _strip_ext


# --- _doc_tokens -----------------------------------------------------------

def test_tokens_lowercases_and_splits():
    assert _doc_tokens("ACORD 25") == ["acord", "25"]


def test_tokens_keep_digits():
    assert "101" in _doc_tokens("ACORD FORM 101")


def test_tokens_drop_single_letters():
    # 'A&B' -> a, b (una letra) se descartan; quedan los significativos.
    toks = _doc_tokens("GL A&B endorsement pages")
    assert "a" not in toks and "b" not in toks
    assert "gl" in toks and "endorsement" in toks


def test_tokens_drop_stopwords():
    toks = _doc_tokens("Evidence of Property Form")
    assert "of" not in toks and "form" not in toks
    assert "evidence" in toks and "property" in toks


def test_tokens_empty():
    assert _doc_tokens("") == []
    assert _doc_tokens("   ") == []


# --- _strip_ext ------------------------------------------------------------

def test_strip_ext_basic():
    assert _strip_ext("file.PDF") == ("file", "pdf")


def test_strip_ext_multidot():
    # Solo la ultima extension.
    assert _strip_ext("ACORD 101 - GL 01.06.26.pdf") == ("ACORD 101 - GL 01.06.26", "pdf")


def test_strip_ext_none():
    assert _strip_ext("SOV") == ("SOV", "")


# --- semantica de subconjunto (lo que dispara un match 'tokens') ----------

def _subset(doc: str, filename: str) -> bool:
    exp = set(_doc_tokens(doc))
    return bool(exp) and exp <= set(_doc_tokens(filename))


def test_subset_acord_matches_real_filename():
    assert _subset("ACORD 101", "ACENTO - ADDITIONAL REMARKS SECTION - ACORD FORM 101 - GL SAMPLE.pdf")


def test_subset_sov_matches():
    assert _subset("SOV", "Acento Real Estate Partners, LLC - SOV - Lenders File.xlsx")


def test_subset_missing_token_no_match():
    # 'loss runs' requiere ambos tokens; el archivo no los tiene.
    assert not _subset("loss runs", "ACORD FORM 25 - SAMPLE.pdf")


def test_subset_partial_number_no_false_positive():
    # 'ACORD 28' no debe machear un archivo de ACORD 25.
    assert not _subset("ACORD 28", "CERT OF LIAB INS - ACORD FORM 25 - SAMPLE.pdf")
