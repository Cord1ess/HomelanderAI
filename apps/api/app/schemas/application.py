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
    # Where the portal sign-in is sent. Optional: without it the operator is
    # shown the credentials to hand over in person.
    email: str | None = Field(default=None, max_length=255)


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
    # When the applicant was told to expect an answer, and whether that has
    # passed while the carrier still holds the case.
    expected_by: date | None = None
    overdue: bool = False


class QueueSchema(BaseSchema):
    items: list[QueueItemSchema]
    total: int
    # Every status with at least one application, for the filter chips.
    counts: dict[str, int] = Field(default_factory=dict)


# ── turnaround ───────────────────────────────────────────────────────────────


class TurnaroundIn(BaseSchema):
    """Revise when the applicant can expect an answer.

    The reason is required: a date that moves with no explanation is exactly
    the silent slip this feature exists to replace. It is stored on the
    application and shown to the applicant.
    """

    expected_by: date
    reason: str = Field(..., min_length=3, max_length=300)


class TenantSettingsSchema(BaseSchema):
    name: str
    turnaround_business_days: int
    # Risk-score tier boundaries: low is up to and including low_max, moderate
    # up to and including moderate_max, elevated above that.
    tier_low_max: float
    tier_moderate_max: float
    # Pricing policy: monthly premium for the two quotable plans at the
    # reference cover; premiums scale linearly with the cover requested.
    premium_low_bdt: float
    premium_moderate_bdt: float
    reference_cover_bdt: float


class TenantSettingsIn(BaseSchema):
    """A partial update: only the fields sent are changed.

    Ranges here; the relationship between the two boundaries is checked in the
    endpoint against the values that will actually be stored, because one may
    be sent without the other.
    """

    turnaround_business_days: int | None = Field(default=None, ge=1, le=30)
    tier_low_max: float | None = Field(default=None, gt=0, lt=100)
    tier_moderate_max: float | None = Field(default=None, gt=0, lt=100)
    premium_low_bdt: float | None = Field(default=None, gt=0, le=10_000_000)
    premium_moderate_bdt: float | None = Field(default=None, gt=0, le=10_000_000)
    reference_cover_bdt: float | None = Field(default=None, gt=0, le=1_000_000_000)


class SettingsChangeSchema(BaseSchema):
    """One recorded change to the company's settings."""

    changed_at: datetime
    actor_name: str | None
    # {field: {"from": x, "to": y}}
    changes: dict[str, dict[str, float | int | None]]


# ── requested documents ──────────────────────────────────────────────────────


class RequestEvidenceIn(BaseSchema):
    """What the underwriter is asking the applicant for.

    At least one item, each in plain words. "More evidence needed" with nothing
    named is exactly the uselessness this replaces.
    """

    items: list[str] = Field(..., min_length=1)
    # Optional context for the applicant, shown above the list.
    note: str | None = Field(default=None, max_length=500)


class RequestedDocumentSchema(BaseSchema):
    id: UUID
    description: str
    requested_at: datetime
    requested_by_name: str | None = None
    fulfilled_at: datetime | None = None


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


class ArmRunSchema(BaseSchema):
    """One model's reading of this application, as it was stored.

    `details` is the arm's own report, whose shape differs per arm — the chest
    model reports 18 findings, the mortality arm a phenotypic age and a
    contribution per blood marker. The review screen picks the panel by `arm`.
    """

    arm: str
    arm_type: str
    version: str
    score: float | None = None
    details: dict = Field(default_factory=dict)
    error: str | None = None


class ClassifiedFileSchema(BaseSchema):
    """One file as triage sees it, for the intake review screen.

    `kind` is a proposal, not a decision. The operator confirms or corrects it
    before anything is scored, and `reason` is what lets them judge whether the
    proposal is sensible.
    """

    filename: str
    kind: str
    kind_label: str
    reason: str
    # Empty when nothing reads this kind yet, which is an ordinary outcome for
    # a lab report and is shown as such rather than as a failure.
    arms: list[str] = Field(default_factory=list)
    # Blocks submission until the operator chooses. An unrecognised file that
    # can be waved through is the whole safeguard undone.
    needs_choice: bool = False
    # A small preview so the operator checks a document, not a filename.
    thumbnail: str | None = None


class EvidenceChoiceSchema(BaseSchema):
    """One option in the correction dropdown on the review screen."""

    kind: str
    label: str
    arms: list[str] = Field(default_factory=list)


class ClassifyResponseSchema(BaseSchema):
    files: list[ClassifiedFileSchema]
    # Every kind the operator may pick from when correcting a row. A typed
    # model rather than a bare dict, so the generated TypeScript keeps its
    # shape and the dashboard cannot read a field that does not exist.
    choices: list[EvidenceChoiceSchema] = Field(default_factory=list)


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
    # The date the applicant was given, the reason for the latest revision if
    # any, and whether it has passed while the carrier still holds the case.
    expected_by: date | None = None
    expected_by_note: str | None = None
    overdue: bool = False

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
    # Every arm that ran, with its own score and report. `findings` and
    # `model_info` above describe the governing vision arm only.
    arms: list[ArmRunSchema] = Field(default_factory=list)
    files: list[FileSchema] = Field(default_factory=list)
    decision: DecisionSchema | None = None
    # What the underwriter has asked the applicant for, fulfilled or not. The
    # review screen shows the outstanding ones; the portal will show the same
    # list to the applicant.
    requested_documents: list[RequestedDocumentSchema] = Field(default_factory=list)
    # Why an arm produced nothing. The review screen must never show a blank
    # panel with no explanation.
    errors: list[str] = Field(default_factory=list)


class PortalCredentialsSchema(BaseSchema):
    """The applicant's portal sign-in, as created at intake.

    `password` is present only when it could not be emailed, so the operator can
    hand it over in person. It exists here once: only its hash is stored, and no
    endpoint can return it again.
    """

    portal_id: str
    password: str | None = None
    emailed: bool = False
    email: str | None = None


class SubmitResponseSchema(BaseSchema):
    id: UUID
    reference: str
    status: ApplicationStatus
    portal: PortalCredentialsSchema | None = None


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
