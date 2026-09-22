"""Clients and analytics, as the console reads them."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.application import ApplicationStatus
from app.schemas.auth import BaseSchema


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
