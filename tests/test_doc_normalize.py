from app.services.doc_normalize import split_document, normalize_documents


def test_split_plus_same_prefix():
    assert split_document("ACORD 25 + ACORD 101") == ["ACORD 25", "ACORD 101"]


def test_split_slash():
    assert split_document("ACORD 25/28") == ["ACORD 25", "ACORD 28"]


def test_split_bare_number_continuation():
    assert split_document("ACORD 25 + 28 + 101") == ["ACORD 25", "ACORD 28", "ACORD 101"]


def test_qualifier_kept_per_acord():
    assert split_document("ACORD 28 (Property) + ACORD 101") == ["ACORD 28 (Property)", "ACORD 101"]


def test_plus_separates_non_acord_from_acord():
    assert split_document("Invoice + ACORD 25/28") == ["Invoice", "ACORD 25", "ACORD 28"]


def test_non_acord_slash_not_split():
    # GL/Umbrella no se debe partir
    assert split_document("split GL vs Umbrella on invoice.") == ["split GL vs Umbrella on invoice"]


def test_plain_doc_unchanged():
    assert split_document("GL A&B endorsement pages") == ["GL A&B endorsement pages"]


def test_trailing_punctuation_stripped():
    assert split_document("paid receipt if requested.") == ["paid receipt if requested"]


def test_idempotent():
    once = normalize_documents(["ACORD 25 + 28 + 101"])
    assert normalize_documents(once) == once == ["ACORD 25", "ACORD 28", "ACORD 101"]


def test_normalize_dedup_across_rows():
    assert normalize_documents(["ACORD 25/28", "ACORD 28", "SOV"]) == ["ACORD 25", "ACORD 28", "SOV"]
