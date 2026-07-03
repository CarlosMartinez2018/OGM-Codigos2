"""
business_context.py -- Carga el contexto de negocio de Acento.

Fuente: data/business_context.json (que hace Acento, flujo de correos, categorias
de comunicacion, escalado de riesgo, guardrails, injection guard). Activo listo
para alimentar al LLM y afinar el clasificador cuando se retome esa tarea. Por
ahora NO se cablea al clasificador (ver memoria afinamiento-clasificacion).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "business_context.json"


@lru_cache(maxsize=1)
def load_business_context() -> dict:
    if not _PATH.exists():
        return {}
    return json.loads(_PATH.read_text(encoding="utf-8"))


def company_summary() -> str:
    c = load_business_context().get("company", {})
    parts = [c.get("name"), c.get("description"), c.get("business_model")]
    return " ".join(p for p in parts if p)


def communication_categories() -> list[dict]:
    return load_business_context().get("communication_categories", [])


def critical_keywords() -> list[str]:
    return load_business_context().get("risk_escalation", {}).get("critical_keywords", [])


def injection_patterns() -> list[str]:
    return load_business_context().get("injection_guard", {}).get("blocked_patterns", [])


def guardrails() -> list[str]:
    return load_business_context().get("guardrails", [])
