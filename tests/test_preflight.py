from preflight import PreflightResult, gate_blacklist, gate_domain, _infer_lender_name
from schemas import EmailData


def _kb(domain_status):
    return {"domain_status": domain_status}


def test_preflight_result_defaults():
    r = PreflightResult(passed=True)
    assert r.passed is True
    assert r.stage is None
    assert r.reason == ""
    assert r.detected_original_sender is None


def test_blacklist_hit_names_lender():
    e = EmailData(sender="bot@teams.mail.microsoft", sender_domain="teams.mail.microsoft")
    kb = _kb({"teams.mail.microsoft": "NO_APROBADO"})
    r = gate_blacklist(e, kb)
    assert r is not None and r.passed is False and r.stage == "blacklist"
    assert "teams.mail.microsoft" in r.reason


def test_blacklist_pass_when_not_noapprobado():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com")
    assert gate_blacklist(e, _kb({"jll.com": "APROBADO"})) is None


def test_domain_approved_passes():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com")
    assert gate_domain(e, _kb({"jll.com": "APROBADO"})) is None


def test_domain_por_aprobar():
    e = EmailData(sender="a@x.com", sender_domain="x.com")
    r = gate_domain(e, _kb({"x.com": "POR_APROBAR"}))
    assert r.stage == "lender_por_aprobar" and r.passed is False


def test_domain_nuevo():
    e = EmailData(sender="a@new-lender.com", sender_domain="new-lender.com")
    r = gate_domain(e, _kb({}))
    assert r.stage == "lender_nuevo" and r.passed is False


def test_domain_internal_passes_through():
    e = EmailData(sender="blanca@acentopartners.com", sender_domain="acentopartners.com")
    assert gate_domain(e, _kb({})) is None


def test_infer_lender_name():
    assert _infer_lender_name("berkleyenvironmental.com") == "Berkleyenvironmental"
