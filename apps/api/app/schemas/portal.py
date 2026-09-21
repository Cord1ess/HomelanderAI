"""What an applicant may see about their own application.

**There is no field here for a risk score, a tier, or a model finding, and that
is the design.** The scores come from models that are explicitly not diagnostic
and, for the chest arm, tested on one hospital's data. Telling someone "75,
elevated, infiltration" through an insurance portal, with no clinician present,
would be delivering an unvalidated clinical impression as though it were a
result. The underwriter's decision is different: it is a commercial fact about
their policy and they are entitled to it.

So the omission is structural rather than a filter. A response model that has no
such field cannot leak one because somebody forgot to strip it, and the test
suite asserts the serialised payload contains none of those keys.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.schemas.auth import BaseSchema


class PortalLoginIn(BaseSchema):
    portal_id: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=1, max_length=200)


class PortalDocumentSchema(BaseSchema):
    """One thing the underwriter has asked for, in their words."""

    description: str
    requested_at: datetime
    received: bool


class PortalOfferSchema(BaseSchema):
    """The outcome, once a person has recorded it. Never a prediction."""

    outcome: str
    plan_name: str | None = None
    monthly_premium_bdt: Decimal | None = None
    decided_at: datetime


class PortalStatusSchema(BaseSchema):
    reference: str
    applicant_name: str | None = None
    coverage_type: str | None = None
    coverage_amount: Decimal | None = None
    submitted_at: datetime

    # Where the application is, in plain words.
    stage: str
    stage_label: str
    stage_detail: str

    # A date, never a countdown. `overdue` is only ever true while the carrier
    # holds the case, never while it waits on the applicant.
    expected_by: date | None = None
    expected_by_note: str | None = None
    overdue: bool = False

    documents: list[PortalDocumentSchema] = Field(default_factory=list)
    offer: PortalOfferSchema | None = None
