"""Applicant ORM model — the person being underwritten.

Applicants are not users of the console and have no row in `users`. They can
sign in to one thing, the read-only client portal, with the `portal_id` and
password hash held here (see `routers/portal.py`).

`name` and `phone` are entered by the operator for the carrier's own reference
and are deliberately not taken from any uploaded file's header — those
identifiers are stripped on the way in.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Applicant(Base):
    __tablename__ = "applicants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Assigned by the database (applicants_ref_seq -> HL-000123) by a BEFORE
    # INSERT trigger, so never set this from Python: leave it out of the INSERT
    # and read it back after the flush.
    external_ref: Mapped[str] = mapped_column(String(100), nullable=False)

    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Identity photo. No model reads this — it exists so the operator can confirm
    # they are talking to the right person.
    face_photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Client portal sign-in. `portal_id` is random rather than the HL-
    # reference: the reference is a sequence, so it reveals how many
    # applications exist and is known to staff, which makes it a poor login
    # name. The password is generated at intake and only its hash is kept.
    portal_id: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
