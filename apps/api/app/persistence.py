"""Write an `Evaluation` to the database.

`pipeline.evaluate()` knows nothing about Postgres on purpose — it takes bytes
and returns a result object, which is why the whole scoring path is testable
without a database. This module is the thin layer that turns that result into
rows, and it is the only place that knows about both.

Nothing here decides anything. If a number looks wrong, the bug is in
`scoring.py` or `arms/`, not here.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit as audit_chain
from app import storage
from app.arms import ARMS, Arm
from app.models import (
    Application,
    ApplicationStatus,
    AuditLog,
    CompositeScore,
    ExplanationArtifact,
    ExplanationArtifactType,
    ModelArm,
    ModelRun,
    ModelRunStatus,
    RiskTier,
    SubScore,
)
from app.pipeline import STATUS_SCORED, Evaluation

log = logging.getLogger(__name__)


async def register_arm(db: AsyncSession, arm: Arm) -> ModelArm:
    """The `model_arms` row for an arm, created on first use.

    The registry in `app/arms/` is the source of truth, so the row always
    describes the code that actually produced the score. Seeding it by hand
    would drift the moment a model is retrained.
    """
    existing = await db.execute(
        select(ModelArm).where(ModelArm.name == arm.name, ModelArm.version == arm.version)
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row

    row = ModelArm(
        name=arm.name,
        version=arm.version,
        arm_type=arm.arm_type,
        preprocessing_version=arm.preprocessing_version,
        weight_hash=arm.weight_hash,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    return row


async def save_evaluation(
    db: AsyncSession,
    application: Application,
    evaluation: Evaluation,
    started_at: datetime,
) -> None:
    """Persist every part of one evaluation and move the application on.

    Called inside the caller's transaction; the caller commits.
    """
    finished_at = datetime.now(UTC)
    tenant_id = application.tenant_id

    for run in evaluation.runs:
        arm = ARMS.get(run.arm_name)
        if arm is None:
            # An arm that ran but is no longer registered. Recording the score
            # with no provenance would be worse than dropping it.
            log.error("Arm %r produced a result but is not in the registry", run.arm_name)
            continue

        arm_row = await register_arm(db, arm)

        model_run = ModelRun(
            tenant_id=tenant_id,
            application_id=application.id,
            model_arm_id=arm_row.id,
            status=ModelRunStatus.FAILED if run.failed else ModelRunStatus.COMPLETED,
            error_message=run.result.error,
            started_at=started_at,
            completed_at=finished_at,
        )
        db.add(model_run)
        await db.flush()

        if run.failed:
            continue

        db.add(
            SubScore(
                tenant_id=tenant_id,
                model_run_id=model_run.id,
                # Both are the arm's 0-100 score. They differ once there is a
                # labelled test set to calibrate against; until then, saying so
                # is better than implying a calibration that never happened.
                raw_score=round(run.result.score, 2),
                calibrated_score=round(run.result.score, 2),
                details={
                    **run.result.details,
                    "probability": run.result.raw_score,
                    "evidence_hash": run.evidence_hash,
                },
            )
        )

        for name, data in run.result.artifacts.items():
            path = storage.write(
                tenant_id, application.id, f"{run.arm_name}-{name}-{model_run.id}.png", data
            )
            db.add(
                ExplanationArtifact(
                    tenant_id=tenant_id,
                    model_run_id=model_run.id,
                    artifact_type=_artifact_type(name),
                    storage_path=path,
                )
            )

    if evaluation.status == STATUS_SCORED and evaluation.crs is not None:
        db.add(
            CompositeScore(
                tenant_id=tenant_id,
                application_id=application.id,
                version=1,
                crs_value=evaluation.crs,
                tier=RiskTier(evaluation.tier),
                method="txrv_logreg_plus_declared_history_v1",
                tier_thresholds=evaluation.thresholds.as_dict(),
                adjustments=[
                    {"key": a.key, "points": a.points, "reason": a.reason}
                    for a in evaluation.adjustments
                ],
            )
        )
        application.status = ApplicationStatus.SCORED
    else:
        application.status = ApplicationStatus.INSUFFICIENT_EVIDENCE

    application.evaluated_at = finished_at


def _artifact_type(name: str) -> ExplanationArtifactType:
    try:
        return ExplanationArtifactType(name)
    except ValueError:
        # An arm produced an artifact kind the enum does not know. Grad-CAM is
        # the closest honest label for an image overlay.
        log.warning("Unknown explanation artifact %r; recording it as gradcam", name)
        return ExplanationArtifactType.GRADCAM


async def append_audit(
    db: AsyncSession,
    tenant_id: UUID,
    application_id: UUID,
    event_type: str,
    payload: dict,
    actor_user_id: UUID | None = None,
) -> AuditLog:
    """Add one entry to an application's audit chain.

    The chain is **per application**: each entry hashes the one before it for
    that application, so editing any historical row breaks every hash after it
    and `GET /api/applications/{id}/audit` can verify the whole thing on its
    own. A single global chain would detect slightly more (an entire
    application's entries being dropped) at the cost of serialising every write
    in the system — not a trade worth making here.
    """
    previous = await db.execute(
        select(AuditLog)
        .where(AuditLog.application_id == application_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    last = previous.scalar_one_or_none()

    prior = (
        audit_chain.Entry(
            event_type=last.event_type,
            payload=last.payload,
            prev_hash=last.prev_hash or audit_chain.GENESIS,
            payload_hash=last.payload_hash,
        )
        if last
        else None
    )

    entry = audit_chain.append(prior, event_type, payload)

    row = AuditLog(
        tenant_id=tenant_id,
        application_id=application_id,
        actor_user_id=actor_user_id,
        event_type=entry.event_type,
        payload=entry.payload,
        payload_hash=entry.payload_hash,
        prev_hash=entry.prev_hash,
    )
    db.add(row)
    return row
