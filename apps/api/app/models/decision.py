"""The human end of the pipeline: decisions, the audit chain, and notifications."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class UnderwriterDecisionType(enum.StrEnum):
    """Four actions, and deliberately no reject.

    A model finding is grounds for a closer look, never for an automated
    denial — escalation to a senior underwriter is how a hard case is handled
    (SPEC.md §1).
    """

    CONFIRMED_FAST_TRACK = "confirmed_fast_track"
    APPROVED_WITH_ADJUSTMENT = "approved_with_adjustment"
    ESCALATED_SENIOR_REVIEW = "escalated_senior_review"
    REQUESTED_ADDITIONAL_EVIDENCE = "requested_additional_evidence"


class NotificationType(enum.StrEnum):
    APPLICATION_SUBMITTED = "application_submitted"
    PROCESSING_COMPLETE = "processing_complete"
    TIER_ESCALATION = "tier_escalation"
    DECISION_RECORDED = "decision_recorded"
    EVIDENCE_REQUESTED = "evidence_requested"
    API_KEY_EXPIRING = "api_key_expiring"


class NotificationChannel(enum.StrEnum):
    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"


class NotificationStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class UnderwriterDecision(Base):
    """Write-once. The unique constraint on application_id is what enforces it —
    a second decision is rejected by the database, not just by the UI."""

    __tablename__ = "underwriter_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: a decision must stay attributable, so the user who
    # made it cannot be deleted out from under it.
    underwriter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[UnderwriterDecisionType] = mapped_column(
        pg_enum(UnderwriterDecisionType, "underwriter_decision_type"), nullable=False
    )
    final_premium: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    """Append-only, enforced by triggers in db/schema.sql.

    Each row carries the hash of the one before it, so a quiet edit of any
    historical row breaks every hash after it. The chain is built by
    `app/audit.py`; this is only where it is stored.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # NULL means the system acted, not a person — scoring, for instance.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Notification(Base):
    """In-app only in Phase 1 — these go to staff, never to applicants."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        pg_enum(NotificationType, "notification_type"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        pg_enum(NotificationChannel, "notification_channel"), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
