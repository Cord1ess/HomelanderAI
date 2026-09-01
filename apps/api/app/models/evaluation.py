"""What the models produced: runs, sub-scores, explanations, and the composite.

One `Application` has one `ModelRun` per (arm, piece of evidence). Each run that
succeeds gets a `SubScore`; the run may also leave an `ExplanationArtifact` (the
Grad-CAM heatmap). The `CompositeScore` is the single number the underwriter
sees, and it stores the tier cut-points used at the time so an old score can
still be explained after they are re-tuned.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum


class ModelArmType(enum.StrEnum):
    VISION = "vision"
    NLP = "nlp"
    TABULAR = "tabular"


class ModelRunStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExplanationArtifactType(enum.StrEnum):
    GRADCAM = "gradcam"
    SHAP = "shap"
    ANNOTATED_TEXT = "annotated_text"


class RiskTier(enum.StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ModelArm(Base):
    """The registry of arms. Shared across tenants — a model is not owned by a
    carrier — so this is the one table with no tenant_id."""

    __tablename__ = "model_arms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    arm_type: Mapped[ModelArmType] = mapped_column(
        pg_enum(ModelArmType, "model_arm_type"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    # Preprocessing is versioned separately from the weights: the same weights
    # with different preprocessing are a different model in practice.
    preprocessing_version: Mapped[str] = mapped_column(String(50), nullable=False)
    weight_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    model_arm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_arms.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ModelRunStatus] = mapped_column(
        pg_enum(ModelRunStatus, "model_run_status"), nullable=False,
        default=ModelRunStatus.PENDING,
    )
    # Why the arm produced nothing. An underwriter looking at a blank panel
    # needs this, so it is a column rather than only a log line.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubScore(Base):
    __tablename__ = "sub_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    model_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    raw_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    # Equal to raw_score today. There is no labelled test set to calibrate
    # against yet, and claiming a calibration that has not happened would be
    # worse than saying so plainly (PHASE1_PLAN.md).
    calibrated_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    # The 18 finding probabilities and each one's signed contribution — this is
    # what the review screen's "what moved the score" panel reads.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ExplanationArtifact(Base):
    __tablename__ = "explanation_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    model_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[ExplanationArtifactType] = mapped_column(
        pg_enum(ExplanationArtifactType, "explanation_artifact_type"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CompositeScore(Base):
    __tablename__ = "composite_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # Re-scoring an application adds a version rather than overwriting: the
    # decision made against the old number has to stay explainable.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    crs_value: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tier: Mapped[RiskTier] = mapped_column(pg_enum(RiskTier, "risk_tier"), nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False, default="expert_weights_v1")
    # Cut-points as they stood when this score was computed.
    tier_thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The declared-history rules that fired: key, points, and the reason text
    # shown to the underwriter.
    adjustments: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
