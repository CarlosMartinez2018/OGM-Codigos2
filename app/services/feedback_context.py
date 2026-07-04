"""
feedback_context.py -- Loop de mejora continua del clasificador.

Cada correccion o rechazo humano se anexa, en lenguaje natural, a un archivo
markdown incremental (`data/feedback_context.md`). El clasificador lo lee como
contexto para no repetir errores; cuando el LLM esta encendido, se inyecta en
el prompt. Versionable en git, legible por humanos.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "feedback_context.md"

_HEADER = (
    "# Contexto de feedback del clasificador\n\n"
    "Correcciones y rechazos del operador humano. El clasificador lee esto para\n"
    "mejorar. Cada linea es un caso; no editar a mano salvo para resumir.\n"
)


def _stamp(when: Optional[datetime]) -> str:
    dt = when or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


def _ensure_header(path: Path) -> None:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_HEADER, encoding="utf-8")


def _append_line(path: Path, line: str) -> None:
    _ensure_header(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line if line.endswith("\n") else line + "\n")


def append_correction(
    original_lender: str,
    original_waiver: str,
    corrected_lender: str,
    corrected_waiver: str,
    note: Optional[str] = None,
    when: Optional[datetime] = None,
    path: Path = _PATH,
) -> None:
    """Registra que el operador corrigio una clasificacion."""
    tail = f" — nota: {note}" if note else ""
    line = (
        f"- [{_stamp(when)}] CORRECCION: "
        f"'{original_lender} / {original_waiver}' → "
        f"'{corrected_lender} / {corrected_waiver}'{tail}"
    )
    _append_line(path, line)


def append_rejection(
    lender: str,
    waiver: str,
    comment: str,
    when: Optional[datetime] = None,
    path: Path = _PATH,
) -> None:
    """Registra que el operador rechazo una clasificacion (con motivo)."""
    line = (
        f"- [{_stamp(when)}] RECHAZO: "
        f"'{lender} / {waiver}' — motivo: {comment}"
    )
    _append_line(path, line)


def read_context(path: Path = _PATH) -> str:
    """Devuelve el contenido del contexto de feedback (o '' si no existe)."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
