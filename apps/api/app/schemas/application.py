"""Request and response shapes for the application endpoints.

Everything inherits the camelCase aliasing in `schemas/auth.py`, so the React
side reads `submittedAt` while Python keeps `submitted_at`.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.application import ApplicationStatus
from app.models.decision import UnderwriterDecisionType
from app.schemas.auth import BaseSchema

# ── intake ───────────────────────────────────────────────────────────────────


class ApplicantIn(BaseSchema):
    name: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., min_length=1, max_length=30)
    date_of_birth: date | None = None
    sex: str | None = None


class CoverageIn(BaseSchema):
    coverage_type: str | None = None
    coverage_amount: Decimal | None = None
    policy_term: str | None = None


class IntakeIn(BaseSchema):
    """The JSON half of the multipart intake request.

    Sent as a single `payload` field rather than flattened form fields: it is
    nested, and a JSON blob keeps the shape identical to what the form already
    builds in the browser.
    """

    applicant: ApplicantIn
    coverage: CoverageIn = Field(default_factory=CoverageIn)
    models_requested: list[str] = Field(default_factory=list)
    # Keyed by arm id: {"cxr_lung": {"symptoms": {...}, "history": {...}}}
    declared_history: dict = Field(default_factory=dict)


# ── queue ────────────────────────────────────────────────────────────────────


class QueueItemSchema(BaseSchema):
    id: UUID
    reference: str
    applicant_name: str | None
    submitted_at: datetime
    status: ApplicationStatus
    crs: float | None = None
    tier: str | None = None
    coverage_amount: Decimal | None = None
    # Which models the operator asked for, so the queue shows what is pending.
    models_requested: list[str] = Field(default_factory=list)


class QueueSchema(BaseSchema):
    items: list[QueueItemSchema]
    total: int
    # Every status with at least one application, for the filter chips.
    counts: dict[str, int] = Field(default_factory=dict)


# ── detail ───────────────────────────────────────────────────────────────────


class FindingSchema(BaseSchema):
    """One of the backbone's 18 findings.

    `probability` is what the model reported; `contribution` is how much that
    finding actually moved the TB score. They disagree often, and the
    contribution is the one that explains the number.
    """

    label: str
    probability: float
    contribution: float


class AdjustmentSchema(BaseSchema):
    key: str
    points: float
    reason: str


class ScoreSchema(BaseSchema):
    crs: float
    tier: str
    method: str
    thresholds: dict = Field(default_factory=dict)
    vision_score: float | None = None
    computed_at: datetime


class ModelInfoSchema(BaseSchema):
    """Provenance that has to travel with the score rather than sit in a doc —
    the model has only ever been tested on one hospital."""

    scorer: str | None = None
    backbone: str | None = None
    validation: str | None = None
    cv_auc: float | None = None


class PlanSchema(BaseSchema):
    """The policy recommendation for a tier, priced for this application.

    Illustrative, not actuarial: Idea.md gives a premium per tier but no rate
    card, so `baseMonthlyBdt` is the premium at `referenceCoverBdt` and
    `monthlyPremiumBdt` scales it to the cover actually requested. The screen
    says so wherever it shows a number.
    """

    tier: str
    name: str
    recommendation: str
    human_step: str
    base_monthly_bdt: float | None = None
    reference_cover_bdt: float
    monthly_premium_bdt: float | None = None
    wellness_discount_eligible: bool = False


class PricingSchema(BaseSchema):
    """The full plan table, with each tier's score band attached.

    One response so the pricing screen cannot show a premium against the wrong
    band: the cut-points come from `scoring.Thresholds`, the rates from
    `plans.PLANS`, and neither is retyped in the dashboard.
    """

    plans: list["PlanSchema"]
    low_max: float
    moderate_max: float
    # Echoed back so the screen can say what the premiums were worked out for.
    coverage_amount: float | None = None


class ModelSchema(BaseSchema):
    """One entry in the intake form's model menu.

    `available` is derived from the arm registry, so the form can never offer a
    model that will not actually run.
    """

    id: str
    label: str
    evidence: str
    screens_for: str
    available: bool
    arm_name: str | None = None
    arm_version: str | None = None
    validation: str | None = None


class FileSchema(BaseSchema):
    id: UUID
    kind: str  # "evidence" | "gradcam"
    filename: str | None = None
    mime_type: str | None = None


class DecisionSchema(BaseSchema):
    decision: UnderwriterDecisionType
    final_premium: Decimal | None = None
    decided_at: datetime
    underwriter_name: str | None = None


class ApplicationDetailSchema(BaseSchema):
    id: UUID
    reference: str
    status: ApplicationStatus
    submitted_at: datetime
    evaluated_at: datetime | None = None

    applicant: ApplicantIn
    coverage: CoverageIn
    models_requested: list[str] = Field(default_factory=list)
    declared_history: dict = Field(default_factory=dict)

    score: ScoreSchema | None = None
    # What the tier means for the policy, priced against the cover requested.
    plan: PlanSchema | None = None
    adjustments: list[AdjustmentSchema] = Field(default_factory=list)
    findings: list[FindingSchema] = Field(default_factory=list)
    model_info: ModelInfoSchema | None = None
    files: list[FileSchema] = Field(default_factory=list)
    decision: DecisionSchema | None = None
    # Why an arm produced nothing. The review screen must never show a blank
    # panel with no explanation.
    errors: list[str] = Field(default_factory=list)


class SubmitResponseSchema(BaseSchema):
    id: UUID
    reference: str
    status: ApplicationStatus


# ── decision ─────────────────────────────────────────────────────────────────


class DecisionIn(BaseSchema):
    decision: UnderwriterDecisionType
    final_premium: Decimal | None = None


# ── audit ────────────────────────────────────────────────────────────────────


class AuditEntrySchema(BaseSchema):
    id: UUID
    event_type: str
    payload: dict
    actor_name: str | None = None
    created_at: datetime


class AuditTrailSchema(BaseSchema):
    entries: list[AuditEntrySchema]
    # Whether the hash chain still verifies. False means a stored row was
    # altered after the fact.
    intact: bool
    broken_at: str | None = None


# ── notifications ────────────────────────────────────────────────────────────


class NotificationSchema(BaseSchema):
    id: UUID
    message: str
    notification_type: str
    application_id: UUID | None = None
    reference: str | None = None
    created_at: datetime
    read_at: datetime | None = None
