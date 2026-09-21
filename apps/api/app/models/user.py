"""User ORM model: a member of a carrier's staff, in one of three roles."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class UserRole(enum.StrEnum):
    """The three staff roles. There are no others.

    Applicants are not in this list on purpose: they have no row in `users` and
    no role. They read their own application through the client portal with a
    generated portal ID and password (see `routers/portal.py`).

    `medical_professional` was `senior_underwriter` until 2026-09-22 (migration
    008); what it may do did not change.
    """

    # Takes applications in and decides the ones the models call low or moderate.
    UNDERWRITER = "underwriter"
    # Reads the clinical evidence on escalated cases and decides them.
    MEDICAL_PROFESSIONAL = "medical_professional"
    # Runs the carrier's workspace: staff accounts and carrier settings.
    ADMIN = "admin"


class User(Base):
    """System user belonging to a carrier tenant."""

    __tablename__ = "users"
    # Email is unique system-wide, not per company: sign-in asks only for an
    # email and password, so the same address in two companies would make the
    # account ambiguous.
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=UserRole.UNDERWRITER,
    )
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Users are never deleted — their past decisions must stay attributable —
    # so switching this off is how an account is retired.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
