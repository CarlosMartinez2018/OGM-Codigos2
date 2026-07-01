# Pipeline de pre-filtrado + Aprobación de lenders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insertar un pipeline de pre-filtrado (5 gates) antes del LLM que descarta correos a una cola de revisión manual, y un workflow de aprobación de lenders (POR_APROBAR/APROBADO/NO_APROBADO) con re-clasificación al aprobar.

**Architecture:** Gates puros y sin estado en `preflight.py` (testeables sin BD) que devuelven `PreflightResult`. El clasificador orquesta: por correo corre `preflight.evaluate()`; si no pasa, escribe `email_reviews` y salta el LLM; si pasa, clasifica como hoy. Los efectos de BD (auto-alta de lender, escritura de reviews) viven en la capa de integración, no en los gates. La aprobación de lenders vive en `lender_approval.py`.

**Tech Stack:** Python 3.12, SQLAlchemy async (asyncpg), PostgreSQL, pytest (para gates puros), Ollama (LLM existente, sin cambios).

## Global Constraints

- Base de datos dev tiene datos reales (137 production_emails, 10 training, 14 dominios, 11 matrix, 47 docs). **Ninguna migración debe borrar production_emails/training_emails.** Usar migración in-place, nunca `seed_db.py` sobre dev.
- `.env` contiene secretos de Azure — nunca commitear (ya en `.gitignore`).
- Ejecutable Python del venv: `./venv/Scripts/python.exe` (Windows).
- Estados de lender exactos: `APROBADO` | `POR_APROBAR` | `NO_APROBADO`.
- Stages de review exactos: `blacklist` | `lender_nuevo` | `lender_por_aprobar` | `hilo_incompleto` | `reenvio` | `seguridad_bloqueo` | `duplicado`.
- Dominios internos: `acentopartners.com`, `captiveadvisorypartners.com`.
- Dominios ruido (blacklist inicial): `teams.mail.microsoft`, `proofpointessentials.com`, `microsoft.com`.
- El LLM solo cruza con lenders `APROBADO`.

---

### Task 1: Infra de tests + config de seguridad + PreflightResult

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`
- Create: `preflight.py`
- Create: `tests/__init__.py`
- Create: `tests/test_preflight.py`

**Interfaces:**
- Produces: `PreflightResult(passed: bool, stage: str|None, reason: str, detected_original_sender: str|None)` en `preflight.py`.
- Produces en `config.settings`: `internal_domains: list[str]`, `security_block_markers: list[str]`, `security_min_body_len: int`.

- [ ] **Step 1: Añadir pytest a requirements**

En `requirements.txt` agregar al final:

```
pytest==8.3.4
```

- [ ] **Step 2: Instalar**

Run: `./venv/Scripts/python.exe -m pip install pytest==8.3.4`
Expected: `Successfully installed pytest-8.3.4`

- [ ] **Step 3: Añadir settings de seguridad e internos a config.py**

En `config.py`, dentro de `class Settings`, después de `ollama_timeout`:

```python
    # Pre-filtrado
    internal_domains: list[str] = ["acentopartners.com", "captiveadvisorypartners.com"]
    security_block_markers: list[str] = [
        "encrypted message",
        "this message is protected",
        "rights-protected",
        "enable content to view",
        "message has been blocked",
        "contenido bloqueado",
        "no se puede mostrar el contenido",
        "cannot display this message",
    ]
    security_min_body_len: int = 20
```

- [ ] **Step 4: Escribir el test que falla (PreflightResult existe)**

Crear `tests/__init__.py` vacío. Crear `tests/test_preflight.py`:

```python
from preflight import PreflightResult


def test_preflight_result_defaults():
    r = PreflightResult(passed=True)
    assert r.passed is True
    assert r.stage is None
    assert r.reason == ""
    assert r.detected_original_sender is None
```

- [ ] **Step 5: Correr el test para verificar que falla**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'preflight'`

- [ ] **Step 6: Crear preflight.py con el dataclass**

Crear `preflight.py`:

```python
"""
preflight.py -- Pipeline de pre-filtrado antes del LLM.

Gates puros y sin estado: reciben un EmailData (+ contexto) y devuelven un
PreflightResult. Los efectos de BD (auto-alta de lender, escritura de reviews)
los hace la capa de integracion en llm_classifier.py, no estos gates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from config import settings
from schemas import EmailData


@dataclass
class PreflightResult:
    passed: bool
    stage: Optional[str] = None
    reason: str = ""
    detected_original_sender: Optional[str] = None
```

- [ ] **Step 7: Correr el test para verificar que pasa**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add requirements.txt config.py preflight.py tests/__init__.py tests/test_preflight.py
git commit -m "feat(preflight): infra de tests, config de seguridad y PreflightResult"
```

---

### Task 2: Cambios de modelo (status, created_at, case_id, EmailReview)

**Files:**
- Modify: `models.py`
- Create: `tests/test_models_preflight.py`

**Interfaces:**
- Produces: `DomainLenderMap.status: str`, `DomainLenderMap.created_at: datetime`.
- Produces: `ProductionEmail.case_id: str`.
- Produces: modelo `EmailReview` (tabla `email_reviews`) con columnas del spec.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_models_preflight.py`:

```python
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
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `./venv/Scripts/python.exe -m pytest tests/test_models_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'EmailReview'`

- [ ] **Step 3: Añadir status/created_at a DomainLenderMap**

En `models.py`, clase `DomainLenderMap`, después de `lender_name`:

```python
    status: Mapped[str] = mapped_column(String(20), default="POR_APROBAR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Añadir case_id a ProductionEmail**

En `models.py`, clase `ProductionEmail`, después de `conversation_id`:

```python
    case_id: Mapped[str] = mapped_column(String(500), default="")
```

- [ ] **Step 5: Añadir el modelo EmailReview**

En `models.py`, al final del archivo:

```python
# ---------------------------------------------------------------------------
# Cola de revision manual (correos descartados por el pre-filtrado)
# ---------------------------------------------------------------------------

class EmailReview(Base):
    __tablename__ = "email_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    production_email_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("production_emails.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[str] = mapped_column(String(500), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(500), default="")
    case_id: Mapped[str] = mapped_column(String(500), default="")
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    detected_original_sender: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("message_id", "stage", name="uq_review_message_stage"),
    )
```

- [ ] **Step 6: Correr para verificar que pasa**

Run: `./venv/Scripts/python.exe -m pytest tests/test_models_preflight.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add models.py tests/test_models_preflight.py
git commit -m "feat(models): status/created_at en domain_lender_map, case_id, EmailReview"
```

---

### Task 3: Migración in-place (preserva correos)

**Files:**
- Create: `migrate_preflight.py`

**Interfaces:**
- Consumes: modelos de Task 2.
- Produces: esquema dev migrado; script idempotente.

- [ ] **Step 1: Crear migrate_preflight.py**

Crear `migrate_preflight.py`:

```python
"""
migrate_preflight.py -- Migracion in-place para el pipeline de pre-filtrado.

NO borra datos (a diferencia de seed_db.py). Agrega columnas a domain_lender_map
y production_emails, crea email_reviews, y siembra estados iniciales.
Idempotente.

Uso:
    python migrate_preflight.py
"""
import asyncio

from rich.console import Console
from sqlalchemy import text

from database import engine, init_db
import models  # noqa: F401 -- registra tablas en Base.metadata

console = Console()

NOISE_DOMAINS = ["teams.mail.microsoft", "proofpointessentials.com", "microsoft.com"]


async def _col_exists(conn, table, column):
    r = await conn.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return r.first() is not None


async def main():
    console.print("\n[bold]migrate_preflight.py[/bold]\n")

    # Crea tablas faltantes (email_reviews). No borra nada.
    await init_db()
    console.print("[green]OK - email_reviews asegurada[/green]")

    async with engine.begin() as conn:
        # domain_lender_map.status / created_at
        if not await _col_exists(conn, "domain_lender_map", "status"):
            await conn.execute(text(
                "ALTER TABLE domain_lender_map ADD COLUMN status VARCHAR(20) "
                "NOT NULL DEFAULT 'POR_APROBAR'"
            ))
        if not await _col_exists(conn, "domain_lender_map", "created_at"):
            await conn.execute(text(
                "ALTER TABLE domain_lender_map ADD COLUMN created_at TIMESTAMPTZ "
                "NOT NULL DEFAULT now()"
            ))
        # Los dominios ya existentes son lenders validos (el ruido no esta aun
        # en la tabla; se inserta como NO_APROBADO en el paso siguiente).
        await conn.execute(text(
            "UPDATE domain_lender_map SET status='APROBADO' WHERE status='POR_APROBAR'"
        ))
        # Dominios ruido -> blacklist. Upsert (sobrescribe a NO_APROBADO si existieran).
        for d in NOISE_DOMAINS:
            await conn.execute(text(
                "INSERT INTO domain_lender_map (domain, lender_name, status, created_at) "
                "VALUES (:d, :n, 'NO_APROBADO', now()) "
                "ON CONFLICT (domain) DO UPDATE SET status='NO_APROBADO'"
            ), {"d": d, "n": d})
        console.print("[green]OK - domain_lender_map: status/created_at + ruido[/green]")

        # production_emails.case_id
        if not await _col_exists(conn, "production_emails", "case_id"):
            await conn.execute(text(
                "ALTER TABLE production_emails ADD COLUMN case_id VARCHAR(500) DEFAULT ''"
            ))
        await conn.execute(text(
            "UPDATE production_emails SET case_id = conversation_id "
            "WHERE case_id IS NULL OR case_id = ''"
        ))
        console.print("[green]OK - production_emails.case_id relleno[/green]")

    console.print("\n[bold green]LISTO. Migracion aplicada (correos preservados).[/bold green]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Correr la migración**

Run: `./venv/Scripts/python.exe migrate_preflight.py`
Expected: 4 líneas `OK` + `LISTO`.

- [ ] **Step 3: Verificar esquema y datos (no destructivo)**

Run:
```bash
./venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from database import engine
async def m():
    async with engine.connect() as c:
        for q in ['SELECT count(*) FROM production_emails',
                  \"SELECT status,count(*) FROM domain_lender_map GROUP BY status\",
                  'SELECT count(*) FROM email_reviews']:
            print(q, '->', [tuple(r) for r in await c.execute(text(q))])
    await engine.dispose()
asyncio.run(m())
"
```
Expected: production_emails 137; domain_lender_map con `APROBADO` 14 y `NO_APROBADO` 3; email_reviews 0.

- [ ] **Step 4: Commit**

```bash
git add migrate_preflight.py
git commit -m "feat(migrate): migracion in-place del pre-filtrado (preserva correos)"
```

---

### Task 4: Gates blacklist + dominio

**Files:**
- Modify: `preflight.py`
- Modify: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `kb["domain_status"]: dict[str,str]` (dominio -> status; todos los dominios).
- Produces: `gate_blacklist(email, kb) -> PreflightResult|None`, `gate_domain(email, kb) -> PreflightResult|None`, `_domain_status(email, kb) -> str|None`, `_infer_lender_name(domain) -> str`.

- [ ] **Step 1: Escribir tests que fallan**

Añadir a `tests/test_preflight.py`:

```python
from preflight import gate_blacklist, gate_domain, _infer_lender_name
from schemas import EmailData


def _kb(domain_status):
    return {"domain_status": domain_status}


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
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'gate_blacklist'`

- [ ] **Step 3: Implementar los gates**

Añadir a `preflight.py`:

```python
def _sender_domain(email: EmailData) -> str:
    return (email.sender_domain or "").lower()


def _domain_status(email: EmailData, kb: dict[str, Any]) -> Optional[str]:
    return kb["domain_status"].get(_sender_domain(email))


def _infer_lender_name(domain: str) -> str:
    base = (domain or "").split(".")[0]
    return base.capitalize()


def gate_blacklist(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    domain = _sender_domain(email)
    if _domain_status(email, kb) == "NO_APROBADO":
        lender = kb.get("domain_name", {}).get(domain, domain)
        reason = f"Lender/dominio en blacklist (NO_APROBADO): {lender} <{domain}>"
        return PreflightResult(False, "blacklist", reason)
    return None


def gate_domain(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    domain = _sender_domain(email)
    if domain in settings.internal_domains:
        return None  # remitente interno: lo maneja el gate de hilos
    status = _domain_status(email, kb)
    if status == "APROBADO":
        return None
    if status == "POR_APROBAR":
        return PreflightResult(False, "lender_por_aprobar",
                               f"Dominio pendiente de aprobacion: {domain}")
    # No esta en el mapa -> nuevo lender por aprobar
    return PreflightResult(False, "lender_nuevo",
                           f"Dominio nuevo, requiere aprobacion: {domain}")
```

Nota: `kb["domain_name"]` es opcional (dominio->lender_name) para enriquecer el
`reason` de blacklist; si no está, cae al dominio. Se poblará en Task 8.

- [ ] **Step 4: Correr para verificar que pasan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add preflight.py tests/test_preflight.py
git commit -m "feat(preflight): gates blacklist y dominio con auto-alta"
```

---

### Task 5: Gate de hilos (reenvíos / hilo incompleto)

**Files:**
- Modify: `preflight.py`
- Modify: `tests/test_preflight.py`

**Interfaces:**
- Produces: `gate_threads(email, kb) -> PreflightResult|None`, `_is_forward(email) -> bool`, `_extract_original_sender(body) -> str|None`.

- [ ] **Step 1: Escribir tests que fallan**

Añadir a `tests/test_preflight.py`:

```python
from preflight import gate_threads, _is_forward, _extract_original_sender


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
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'gate_threads'`

- [ ] **Step 3: Implementar**

Añadir a `preflight.py`:

```python
_FORWARD_SUBJECT = re.compile(r"^\s*(fw|fwd|rv|enc)\s*:", re.IGNORECASE)
_ORIGINAL_SENDER = re.compile(
    r"(?im)^(?:de|from)\s*:\s*.*?([\w.\-+%]+@[\w.\-]+\.\w+)"
)


def _is_forward(email: EmailData) -> bool:
    if _FORWARD_SUBJECT.search(email.subject or ""):
        return True
    return bool(_ORIGINAL_SENDER.search(email.body_text or ""))


def _extract_original_sender(body: str | None) -> Optional[str]:
    m = _ORIGINAL_SENDER.search(body or "")
    return m.group(1).lower() if m else None


def gate_threads(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    # Un correo directo de un lender aprobado es un hilo valido.
    if _domain_status(email, kb) == "APROBADO":
        return None
    # Remitente interno / no-lender que llego hasta aca -> revision.
    orig = _extract_original_sender(email.body_text)
    if _is_forward(email):
        reason = "Reenvio: la solicitud no llega directa del lender al buzon."
        return PreflightResult(False, "reenvio", reason, detected_original_sender=orig)
    reason = "Hilo sin origen de lender en el buzon."
    return PreflightResult(False, "hilo_incompleto", reason, detected_original_sender=orig)
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add preflight.py tests/test_preflight.py
git commit -m "feat(preflight): gate de hilos (reenvio/hilo incompleto)"
```

---

### Task 6: Gate de seguridad (contenido bloqueado/incompleto)

**Files:**
- Modify: `preflight.py`
- Modify: `tests/test_preflight.py`

**Interfaces:**
- Produces: `gate_security(email, kb) -> PreflightResult|None`, `_is_body_blocked(email) -> bool`.

- [ ] **Step 1: Escribir tests que fallan**

Añadir a `tests/test_preflight.py`:

```python
from preflight import gate_security


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
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'gate_security'`

- [ ] **Step 3: Implementar**

Añadir a `preflight.py`:

```python
def _is_body_blocked(email: EmailData) -> bool:
    body = (email.body_text or "").strip()
    if len(body) < settings.security_min_body_len:
        return True
    low = body.lower()
    return any(marker in low for marker in settings.security_block_markers)


def gate_security(email: EmailData, kb: dict[str, Any]) -> Optional[PreflightResult]:
    if _is_body_blocked(email):
        return PreflightResult(False, "seguridad_bloqueo",
                               "Contenido bloqueado o incompleto (cifrado/truncado).")
    return None
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add preflight.py tests/test_preflight.py
git commit -m "feat(preflight): gate de seguridad (contenido bloqueado)"
```

---

### Task 7: Gate de dedup + orquestador evaluate

**Files:**
- Modify: `preflight.py`
- Modify: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `group: list[EmailData]` (correos del mismo case_id).
- Produces: `gate_dedup(email, group) -> PreflightResult|None`, `_is_primary(email, group) -> bool`, `evaluate(email, kb, group) -> PreflightResult`.

- [ ] **Step 1: Escribir tests que fallan**

Añadir a `tests/test_preflight.py`:

```python
from datetime import datetime, timezone
from preflight import gate_dedup, evaluate


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
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'gate_dedup'`

- [ ] **Step 3: Implementar dedup + evaluate**

Añadir a `preflight.py`:

```python
def _sort_key(e: EmailData):
    # received_date puede ser None; los nulos van al final. Desempate por message_id.
    dt = e.received_date
    return (dt is None, dt, e.message_id or "")


def _is_primary(email: EmailData, group: list[EmailData]) -> bool:
    if not group:
        return True
    primary = min(group, key=_sort_key)
    return (email.message_id or "") == (primary.message_id or "")


def gate_dedup(email: EmailData, group: list[EmailData]) -> Optional[PreflightResult]:
    if _is_primary(email, group):
        return None
    return PreflightResult(False, "duplicado",
                           "No es el primer correo del conversation_id por fecha.")


def evaluate(email: EmailData, kb: dict[str, Any], group: list[EmailData]) -> PreflightResult:
    for gate in (
        lambda: gate_blacklist(email, kb),
        lambda: gate_domain(email, kb),
        lambda: gate_threads(email, kb),
        lambda: gate_security(email, kb),
        lambda: gate_dedup(email, group),
    ):
        result = gate()
        if result is not None:
            return result
    return PreflightResult(True)
```

- [ ] **Step 4: Correr toda la suite de preflight**

Run: `./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (todos los tests de preflight y models)

- [ ] **Step 5: Commit**

```bash
git add preflight.py tests/test_preflight.py
git commit -m "feat(preflight): gate dedup y orquestador evaluate"
```

---

### Task 8: Integración en el clasificador

**Files:**
- Modify: `llm_classifier.py`

**Interfaces:**
- Consumes: `preflight.evaluate`, modelos `EmailReview`, `DomainLenderMap`.
- Produces: `kb["domain_status"]`, `kb["domain_name"]`; `domain_map` solo APROBADO; `_ensure_pending_lender(session, domain)`, `_save_review(session, pe, result, case_id)`, integración en `classify_pending_production_emails`.

- [ ] **Step 1: Importar dependencias nuevas**

En `llm_classifier.py`, en el bloque `from models import (...)` añadir `DomainLenderMap` ya está; añadir `EmailReview`. Y arriba, tras los imports existentes:

```python
from collections import defaultdict

import preflight
```

- [ ] **Step 2: Cargar domain_status y filtrar domain_map a APROBADO**

En `_load_business_data`, reemplazar la construcción de `domain_map`:

```python
        domain_map = {}
        domain_status = {}
        domain_name = {}
        for row in domain_rows:
            d = row.domain.lower()
            domain_status[d] = row.status
            domain_name[d] = row.lender_name
            if row.status == "APROBADO":
                domain_map[d] = row.lender_name
        authorized_lenders = set(domain_map.values())
```

Y en el `return {...}` añadir las claves:

```python
            "domain_status": domain_status,
            "domain_name": domain_name,
```

- [ ] **Step 3: Añadir helpers de integración**

En `class EmailClassifier`, añadir métodos:

```python
    async def _ensure_pending_lender(self, session: AsyncSession, domain: str) -> None:
        domain = (domain or "").lower()
        if not domain:
            return
        stmt = pg_insert(DomainLenderMap).values(
            domain=domain,
            lender_name=preflight._infer_lender_name(domain),
            status="POR_APROBAR",
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["domain"])
        await session.execute(stmt)

    async def _save_review(
        self,
        session: AsyncSession,
        production_email: ProductionEmail,
        result: "preflight.PreflightResult",
        case_id: str,
    ) -> None:
        stmt = pg_insert(EmailReview).values(
            production_email_id=production_email.id,
            message_id=production_email.message_id,
            conversation_id=production_email.conversation_id or "",
            case_id=case_id,
            stage=result.stage,
            reason=result.reason,
            detected_original_sender=result.detected_original_sender,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id", "stage"],
            set_={
                "reason": stmt.excluded.reason,
                "detected_original_sender": stmt.excluded.detected_original_sender,
                "case_id": stmt.excluded.case_id,
            },
        )
        await session.execute(stmt)
```

- [ ] **Step 4: Integrar preflight en el loop de batch**

En `classify_pending_production_emails`, después de cargar `kb` y antes del loop, agrupar por case_id; y dentro del loop correr preflight:

```python
        kb = await self._load_business_data(session)

        # Agrupar por case_id (conversation_id) para el gate de dedup.
        groups: dict[str, list[EmailData]] = defaultdict(list)
        email_data_by_id: dict[int, EmailData] = {}
        for pe in emails:
            ed = self._production_to_email_data(pe)
            email_data_by_id[pe.id] = ed
            groups[pe.case_id or pe.conversation_id or ed.conversation_id].append(ed)

        results: list[tuple[ProductionEmail, ClassificationResult]] = []
        for production_email in emails:
            if not reclassify:
                existing = await session.scalar(
                    select(EmailClassification.id)
                    .where(EmailClassification.message_id == production_email.message_id)
                    .limit(1)
                )
                if existing:
                    continue

            email = email_data_by_id[production_email.id]
            case_id = production_email.case_id or production_email.conversation_id or email.conversation_id
            pre = preflight.evaluate(email, kb, groups[case_id])
            if not pre.passed:
                if pre.stage == "lender_nuevo":
                    await self._ensure_pending_lender(session, email.sender_domain)
                await self._save_review(session, production_email, pre, case_id)
                continue

            result = await self.classify(email, session, kb=kb)
            await self.save_classification(session, production_email, result)
            results.append((production_email, result))

        await session.commit()
        return results
```

Nota: se reemplaza la llamada previa `classify_production_email(...)` por
`classify(email, session, kb=kb)` (ya reutiliza el `EmailData` construido).

- [ ] **Step 5: Verificar suite de preflight sigue verde**

Run: `./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (sin regresiones; no dependen de este archivo).

- [ ] **Step 6: Verificación de integración sobre los 137 reales**

Run:
```bash
USE_LLM_CLASSIFIER=false ./venv/Scripts/python.exe llm_classifier.py --limit 0 --reclassify
```
Luego:
```bash
./venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text
from database import engine
async def m():
    async with engine.connect() as c:
        cls=(await c.execute(text('SELECT count(*) FROM email_classifications'))).scalar()
        rev=[tuple(r) for r in await c.execute(text('SELECT stage,count(*) FROM email_reviews GROUP BY stage ORDER BY 2 DESC'))]
        pend=(await c.execute(text(\"SELECT count(*) FROM domain_lender_map WHERE status='POR_APROBAR'\"))).scalar()
        print('clasificados:', cls)
        print('reviews por stage:', rev)
        print('lenders POR_APROBAR (auto-alta):', pend)
    await engine.dispose()
asyncio.run(m())
"
```
Expected: `clasificados` << 137 (solo sobrevivientes); `email_reviews` con stages `reenvio`/`hilo_incompleto`/`blacklist`/`duplicado`/`lender_nuevo`; algunos lenders nuevos `POR_APROBAR`. Confirmar que ningún correo interno/ruido llegó al LLM.

- [ ] **Step 7: Commit**

```bash
git add llm_classifier.py
git commit -m "feat(classifier): integra pre-filtrado y filtra lenders APROBADO"
```

---

### Task 9: Aprobación de lenders + re-clasificación

**Files:**
- Create: `lender_approval.py`

**Interfaces:**
- Consumes: `classifier` (singleton de `llm_classifier`), `preflight`, modelos.
- Produces: `approve_domain(session, domain) -> dict`, `reject_domain(session, domain) -> None`.

- [ ] **Step 1: Crear lender_approval.py**

Crear `lender_approval.py`:

```python
"""
lender_approval.py -- Aprobar/rechazar lenders y re-clasificar su ventana.

Sin UI: funciones invocables desde codigo/tests. La UI (futura) las expone con
los botones aprobar/rechazar.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import DomainLenderMap, EmailReview, ProductionEmail
from llm_classifier import classifier


async def reject_domain(session: AsyncSession, domain: str) -> None:
    domain = (domain or "").lower()
    await session.execute(
        update(DomainLenderMap)
        .where(DomainLenderMap.domain == domain)
        .values(status="NO_APROBADO")
    )
    await session.commit()


async def approve_domain(session: AsyncSession, domain: str) -> dict:
    domain = (domain or "").lower()
    row = await session.scalar(
        select(DomainLenderMap).where(DomainLenderMap.domain == domain)
    )
    if row is None:
        return {"domain": domain, "found": False, "reclassified": 0}

    await session.execute(
        update(DomainLenderMap)
        .where(DomainLenderMap.domain == domain)
        .values(status="APROBADO")
    )
    await session.commit()

    # Ventana: desde 1 dia antes de la creacion del lender hasta ahora.
    window_start = row.created_at - timedelta(days=1)
    emails = (await session.scalars(
        select(ProductionEmail)
        .where(ProductionEmail.sender_domain == domain)
        .where(ProductionEmail.received_date >= window_start)
    )).all()

    # Marca sus reviews lender_* como gestionadas.
    from datetime import datetime, timezone
    await session.execute(
        update(EmailReview)
        .where(EmailReview.stage.in_(["lender_nuevo", "lender_por_aprobar"]))
        .where(EmailReview.message_id.in_([e.message_id for e in emails] or [""]))
        .values(status="GESTIONADO", resolved_at=datetime.now(timezone.utc))
    )
    await session.commit()

    # Re-clasifica esos correos con la KB actualizada (dominio ya APROBADO).
    kb = await classifier._load_business_data(session)
    from collections import defaultdict
    groups = defaultdict(list)
    ed_by_id = {}
    for pe in emails:
        ed = classifier._production_to_email_data(pe)
        ed_by_id[pe.id] = ed
        groups[pe.case_id or pe.conversation_id or ed.conversation_id].append(ed)

    import preflight
    reclassified = 0
    for pe in emails:
        ed = ed_by_id[pe.id]
        case_id = pe.case_id or pe.conversation_id or ed.conversation_id
        pre = preflight.evaluate(ed, kb, groups[case_id])
        if not pre.passed:
            await classifier._save_review(session, pe, pre, case_id)
            continue
        result = await classifier.classify(ed, session, kb=kb)
        await classifier.save_classification(session, pe, result)
        reclassified += 1
    await session.commit()
    return {"domain": domain, "found": True, "reclassified": reclassified}
```

- [ ] **Step 2: Verificar import**

Run: `./venv/Scripts/python.exe -c "import lender_approval; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verificación funcional (aprobar un dominio nuevo)**

Run:
```bash
./venv/Scripts/python.exe -c "
import asyncio
from sqlalchemy import text, select
from database import async_session, engine
from models import DomainLenderMap
import lender_approval
async def m():
    async with async_session() as s:
        d=await s.scalar(select(DomainLenderMap.domain).where(DomainLenderMap.status=='POR_APROBAR').limit(1))
        if not d:
            print('no hay POR_APROBAR para probar'); return
        print('aprobando', d)
        print(await lender_approval.approve_domain(s, d))
    await engine.dispose()
asyncio.run(m())
"
```
Expected: dict `{'domain': ..., 'found': True, 'reclassified': N}` con N >= 0; el dominio queda `APROBADO`.

- [ ] **Step 4: Commit**

```bash
git add lender_approval.py
git commit -m "feat(approval): aprobar/rechazar lenders + re-clasificacion por ventana"
```

---

### Task 10: Semilla y export para producción

**Files:**
- Modify: `seed_db.py`
- Modify: `export_seed.py`

**Interfaces:**
- Produces: `domain_lender_map.json` con `status`; `seed_db` siembra `status`.

- [ ] **Step 1: export_seed.py — incluir status en el JSON de dominios**

En `export_seed.py`, `_export_domain_map`, reemplazar el select y el dict:

```python
async def _export_domain_map() -> int:
    rows = await _fetch("SELECT domain, lender_name, status FROM domain_lender_map ORDER BY id")
    data = [{"domain": r["domain"], "lender_name": r["lender_name"], "status": r["status"]} for r in rows]
    path = BASE_DIR / "domain_lender_map.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(data)
```

Nota: cambia el formato de `domain_lender_map.json` de dict a lista de objetos
(para llevar el status). `seed_db.py` se ajusta en el paso siguiente.

- [ ] **Step 2: seed_db.py — leer el nuevo formato con status**

En `seed_db.py`, `_seed_domain_lender_map`, reemplazar el loop:

```python
    async with async_session() as session:
        for entry in data:
            if isinstance(entry, str):
                # compat formato viejo {domain: lender}
                domain, lender_name, status = entry, data[entry], "APROBADO"
            else:
                domain = entry["domain"]
                lender_name = entry["lender_name"]
                status = entry.get("status", "APROBADO")
            session.add(DomainLenderMap(domain=domain, lender_name=lender_name, status=status))
        await session.commit()
```

- [ ] **Step 3: Regenerar el JSON desde la BD dev**

Run: `./venv/Scripts/python.exe export_seed.py`
Expected: `domain_lender_map.json: 17 dominios` (14 APROBADO + 3 ruido + los nuevos POR_APROBAR que hayan surgido).

- [ ] **Step 4: Verificar el JSON**

Run: `./venv/Scripts/python.exe -c "import json; d=json.load(open('domain_lender_map.json',encoding='utf-8')); print(type(d).__name__, len(d)); print(d[0])"`
Expected: `list N` y el primer elemento con claves `domain`, `lender_name`, `status`.

- [ ] **Step 5: Commit**

```bash
git add seed_db.py export_seed.py domain_lender_map.json
git commit -m "feat(seed): status de lender en export/seed para produccion"
```

---

## Notas de ejecución

- Las tareas 1-2 y 4-7 son puras (pytest, sin BD) y se pueden ejecutar/verificar sin postgres.
- Las tareas 3, 8, 9, 10 tocan la BD dev: requieren postgres corriendo y **no** deben usar `seed_db.py` (borra correos). Usar `migrate_preflight.py`.
- Orden obligatorio: Task 2 (modelos) → Task 3 (migración) antes de Task 8/9.
- Tras Task 8, `email_classifications` reflejará solo sobrevivientes; es el comportamiento esperado del nuevo flujo.
