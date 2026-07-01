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
