"""Regresion del DoS en clean_email_body (hallazgo del agente adversario):
la version con `.*<.*@.*>.*wrote:` tardaba ~15s en 64KB y no terminaba en 1MB."""
import time

from app.schemas import _MAX_CLEAN_LEN, clean_email_body


def test_large_body_is_fast():
    # Cuerpo hostil: muchas lineas con < @ > que no cierran el patron de cita.
    line = "aaa <user@dom> bbb @ ccc <x@y> ddd no closing marker here\n"
    body = line * 20_000  # ~1.2MB
    t0 = time.perf_counter()
    out = clean_email_body(body)
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0, f"clean_email_body tardo {elapsed:.1f}s"
    assert len(out) <= _MAX_CLEAN_LEN


def test_quote_split_still_works():
    body = (
        "Please send the ACORD 25 for the property.\n"
        "John Smith <john@jll.com> wrote:\n"
        "older message content\n"
    )
    out = clean_email_body(body)
    assert "Please send the ACORD 25" in out


def test_signature_still_stripped():
    body = "The waiver request is attached.\nBest regards,\nJohn\n"
    out = clean_email_body(body)
    assert "waiver request" in out
    assert "John" not in out.split("Best regards")[-1] if "Best regards" in out else True


def test_empty_body():
    assert clean_email_body("") == ""
