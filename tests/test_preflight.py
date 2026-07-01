from datetime import datetime, timezone
from preflight import PreflightResult, gate_blacklist, gate_domain, _infer_lender_name, gate_threads, _is_forward, _extract_original_sender, gate_security, gate_dedup, evaluate
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


def test_lender_direct_passes_threads():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com", subject="Waiver request")
    assert gate_threads(e, _kb({"jll.com": "APROBADO"})) is None


def test_internal_forward_goes_to_reenvio():
    e = EmailData(
        sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
        subject="FW: [EXTERNAL] Waiver request",
        body_text="De: john@jll.com\nPara: blanca\nMensaje original",
    )
    r = gate_threads(e, _kb({"jll.com": "APROBADO"}))
    assert r.stage == "reenvio" and r.detected_original_sender == "john@jll.com"


def test_internal_no_forward_is_hilo_incompleto():
    e = EmailData(sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
                  subject="Coordinacion interna", body_text="revisemos esto")
    r = gate_threads(e, _kb({}))
    assert r.stage == "hilo_incompleto"


def test_is_forward_by_subject():
    assert _is_forward(EmailData(subject="FW: algo")) is True
    assert _is_forward(EmailData(subject="RE: algo")) is False


def test_extract_original_sender():
    assert _extract_original_sender("From: bob@x.com\n...") == "bob@x.com"
    assert _extract_original_sender("sin cabecera") is None


def test_security_blocked_by_marker():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com",
                  subject="secure", body_text="This message is protected. Enable content to view")
    r = gate_security(e, _kb({}))
    assert r.stage == "seguridad_bloqueo" and r.passed is False


def test_security_blocked_by_short_body():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com", subject="x", body_text="ok")
    assert gate_security(e, _kb({})).stage == "seguridad_bloqueo"


def test_security_ok_normal_body():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com", subject="Waiver",
                  body_text="Please provide ACORD 25 and the endorsement pages for the property.")
    assert gate_security(e, _kb({})) is None


def _mail(mid, domain, dt, subject="Waiver request for property", body="Please send ACORD 25 and endorsement pages."):
    return EmailData(message_id=mid, sender=f"a@{domain}", sender_domain=domain,
                     subject=subject, body_text=body,
                     received_date=datetime(2026, 1, dt, tzinfo=timezone.utc))


def test_dedup_primary_passes():
    a = _mail("A", "jll.com", 1)
    b = _mail("B", "jll.com", 2)
    assert gate_dedup(a, [a, b]) is None


def test_dedup_non_primary_goes_to_review():
    a = _mail("A", "jll.com", 1)
    b = _mail("B", "jll.com", 2)
    r = gate_dedup(b, [a, b])
    assert r.stage == "duplicado" and r.passed is False


def test_evaluate_full_pass_for_lender_primary():
    a = _mail("A", "jll.com", 1)
    kb = {"domain_status": {"jll.com": "APROBADO"}}
    assert evaluate(a, kb, [a]).passed is True


def test_evaluate_blacklist_short_circuits():
    e = _mail("A", "teams.mail.microsoft", 1)
    kb = {"domain_status": {"teams.mail.microsoft": "NO_APROBADO"}}
    assert evaluate(e, kb, [e]).stage == "blacklist"
