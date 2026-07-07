from datetime import datetime, timezone

from app.services.preflight import (
    DISPOSITION_DESCARTADO,
    DISPOSITION_PENDIENTE,
    PreflightResult,
    _extract_original_sender,
    _infer_lender_name,
    _is_forward,
    evaluate,
    gate_blacklist,
    gate_dedup,
    gate_lender,
    gate_security,
    mentioned_lender,
)
from app.schemas import EmailData


def _kb(domain_status, domain_map=None, entries=None):
    return {
        "domain_status": domain_status,
        "domain_map": domain_map or {},
        "entries": entries or [],
    }


def test_preflight_result_defaults():
    r = PreflightResult(passed=True)
    assert r.passed is True
    assert r.stage is None
    assert r.reason == ""
    assert r.detected_original_sender is None
    assert r.disposition == DISPOSITION_PENDIENTE


# --- blacklist (punto 3: DESCARTADO directo) --------------------------------

def test_blacklist_hit_discards_directly():
    e = EmailData(sender="bot@teams.mail.microsoft", sender_domain="teams.mail.microsoft")
    kb = _kb({"teams.mail.microsoft": "NO_APROBADO"})
    r = gate_blacklist(e, kb)
    assert r is not None and r.passed is False and r.stage == "blacklist"
    assert "teams.mail.microsoft" in r.reason
    assert r.disposition == DISPOSITION_DESCARTADO


def test_blacklist_pass_when_not_noapprobado():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com")
    assert gate_blacklist(e, _kb({"jll.com": "APROBADO"})) is None


# --- gate_lender (punto 2) ---------------------------------------------------

def test_lender_direct_approved_passes():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com")
    assert gate_lender(e, _kb({"jll.com": "APROBADO"})) is None


def test_direct_domain_por_aprobar_goes_to_review():
    e = EmailData(sender="a@x.com", sender_domain="x.com", subject="Waiver")
    r = gate_lender(e, _kb({"x.com": "POR_APROBAR"}))
    assert r.stage == "lender_por_aprobar" and r.passed is False
    assert r.disposition == DISPOSITION_PENDIENTE


def test_direct_new_domain_goes_to_review():
    e = EmailData(sender="a@new-lender.com", sender_domain="new-lender.com", subject="Hi")
    r = gate_lender(e, _kb({}))
    assert r.stage == "lender_nuevo" and r.passed is False
    assert r.disposition == DISPOSITION_PENDIENTE


def test_forward_with_approved_lender_domain_in_body_passes():
    e = EmailData(
        sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
        subject="FW: [EXTERNAL] Waiver request",
        body_text="De: john@jll.com\nPara: blanca\nMensaje original del lender",
    )
    kb = _kb({"jll.com": "APROBADO"}, domain_map={"jll.com": "JLL"})
    assert gate_lender(e, kb) is None


def test_forward_with_lender_alias_in_text_passes():
    e = EmailData(
        sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
        subject="FW: Second Notice - KeyBank Loan 402111226",
        body_text="Please see the notice below regarding the loan." + " x" * 20,
    )
    kb = _kb({}, entries=[{"lender": "KeyBank", "lender_aliases": ["KeyBank Trust"]}])
    assert gate_lender(e, kb) is None


def test_forward_without_lender_is_discarded():
    e = EmailData(
        sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
        subject="FW: coordinacion",
        body_text="From: someone@randomcorp.com\nsin lender aqui",
    )
    r = gate_lender(e, _kb({}, domain_map={"jll.com": "JLL"},
                           entries=[{"lender": "JLL", "lender_aliases": []}]))
    assert r.stage == "sin_lender" and r.passed is False
    assert r.disposition == DISPOSITION_DESCARTADO
    assert r.detected_original_sender == "someone@randomcorp.com"


def test_internal_non_forward_without_lender_is_discarded():
    e = EmailData(sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
                  subject="Coordinacion interna", body_text="revisemos esto manana")
    r = gate_lender(e, _kb({}))
    assert r.stage == "sin_lender" and r.disposition == DISPOSITION_DESCARTADO


def test_internal_non_forward_with_lender_mention_passes():
    e = EmailData(sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
                  subject="Freddie Mac wording deficiency",
                  body_text="seguimiento al caso de Freddie Mac para Heritage Plaza")
    kb = _kb({}, entries=[{"lender": "Freddie Mac", "lender_aliases": []}])
    assert gate_lender(e, kb) is None


def test_mentioned_lender_ignores_internal_domains():
    e = EmailData(subject="FW: interno",
                  body_text="From: otra@acentopartners.com\nnada de lenders")
    kb = _kb({}, domain_map={"acentopartners.com": "Acento"})
    assert mentioned_lender(e, kb) is None


def test_mentioned_lender_requires_word_boundary():
    # "Arbor" no debe matchear dentro de "arboretum".
    e = EmailData(subject="FW: visita", body_text="the arboretum event is confirmed for tomorrow")
    kb = _kb({}, entries=[{"lender": "Arbor", "lender_aliases": []}])
    assert mentioned_lender(e, kb) is None


def test_infer_lender_name():
    assert _infer_lender_name("berkleyenvironmental.com") == "Berkleyenvironmental"


def test_is_forward_by_subject():
    assert _is_forward(EmailData(subject="FW: algo")) is True
    assert _is_forward(EmailData(subject="RE: algo")) is False


def test_extract_original_sender():
    assert _extract_original_sender("From: bob@x.com\n...") == "bob@x.com"
    assert _extract_original_sender("sin cabecera") is None


# --- security ----------------------------------------------------------------

def test_security_blocked_by_marker():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com",
                  subject="secure", body_text="This message is protected. Enable content to view")
    r = gate_security(e, _kb({}))
    assert r.stage == "seguridad_bloqueo" and r.passed is False
    assert r.disposition == DISPOSITION_PENDIENTE


def test_security_blocked_by_short_body():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com", subject="x", body_text="ok")
    assert gate_security(e, _kb({})).stage == "seguridad_bloqueo"


def test_security_ok_normal_body():
    e = EmailData(sender="a@jll.com", sender_domain="jll.com", subject="Waiver",
                  body_text="Please provide ACORD 25 and the endorsement pages for the property.")
    assert gate_security(e, _kb({})) is None


# --- dedup (punto 4: gana el ULTIMO del hilo) --------------------------------

def _mail(mid, domain, dt, subject="Waiver request for property",
          body="Please send ACORD 25 and endorsement pages."):
    return EmailData(message_id=mid, sender=f"a@{domain}", sender_domain=domain,
                     subject=subject, body_text=body,
                     received_date=datetime(2026, 1, dt, tzinfo=timezone.utc))


def test_dedup_latest_passes():
    a = _mail("A", "jll.com", 1)
    b = _mail("B", "jll.com", 2)
    assert gate_dedup(b, [a, b]) is None


def test_dedup_older_is_discarded():
    a = _mail("A", "jll.com", 1)
    b = _mail("B", "jll.com", 2)
    r = gate_dedup(a, [a, b])
    assert r.stage == "duplicado" and r.passed is False
    assert r.disposition == DISPOSITION_DESCARTADO


def test_dedup_null_date_loses_against_dated():
    dated = _mail("A", "jll.com", 1)
    undated = EmailData(message_id="B", sender="a@jll.com", sender_domain="jll.com")
    assert gate_dedup(dated, [dated, undated]) is None
    assert gate_dedup(undated, [dated, undated]).stage == "duplicado"


def test_dedup_single_email_passes():
    a = _mail("A", "jll.com", 1)
    assert gate_dedup(a, [a]) is None


# --- evaluate (orden y cortocircuito) -----------------------------------------

def test_evaluate_full_pass_for_latest_lender_email():
    a = _mail("A", "jll.com", 1)
    kb = _kb({"jll.com": "APROBADO"})
    assert evaluate(a, kb, [a]).passed is True


def test_evaluate_blacklist_short_circuits():
    e = _mail("A", "teams.mail.microsoft", 1)
    kb = _kb({"teams.mail.microsoft": "NO_APROBADO"})
    r = evaluate(e, kb, [e])
    assert r.stage == "blacklist" and r.disposition == DISPOSITION_DESCARTADO


def test_evaluate_older_thread_email_discarded_before_lender_gate():
    old = _mail("A", "new-lender.com", 1)
    new = _mail("B", "new-lender.com", 2)
    r = evaluate(old, _kb({}), [old, new])
    assert r.stage == "duplicado" and r.disposition == DISPOSITION_DESCARTADO


def test_evaluate_forward_with_lender_reaches_security_pass():
    e = EmailData(
        message_id="F1",
        sender="blanca@acentopartners.com", sender_domain="acentopartners.com",
        subject="FW: [EXTERNAL] Waiver request - Maple Ridge",
        body_text="From: john@jll.com\nPlease provide ACORD 25 and endorsement pages.",
        received_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    kb = _kb({"jll.com": "APROBADO"}, domain_map={"jll.com": "JLL"})
    assert evaluate(e, kb, [e]).passed is True
