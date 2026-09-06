"""Application and the evidence attached to it."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, pg_enum


class ApplicationStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SCORED = "scored"
    DECIDED = "decided"


class EvidenceFileType(enum.StrEnum):
    DICOM = "dicom"
    # A radiograph uploaded as PNG or JPEG. Most are.
    IMAGE = "image"
    LAB_REPORT = "lab_report"
    CLINICAL_NOTE = "clinical_note"
    QUESTIONNAIRE = "questionnaire"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        nullable=False,
        default=ApplicationStatus.SUBMITTED,
    )

    coverage_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    coverage_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    policy_term: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Which arms to run, e.g. ["cxr_lung"]. A list, not columns, so adding an
    # arm needs no migration.
    models_requested: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Keyed by arm id: {"cxr_lung": {"symptoms": {...}, "history": {...}}}.
    # JSONB because the field set changes every time an arm is added.
    declared_history: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    applicant: Mapped["Applicant"] = relationship("Applicant", lazy="joined")  # noqa: F821


class EvidenceFile(Base):
    __tablename__ = "evidence_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    file_type: Mapped[EvidenceFileType] = mapped_column(
        pg_enum(EvidenceFileType, "evidence_file_type"), nullable=False
    )
    # Relative to settings.data_dir. Storing it relative keeps the rows valid
    # when the folder moves between machines.
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # sha256 of what is actually on disk, i.e. the de-identified PNG.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deidentified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_arm_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_arms.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
