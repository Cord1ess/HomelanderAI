"""The human end of the pipeline: decisions, the audit chain, and notifications."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class UnderwriterDecisionType(enum.StrEnum):
    """Four actions, and deliberately no reject.

    A model finding is grounds for a closer look, never for an automated
    denial — escalation to a medical professional is how a hard case is handled
    (SPEC.md §1).
    """

    CONFIRMED_FAST_TRACK = "confirmed_fast_track"
    APPROVED_WITH_ADJUSTMENT = "approved_with_adjustment"
    ESCALATED_SENIOR_REVIEW = "escalated_senior_review"
    REQUESTED_ADDITIONAL_EVIDENCE = "requested_additional_evidence"
    # A person's decision not to insure, always with a reason and never made by
    # a model. Added 2026-10-04: a platform where everything is eventually
    # approved is not underwriting.
    DECLINED = "declined"


class NotificationType(enum.StrEnum):
    APPLICATION_SUBMITTED = "application_submitted"
    PROCESSING_COMPLETE = "processing_complete"
    TIER_ESCALATION = "tier_escalation"
    DECISION_RECORDED = "decision_recorded"
    EVIDENCE_REQUESTED = "evidence_requested"
    API_KEY_EXPIRING = "api_key_expiring"
    # A doctor has reviewed the results and returned the application.
    DOCTOR_REVIEWED = "doctor_reviewed"
    # Someone asked to see a client's details; an administrator answered.
    ACCESS_REQUESTED = "access_requested"
    ACCESS_DECIDED = "access_decided"
    # The client uploaded a requested document from their portal.
    DOCUMENTS_UPLOADED = "documents_uploaded"
    CLAIM_FILED = "claim_filed"
    CLAIM_UPDATED = "claim_updated"
    DELETION_REQUESTED = "deletion_requested"
    # An approval issued a policy; an administrator cancelled one.
    POLICY_ISSUED = "policy_issued"
    POLICY_CANCELLED = "policy_cancelled"


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
    # An approval's terms: an extra percentage on the premium, and conditions
    # the policy will not pay for.
    rating_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exclusions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # A decline's reason (a code from app/decline.py), the words the client
    # reads, and when they may apply again.
    decline_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decline_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reapply_after: Mapped[date | None] = mapped_column(Date, nullable=True)


class RequestedDocument(Base):
    """A document an underwriter has asked the applicant to supply.

    Requesting evidence is a pause, not a decision. `underwriter_decisions` is
    write-once, so if asking for a document consumed the one decision, nothing
    could be decided once the document arrived. This is its own row and its
    own application status, and the decision stays open.
    """

    __tablename__ = "requested_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    # In the underwriter's words, shown verbatim to the applicant.
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="SET NULL"), nullable=True
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


class DoctorReview(Base):
    """A doctor's verdict on the readers' results: accurate or inaccurate.

    Not a decision about the policy — that stays the underwriter's. The latest
    review is the tag the application carries back to them.
    """

    __tablename__ = "doctor_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ClientMessage(Base):
    """A doctor writing to the client directly, shown on their portal."""

    __tablename__ = "client_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    urgency: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    emailed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ClientAccessRequest(Base):
    """Someone asking to see one client's personal details, and why.

    Underwriters and doctors see a client's name and reference; the rest is
    the company owner's to hand out. An approval opens that client to the
    person who asked for `ACCESS_HOURS` (routers/access.py).
    """

    __tablename__ = "client_access_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id", ondelete="CASCADE"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
