"""Tenant (Carrier Organization) ORM model."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(Base):
    """Subscribing insurance carrier tenant model."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_tier: Mapped[str] = mapped_column(
        String(50), nullable=False, default="standard"
    )
    # Working days an applicant is told a decision usually takes. Copied onto
    # each application as a date at submit, so changing it does not move
    # promises already made.
    turnaround_business_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    # Risk-score tier boundaries. Every score snapshots the boundaries it was
    # tiered with, so changing these affects new scores only.
    tier_low_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("30")
    )
    tier_moderate_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("65")
    )

    # Pricing policy: monthly premium for the low and moderate plans at the
    # reference cover. Premiums scale linearly with the cover requested.
    premium_low_bdt: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("5000")
    )
    premium_moderate_bdt: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("7500")
    )
    reference_cover_bdt: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("1000000")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", cascade="all, delete-orphan"
    )


class TenantSettingsChange(Base):
    """One change to a company's settings: who, when, and each field's before
    and after. Kept apart from `audit_log`, whose hash chain is per application;
    a company setting belongs to no application."""

    __tablename__ = "tenant_settings_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # {field: {"from": x, "to": y}} for each field that changed.
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False)
