"""Policies and claims as the API shows them."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.auth import BaseSchema


class PolicySchema(BaseSchema):
    id: UUID
    policy_number: str
    application_id: UUID
    client_id: UUID
    client_reference: str | None = None
    client_name: str | None = None
    # "life" or "health", and how it reads ("Term life", "Hospital cover").
    product: str
    product_name: str
    plan_name: str
    coverage_type: str | None = None
    # Life: paid out on death. Health: the most paid in hospital bills a year.
    sum_assured_bdt: Decimal
    annual_premium_bdt: Decimal
    monthly_premium_bdt: Decimal
    # How the client pays the bank, and the amount each time.
    premium_mode: str
    premium_amount_bdt: Decimal
    # What the client pays over the whole term if every premium is paid.
    total_premium_bdt: Decimal
    rating_pct: int = 0
    exclusions: list[str] = Field(default_factory=list)
    term_years: int
    start_date: date
    end_date: date
    # Stored: "active" or "cancelled". Shown: "active", "cancelled" or
    # "expired" once the end date has passed.
    status: str
    effective_status: str
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    cancelled_by_name: str | None = None
    free_look_until: date | None = None
    in_free_look: bool = False
    waiting_until: date | None = None
    preexisting_until: date | None = None
    # The next date a premium falls due, while the policy runs.
    next_premium_due: date | None = None
    # Hospital cover nearing its yearly renewal.
    renewal_due: bool = False
    days_to_end: int | None = None
    # Claims on this policy.
    claims_open: int = 0
    claims_paid_bdt: Decimal = Decimal(0)
    # Hospital cover: what is left of this year's limit after approved claims.
    remaining_limit_bdt: Decimal | None = None


class CancelIn(BaseSchema):
    reason: str = Field(..., min_length=5, max_length=1000)


# ── claims ───────────────────────────────────────────────────────────────────


class ClaimDocumentSchema(BaseSchema):
    id: UUID
    file_name: str | None = None
    uploaded_by_client: bool = False
    created_at: datetime


class ClaimSchema(BaseSchema):
    id: UUID
    claim_number: str
    policy_id: UUID
    policy_number: str | None = None
    product: str | None = None
    client_id: UUID
    client_name: str | None = None
    client_reference: str | None = None
    claim_type: str
    event_date: date
    claimed_amount_bdt: Decimal
    description: str
    hospital: str | None = None
    claimant_name: str | None = None
    # submitted | documents_requested | under_review | approved | rejected | settled
    status: str
    documents_note: str | None = None
    documents_complete_at: datetime | None = None
    # By law a claim is settled within 90 days of the documents being complete.
    settle_by: date | None = None
    days_left: int | None = None
    approved_amount_bdt: Decimal | None = None
    decision_note: str | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    settled_at: datetime | None = None
    settlement_reference: str | None = None
    filed_by_client: bool = False
    created_at: datetime
    # Things the person deciding should know: a waiting period not yet over,
    # an exclusion that may apply, an amount over what is left of the limit.
    checks: list[str] = Field(default_factory=list)
    # The most this claim can pay under the policy.
    payable_limit_bdt: Decimal | None = None
    documents: list[ClaimDocumentSchema] = Field(default_factory=list)


class ClaimIn(BaseSchema):
    """A claim, from the client's portal or from staff on someone's behalf."""

    event_date: date
    claimed_amount_bdt: Decimal = Field(..., gt=0)
    description: str = Field(..., min_length=5, max_length=2000)
    hospital: str | None = Field(default=None, max_length=200)
    claimant_name: str | None = Field(default=None, max_length=200)
    # An accident is covered from the first day of hospital cover.
    accident: bool = False


class ClaimActionIn(BaseSchema):
    action: Literal["request_documents", "documents_complete", "approve", "reject", "settle"]
    note: str | None = Field(default=None, max_length=2000)
    approved_amount_bdt: Decimal | None = Field(default=None, gt=0)
    settlement_reference: str | None = Field(default=None, max_length=100)
