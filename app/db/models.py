"""
models.py — Modelos SQLAlchemy para PostgreSQL.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Text, Boolean, DateTime, JSON, UniqueConstraint, Float, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# ---------------------------------------------------------------------------
# Lender Waiver Matrix
# ---------------------------------------------------------------------------

class LenderWaiverMatrix(Base):
    __tablename__ = "lender_waiver_matrix"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lender: Mapped[str] = mapped_column(String(200), nullable=False)
    lender_aliases: Mapped[list] = mapped_column(JSON, default=list)
    waiver_type: Mapped[str] = mapped_column(String(200), nullable=False)
    triggers: Mapped[str] = mapped_column(Text, default="")
    evidence_required_ops: Mapped[str] = mapped_column(Text, default="")
    evidence_required_insurance: Mapped[str] = mapped_column(Text, default="")
    actions_to_automate: Mapped[str] = mapped_column(Text, default="")
    waiver_pack: Mapped[str] = mapped_column(Text, default="")

    # documents_expected esta normalizado en lender_waiver_documents (1 -> muchos).
    documents: Mapped[list["LenderWaiverDocument"]] = relationship(
        back_populates="lender_waiver",
        cascade="all, delete-orphan",
        order_by="LenderWaiverDocument.position",
    )

    __table_args__ = (
        UniqueConstraint("lender", "waiver_type", name="uq_lender_waiver"),
    )


# ---------------------------------------------------------------------------
# Documentos requeridos por combinacion lender-waiver (1 -> muchos)
# ---------------------------------------------------------------------------

class LenderWaiverDocument(Base):
    __tablename__ = "lender_waiver_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lender_waiver_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lender_waiver_matrix.id", ondelete="CASCADE"), nullable=False
    )
    document_name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    lender_waiver: Mapped["LenderWaiverMatrix"] = relationship(back_populates="documents")


# ---------------------------------------------------------------------------
# Domain → Lender mapping
# ---------------------------------------------------------------------------

class DomainLenderMap(Base):
    __tablename__ = "domain_lender_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    lender_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="POR_APROBAR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Correos de producción (Outlook / Graph API)
# ---------------------------------------------------------------------------

class ProductionEmail(Base):
    __tablename__ = "production_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(500), default="")
    case_id: Mapped[str] = mapped_column(String(500), default="")
    sender: Mapped[str] = mapped_column(String(500), default="")
    sender_domain: Mapped[str] = mapped_column(String(255), default="")
    to_recipients: Mapped[list] = mapped_column(JSON, default=list)
    cc_recipients: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(Text, default="")
    received_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    body_text: Mapped[str] = mapped_column(Text, default="")
    body_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_names: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Correos de entrenamiento (archivos .eml locales)
# ---------------------------------------------------------------------------

class TrainingEmail(Base):
    __tablename__ = "training_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(500), default="")
    sender: Mapped[str] = mapped_column(String(500), default="")
    sender_domain: Mapped[str] = mapped_column(String(255), default="")
    to_recipients: Mapped[list] = mapped_column(JSON, default=list)
    cc_recipients: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(Text, default="")
    received_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    body_text: Mapped[str] = mapped_column(Text, default="")
    body_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_names: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Resultados de clasificacion
# ---------------------------------------------------------------------------

class EmailClassification(Base):
    __tablename__ = "email_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    production_email_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("production_emails.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    lender: Mapped[str] = mapped_column(String(200), default="UNKNOWN")
    waiver_type: Mapped[str] = mapped_column(String(200), default="UNKNOWN")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_level: Mapped[str] = mapped_column(String(20), default="low")
    trigger_description: Mapped[str] = mapped_column(Text, default="")
    suggested_response: Mapped[str] = mapped_column(Text, default="")
    documents_expected: Mapped[list] = mapped_column(JSON, default=list)
    validation_details: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Features absorbidas de OGM_Lenders
    secondary_issues: Mapped[list] = mapped_column(JSON, default=list)
    communication_category: Mapped[str] = mapped_column(String(50), default="OPERATIONAL_WAIVER")
    escalate_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_attachments: Mapped[list] = mapped_column(JSON, default=list)

    # Human-in-the-loop: revision/correccion de la clasificacion
    status: Mapped[str] = mapped_column(String(20), default="classified")  # classified|reviewed|corrected
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    corrected_lender: Mapped[str | None] = mapped_column(String(200), nullable=True)
    corrected_waiver_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    correction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


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
    # PENDIENTE | GESTIONADO (auto, aprobacion) | DESCARTADO | CONTESTADO (manual)
    status: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # nota de descarte/respuesta manual
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("message_id", "stage", name="uq_review_message_stage"),
    )


# ---------------------------------------------------------------------------
# Inventario de archivos de SharePoint (Microsoft Graph)
# ---------------------------------------------------------------------------

class SharePointFile(Base):
    __tablename__ = "sharepoint_files"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # driveItem id de Graph
    drive_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    drive_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    parent_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_folder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    web_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sp_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sp_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
