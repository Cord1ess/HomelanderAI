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
    nid_number: str | None = None
    nominee_name: str | None = None
    nominee_relation: str | None = None
    nominee_phone: str | None = None
    consent_at: datetime | None = None
    # Set once their data was erased at their request.
    deleted_at: datetime | None = None
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
    """One calendar month: premiums due from the policies in force, and claims paid."""

    month: date
    premiums_due_bdt: Decimal
    claims_paid_bdt: Decimal


class BusinessSchema(BaseSchema):
    """The money side of the book, from issued policies and their claims.
    Premiums are collected by the bank; these are what falls due."""

    clients: int
    policies_active: int
    policies_cancelled: int
    policies_expired: int
    life_policies: int
    health_policies: int
    # What active policies bring in a year, and a month on average.
    premium_yearly_bdt: Decimal
    premium_monthly_bdt: Decimal
    # What the premiums are expected to cost in claims a year, and so what is
    # left for expenses, commission and profit.
    expected_claims_yearly_bdt: Decimal
    expected_margin_yearly_bdt: Decimal
    # The most the company would pay if every active policy were claimed: life
    # sums assured plus a year of hospital limits.
    sum_assured_in_force_bdt: Decimal
    largest_payout_bdt: Decimal | None = None
    average_payout_bdt: Decimal | None = None
    claims_open: int = 0
    # Open claims whose 90-day settlement date has passed.
    claims_overdue: int = 0
    claims_paid_bdt: Decimal = Decimal(0)
    # Approved and still to be paid by the bank.
    claims_owed_bdt: Decimal = Decimal(0)
    # Claims paid this year as a share of a year's premiums.
    loss_ratio_pct: float | None = None
    renewals_due: int = 0
    months: list[MonthMoneySchema] = Field(default_factory=list)
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
