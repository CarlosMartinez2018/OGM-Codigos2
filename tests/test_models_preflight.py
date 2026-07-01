from models import DomainLenderMap, ProductionEmail, EmailReview


def test_domain_lender_map_has_status_and_created_at():
    cols = DomainLenderMap.__table__.columns.keys()
    assert "status" in cols
    assert "created_at" in cols


def test_production_email_has_case_id():
    assert "case_id" in ProductionEmail.__table__.columns.keys()


def test_email_review_columns():
    cols = EmailReview.__table__.columns.keys()
    for c in ("production_email_id", "message_id", "conversation_id", "case_id",
              "stage", "reason", "detected_original_sender", "status",
              "created_at", "resolved_at"):
        assert c in cols
