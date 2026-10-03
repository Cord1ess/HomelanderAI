"""Clients and analytics, as the console reads them."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.application import ApplicationStatus
from app.schemas.auth import BaseSchema
from app.schemas.policy import PolicySchema


class ClientSchema(BaseSchema):
    """One applicant and where their latest application stands."""

    id: UUID
    reference: str
    name: str | None
    phone: str | None
    email: str | None
    portal_id: str | None
    created_at: datetime
    applications: int
    latest_application_id: UUID | None
    latest_status: ApplicationStatus | None
    latest_tier: str | None
    latest_crs: float | None
    coverage_type: str | None
    coverage_amount: Decimal | None
    expected_by: date | None
    overdue: bool = False
    # Whether the signed-in person may see this client's personal details:
    # "full" (an administrator), "granted" (an approval still running, until
    # `access_until`), "pending", "declined" or "none". Without it, phone,
    # email and portal ID come back empty.
    access: str = "full"
    access_until: datetime | None = None


class ClientApplicationSchema(BaseSchema):
    """One of a client's applications, as their profile lists it."""

    id: UUID
    reference: str
    submitted_at: datetime
    status: ApplicationStatus
    crs: float | None = None
    tier: str | None = None
    coverage_type: str | None = None
    coverage_amount: Decimal | None = None
    policy_term: str | None = None
    expected_by: date | None = None
    overdue: bool = False
    decision: str | None = None
    decided_at: datetime | None = None
    # The newest doctor's verdict on the results, if a doctor has seen them.
    doctor_verdict: str | None = None


class ClientProfileSchema(BaseSchema):
    """Who the client is, and everything they have applied for."""

    id: UUID
    reference: str
    name: str | None
    phone: str | None
    email: str | None
    portal_id: str | None
    date_of_birth: date | None = None
    sex: str | None = None
    height_cm: Decimal | None = None
    weight_kg: Decimal | None = None
    created_at: datetime
    applications: list[ClientApplicationSchema] = Field(default_factory=list)
    # Every policy issued to this client, newest first.
    policies: list[PolicySchema] = Field(default_factory=list)


class CountSchema(BaseSchema):
    key: str
    count: int


class CoverTypeSchema(BaseSchema):
    coverage_type: str
    count: int
    amount_bdt: Decimal
    approved: int


class WeekSchema(BaseSchema):
    week_of: date
    applications: int
    decided: int


class ArmActivitySchema(BaseSchema):
    arm: str
    runs: int
    failed: int
    average_score: float | None


class MonthMoneySchema(BaseSchema):
    """One calendar month: what policies in force were due to pay, and what
    was actually recorded as paid."""

    month: date
    expected_bdt: Decimal
    collected_bdt: Decimal


class BusinessSchema(BaseSchema):
    """The money side of the book, from issued policies and recorded payments."""

    clients: int
    policies_active: int
    policies_cancelled: int
    # What active policies bring in if every client pays.
    premium_monthly_bdt: Decimal
    premium_yearly_bdt: Decimal
    # What was recorded as paid.
    collected_this_month_bdt: Decimal
    collected_this_year_bdt: Decimal
    collected_all_time_bdt: Decimal
    overdue_bdt: Decimal
    overdue_policies: int
    # Paid out if every active policy were claimed today: the company's exposure.
    sum_assured_in_force_bdt: Decimal
    largest_payout_bdt: Decimal | None = None
    average_payout_bdt: Decimal | None = None
    months: list[MonthMoneySchema] = Field(default_factory=list)
    # Every policy, with what it pays out on a claim.
    policies: list[PolicySchema] = Field(default_factory=list)


class AnalyticsSchema(BaseSchema):
    """The company's book. Every figure is backed by rows, none is estimated."""

    applications: int
    decided: int
    approved: int
    escalated: int
    waiting: int
    average_crs: float | None

    by_status: list[CountSchema] = Field(default_factory=list)
    by_tier: list[CountSchema] = Field(default_factory=list)
    by_decision: list[CountSchema] = Field(default_factory=list)

    cover_requested_bdt: Decimal
    cover_approved_bdt: Decimal
    # The sum of the monthly premiums on approved applications.
    monthly_premium_book_bdt: Decimal
    by_cover_type: list[CoverTypeSchema] = Field(default_factory=list)

    average_days_to_decide: float | None
    decided_on_time: int
    decided_late: int

    weeks: list[WeekSchema] = Field(default_factory=list)
    arms: list[ArmActivitySchema] = Field(default_factory=list)
    business: BusinessSchema | None = None
