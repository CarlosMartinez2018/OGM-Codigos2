"""Tests del loop de feedback: correcciones/rechazos -> data/feedback_context.md."""
from datetime import datetime, timezone

from app.services import feedback_context as fc


def _when():
    return datetime(2026, 7, 4, 15, 30, tzinfo=timezone.utc)


def test_append_correction_writes_entry(tmp_path):
    p = tmp_path / "fb.md"
    fc.append_correction("Greyco", "UNKNOWN", "JLL (Insurance Servicing)",
                         "Assault & Battery (A&B) sublimit", "era A&B", when=_when(), path=p)
    txt = p.read_text(encoding="utf-8")
    assert "Greyco" in txt and "JLL (Insurance Servicing)" in txt
    assert "Assault & Battery (A&B) sublimit" in txt
    assert "era A&B" in txt
    assert "2026-07-04" in txt


def test_append_rejection_writes_entry(tmp_path):
    p = tmp_path / "fb.md"
    fc.append_rejection("Greyco", "UNKNOWN", "no es un waiver", when=_when(), path=p)
    txt = p.read_text(encoding="utf-8")
    assert "RECHAZO" in txt.upper()
    assert "Greyco" in txt and "no es un waiver" in txt


def test_appends_accumulate(tmp_path):
    p = tmp_path / "fb.md"
    fc.append_rejection("A", "x", "c1", when=_when(), path=p)
    fc.append_rejection("B", "y", "c2", when=_when(), path=p)
    txt = p.read_text(encoding="utf-8")
    assert txt.count("- ") >= 2
    assert "c1" in txt and "c2" in txt


def test_read_context_missing_returns_empty(tmp_path):
    assert fc.read_context(path=tmp_path / "nope.md") == ""


def test_read_context_returns_content(tmp_path):
    p = tmp_path / "fb.md"
    fc.append_rejection("A", "x", "c1", when=_when(), path=p)
    assert "c1" in fc.read_context(path=p)


def test_header_written_once(tmp_path):
    p = tmp_path / "fb.md"
    fc.append_rejection("A", "x", "c1", when=_when(), path=p)
    fc.append_rejection("B", "y", "c2", when=_when(), path=p)
    txt = p.read_text(encoding="utf-8")
    assert txt.count("# ") == 1  # un solo encabezado
