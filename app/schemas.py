"""
schemas.py — Modelo de datos unificado para correos electrónicos.

Compatible con ambas fuentes: archivos .eml y Microsoft Graph API (Outlook).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import re
from typing import Optional


# Cota dura de trabajo para la limpieza: cuerpos gigantes (dumps, HTML inline)
# se truncan antes de aplicar regex. Sin esta cota, un correo de ~1MB puede
# colgar el pipeline entero (la limpieza corre antes que cualquier gate).
_MAX_CLEAN_LEN = 120_000


def clean_email_body(text: str) -> str:
    """Elimina firmas, disclaimers, enlaces largos y mantiene el hilo original de correos."""
    if not text:
        return ""
    text = text[:_MAX_CLEAN_LEN]

    # 1. Eliminar advertencias de seguridad (suelen venir al principio del correo)
    text = re.sub(r'(?i)CAUTION:\s*This email originated from outside.*?is safe\.\s*', '', text)
    text = re.sub(r'(?i)PRECAUCI[OÓ]N:\s*Este correo.*?es seguro\.\s*', '', text)

    # 2. Acortar y limpiar enlaces (Graph API suele poner <url> o [url])
    text = re.sub(r'<\s*https?://[^>]+>', '[Enlace]', text)
    text = re.sub(r'\[\s*https?://[^\]]+\]', '[Enlace]', text)
    text = re.sub(r'https?://[^\s<>"\']{25,}', '[Enlace]', text)

    # Patrones que indican el inicio de un correo citado (hilo)
    quote_patterns = [
        r"(?im)^_{10,}\s*\n^De:\s",
        r"(?im)^_{10,}\s*\n^From:\s",
        r"(?im)^De:\s+.*",
        r"(?im)^From:\s+.*",
        r"(?im)^-+\s*Original Message\s*-+",
        r"(?im)^-+\s*Mensaje Original\s*-+",
        # Cuantificadores acotados y clases negadas: la version con `.*<.*@.*>.*`
        # backtrackeaba polinomicamente (15s en un cuerpo de 64KB).
        r"(?im)^.{0,200}<[^<>\s]{1,120}@[^<>\s]{1,120}>.{0,200}escribió:\s*$",
        r"(?im)^.{0,200}<[^<>\s]{1,120}@[^<>\s]{1,120}>.{0,200}wrote:\s*$"
    ]

    # Patrones que indican el inicio de una firma o disclaimer corporativo
    sig_patterns = [
        r"(?im)^-- \s*$",
        r"(?im)^_{15,}\s*$",
        r"(?im)^-{15,}\s*$",
        r"(?im)^Saludos cordiales,?\s*$",
        r"(?im)^Saludos,?\s*$",
        r"(?im)^Un saludo,?\s*$",
        r"(?im)^Atentamente,?\s*$",
        r"(?im)^Atte\.?,?\s*$",
        r"(?im)^Cordialmente,?\s*$",
        r"(?im)^Best regards,?\s*$",
        r"(?im)^Regards,?\s*$",
        r"(?im)^Thanks,?\s*$",
        r"(?im)^Enviado desde mi \w+",
        r"(?im)^Sent from my \w+",
        r"(?im)^Obtener Outlook para \w+",
        r"(?im)^Get Outlook for \w+",
        r"(?im)^Este correo(?: electr[óo]nico)? y cualquier archivo.*",
        r"(?im)^This email and any attachments.*",
        r"(?im)^AVISO LEGAL:.*",
        r"(?im)^CONFIDENCIALIDAD:.*",
        r"(?im)^La informaci[oó]n contenida en este correo.*",
        r"(?im)^Este mensaje y sus archivos.*",
        r"(?im)^Por favor, considere el medio ambiente antes de imprimir.*",
        r"(?im)^Please consider the environment before printing.*"
    ]

    # 1. Encontrar todos los inicios de citas para dividir en bloques
    matches = []
    for qp in quote_patterns:
        for m in re.finditer(qp, text):
            matches.append(m.start())
            
    matches.sort()
    filtered_matches = []
    for m in matches:
        if not filtered_matches or m > filtered_matches[-1] + 10:
            filtered_matches.append(m)

    blocks = []
    start = 0
    for idx in filtered_matches:
        if idx > start:
            blocks.append(text[start:idx])
        start = idx
    if start < len(text):
        blocks.append(text[start:])

    # 2. Limpiar firmas en cada bloque
    cleaned_blocks = []
    for block in blocks:
        sig_start = len(block)
        for sp in sig_patterns:
            m = re.search(sp, block)
            if m and m.start() < sig_start:
                sig_start = m.start()
        
        cleaned = block[:sig_start].strip()
        if cleaned:
            cleaned_blocks.append(cleaned)

    # Unir bloques limpiados con saltos de línea dobles
    return "\n\n".join(cleaned_blocks)


@dataclass
class EmailData:
    """Representa un correo electrónico parseado desde cualquier fuente."""

    # --- Identificación -------------------------------------------------------
    message_id: str = ""                    # Cabecera Message-ID (RFC 2822)
    conversation_id: str = ""               # ID de hilo/conversación (Graph o generado)

    # --- Remitente ------------------------------------------------------------
    sender: str = ""                        # Dirección de correo del remitente
    sender_domain: str = ""                 # Dominio extraído del sender

    # --- Destinatarios --------------------------------------------------------
    to_recipients: list[str] = field(default_factory=list)   # Lista To:
    to_domains:    list[str] = field(default_factory=list)   # Dominios únicos To:
    cc_recipients: list[str] = field(default_factory=list)   # Lista Cc:
    cc_domains:    list[str] = field(default_factory=list)   # Dominios únicos Cc:

    # --- Metadatos del correo -------------------------------------------------
    subject: str = ""
    received_date: Optional[datetime] = None

    # --- Cuerpo ---------------------------------------------------------------
    body_text: str = ""                     # Texto plano
    body_html: str = ""                     # HTML original
    body_preview: Optional[str] = None      # Primeros 200 caracteres (generado)

    # --- Adjuntos -------------------------------------------------------------
    has_attachments: bool = False
    attachment_names: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Genera body_preview y sender_domain si no fueron proporcionados. Limpia firmas y enlaces."""
        # Limpieza del cuerpo del texto
        if self.body_text:
            self.body_text = clean_email_body(self.body_text)

        # Preview automático desde texto plano limpio
        if self.body_preview is None:
            source_text = self.body_text or ""
            self.body_preview = source_text[:200].replace("\n", " ").strip() or None

        # Dominio del remitente
        if not self.sender_domain and "@" in self.sender:
            self.sender_domain = self.sender.split("@")[1].lower()

        # Generar conversación ID fallback si no existe
        if not self.conversation_id:
            norm_subj = re.sub(r'(?i)^\s*(re|fw|fwd|rv|enc)\s*:\s*', '', self.subject or "")
            norm_subj = norm_subj.strip().lower()
            if norm_subj:
                self.conversation_id = hashlib.md5(norm_subj.encode("utf-8")).hexdigest()
            else:
                self.conversation_id = "unknown_conv"

    # --- Helpers de acceso rápido ---------------------------------------------

    @property
    def sender_email(self) -> str:
        """Devuelve solo la dirección de correo del remitente (sin nombre)."""
        s = self.sender
        if "<" in s and ">" in s:
            return s[s.index("<") + 1 : s.index(">")].strip()
        return s.strip()

    @property
    def sender_name(self) -> str:
        """Devuelve solo el nombre del remitente (sin dirección)."""
        s = self.sender
        if "<" in s:
            return s[:s.index("<")].strip().strip('"')
        return ""

    @property
    def all_recipients(self) -> list[str]:
        """Todos los destinatarios (To + Cc) en una sola lista."""
        return self.to_recipients + self.cc_recipients


@dataclass
class ClassificationResult:
    """Resultado final de clasificacion de un correo de produccion."""

    lender: str = "UNKNOWN"
    waiver_type: str = "UNKNOWN"
    confidence_score: float = 0.0
    confidence_level: str = "low"
    trigger_description: str = ""
    suggested_response: str = ""
    documents_expected: list[str] = field(default_factory=list)
    required_evidence_ops: str = ""
    required_evidence_insurance: str = ""
    waiver_pack: str = ""
    actions_to_automate: str = ""
    raw_llm_response: Optional[str] = None
    validation_details: dict = field(default_factory=dict)

    # --- Features absorbidas de OGM_Lenders -----------------------------------
    secondary_issues: list[str] = field(default_factory=list)   # waivers adicionales del mismo lender
    communication_category: str = "OPERATIONAL_WAIVER"          # LENDER_COMPLIANCE|LENDER_ALERT|WAIVER_REQUEST|COVENANT_BREACH|OPERATIONAL_WAIVER
    escalate_for_review: bool = False                           # riesgo critico o inyeccion detectada
    suggested_attachments: list[str] = field(default_factory=list)  # PDFs candidatos por lender
