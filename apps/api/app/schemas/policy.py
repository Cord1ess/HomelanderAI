"""Policies as the API shows them: terms, the payment schedule, and totals."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.policies import GRACE_DAYS
from app.schemas.auth import BaseSchema

PaymentMethod = Literal["bkash", "nagad", "rocket", "bank", "card", "cash"]


class InstallmentSchema(BaseSchema):
    number: int
    due_date: date
    amount_bdt: Decimal
    # paid | overdue | due | upcoming
    status: str
    paid_on: date | None = None
    method: str | None = None


class PolicySchema(BaseSchema):
    id: UUID
    policy_number: str
    application_id: UUID
    client_id: UUID
    client_reference: str | None = None
    client_name: str | None = None
    plan_name: str
    coverage_type: str | None = None
    # Paid out on a claim.
    sum_assured_bdt: Decimal
    monthly_premium_bdt: Decimal
    yearly_premium_bdt: Decimal
    # What the client pays over the whole term, if every month is paid.
    total_premium_bdt: Decimal
    term_years: int
    start_date: date
    end_date: date
    status: str
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    cancelled_by_name: str | None = None
    paid_count: int = 0
    paid_total_bdt: Decimal = Decimal(0)
    overdue_count: int = 0
    overdue_total_bdt: Decimal = Decimal(0)
    next_due: date | None = None
    next_amount_bdt: Decimal | None = None
    months_total: int = 0
    grace_days: int = GRACE_DAYS
    installments: list[InstallmentSchema] = Field(default_factory=list)


class CancelIn(BaseSchema):
    reason: str = Field(..., min_length=5, max_length=1000)


class PaymentIn(BaseSchema):
    # The month being paid; the oldest unpaid one when left out.
    due_date: date | None = None
    method: PaymentMethod = "cash"
    reference: str | None = Field(default=None, max_length=100)
