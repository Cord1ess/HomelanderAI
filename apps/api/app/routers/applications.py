"""Applications: intake, queue, review, decision, audit.

The scoring itself lives in `pipeline.py` and knows nothing about HTTP. This
module stores what arrives, hands it to the pipeline, and stores what comes
back.

**Tenant scoping.** Every query here filters on `principal.tenant_id`. That
filter is the isolation — do not remove it on the assumption that row-level
security will catch it: the API currently connects as the database owner, which
bypasses RLS entirely (see docs/DATABASE.md).
"""

import asyncio
import json
import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit as audit_chain
from app import persistence, storage
from app.arms import arm_for_intake
from app.db.session import AsyncSessionLocal, get_db
from app.deps import Principal, current_principal
from app.intake import IntakeError, process_upload
from app.models import (
    Applicant,
    Application,
    ApplicationStatus,
    AuditLog,
    CompositeScore,
    EvidenceFile,
    EvidenceFileType,
    ExplanationArtifact,
    ModelRun,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    SubScore,
    UnderwriterDecision,
    User,
)
from app.pipeline import evaluate
from app.schemas.application import (
    AdjustmentSchema,
    ApplicantIn,
    ApplicationDetailSchema,
    AuditEntrySchema,
    AuditTrailSchema,
    CoverageIn,
    DecisionIn,
    DecisionSchema,
    FileSchema,
    FindingSchema,
    IntakeIn,
    ModelInfoSchema,
    QueueItemSchema,
    QueueSchema,
    ScoreSchema,
    SubmitResponseSchema,
)

router = APIRouter(tags=["Applications"])

log = logging.getLogger(__name__)

# The arm whose declared-history block feeds the scoring rules. The form nests
# history per model; `scoring.py` reads `symptoms` and `history` at the top
# level, so exactly one arm's block is unwrapped and passed through.
SCORING_ARM = "cxr_lung"

# Face photos are identity, not evidence, and no model reads them.
MAX_FACE_BYTES = 10 * 1024 * 1024


# ── intake ───────────────────────────────────────────────────────────────────


@router.post(
    "/applications",
    response_model=SubmitResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an application with its evidence",
)
async def submit_application(
    background: BackgroundTasks,
    payload: str = Form(..., description="JSON matching IntakeIn"),
    files: list[UploadFile] = File(default=[]),
    file_arms: list[str] = Form(default=[]),
    face_photo: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> SubmitResponseSchema:
    """Store the application and its evidence, then score it in the background.

    Scoring is not done inline: model inference takes seconds, and the operator
    has a client sitting opposite. They get a reference immediately, and the
    queue shows the result when it lands.
    """
    try:
        intake = IntakeIn.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The application details could not be read: {exc}",
        ) from exc

    if file_arms and len(file_arms) != len(files):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each uploaded file must say which model it belongs to.",
        )

    applicant = Applicant(
        tenant_id=principal.tenant_id,
        name=intake.applicant.name.strip(),
        phone=intake.applicant.phone.strip(),
        date_of_birth=intake.applicant.date_of_birth,
        sex=intake.applicant.sex,
    )
    db.add(applicant)
    # The reference comes from a BEFORE INSERT trigger, so it only exists after
    # the flush — never build one client-side.
    await db.flush()
    await db.refresh(applicant)

    application = Application(
        tenant_id=principal.tenant_id,
        applicant_id=applicant.id,
        status=ApplicationStatus.SUBMITTED,
        coverage_type=intake.coverage.coverage_type,
        coverage_amount=intake.coverage.coverage_amount,
        policy_term=intake.coverage.policy_term,
        models_requested=intake.models_requested,
        declared_history=intake.declared_history,
    )
    db.add(application)
    await db.flush()

    if face_photo is not None and face_photo.filename:
        raw = await face_photo.read()
        if len(raw) > MAX_FACE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The face photo is larger than 10 MB.",
            )
        if raw:
            applicant.face_photo_path = storage.write(
                principal.tenant_id, application.id, f"face-{applicant.id}.bin", raw
            )

    stored, rejected = await _store_evidence(db, principal, application, files, file_arms)

    if not stored:
        # Nothing scoreable arrived. Say so on the row rather than leaving it
        # queued forever behind a background task that has nothing to do.
        application.status = ApplicationStatus.INSUFFICIENT_EVIDENCE
        application.evaluated_at = datetime.now(UTC)

    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=await _actor_id(db, principal),
        event_type="application_submitted",
        payload={
            "reference": applicant.external_ref,
            "models_requested": intake.models_requested,
            "evidence_files": stored,
            "rejected_files": rejected,
        },
    )

    await db.commit()
    await db.refresh(application)

    if stored:
        background.add_task(score_application, application.id)

    return SubmitResponseSchema(
        id=application.id,
        reference=applicant.external_ref,
        status=application.status,
    )


async def _actor_id(db: AsyncSession, principal: Principal) -> UUID | None:
    """The user id to attribute an action to, or None for the system.

    `actor_user_id` is a real foreign key. The built-in admin's id is seeded
    (db/seed.sql) so it normally resolves to a row and the trail names a person
    — but that account exists precisely for when the database is not in its
    expected state, so an unresolvable id is recorded as the system rather than
    failing the whole request.
    """
    if await db.get(User, principal.user_id) is not None:
        return principal.user_id
    log.warning("No user row for %s; attributing to the system", principal.user_id)
    return None


async def _store_evidence(
    db: AsyncSession,
    principal: Principal,
    application: Application,
    files: list[UploadFile],
    file_arms: list[str],
) -> tuple[list[str], list[str]]:
    """De-identify each upload and save it. Returns (stored, rejected).

    De-identification happens here rather than in the background task so the
    original bytes are never written to disk at all — a DICOM header that is
    never stored cannot leak.
    """
    stored: list[str] = []
    rejected: list[str] = []

    for index, upload in enumerate(files):
        if not upload.filename:
            continue

        raw = await upload.read()
        try:
            processed = process_upload(raw, upload.filename)
        except IntakeError as exc:
            # One unreadable file must not cost the other evidence, or the
            # application. Record the reason and carry on.
            rejected.append(f"{upload.filename}: {exc}")
            continue

        path = storage.write(
            principal.tenant_id,
            application.id,
            f"{processed.content_hash}.png",
            processed.data,
        )

        # `file_arms[i]` is the form's panel id (e.g. "cxr_lung"), not the arm's
        # registry key. Matching it against ARMS directly always missed, which
        # left every evidence row with a null model_arm_id.
        intake_id = file_arms[index] if index < len(file_arms) else None
        arm = arm_for_intake(intake_id) if intake_id else None
        arm_row = await persistence.register_arm(db, arm) if arm else None

        db.add(
            EvidenceFile(
                tenant_id=principal.tenant_id,
                application_id=application.id,
                file_type=(
                    EvidenceFileType.DICOM
                    if processed.source_format == "dicom"
                    else EvidenceFileType.IMAGE
                ),
                storage_path=path,
                original_filename=upload.filename,
                mime_type=processed.mime_type,
                size_bytes=len(processed.data),
                content_hash=processed.content_hash,
                deidentified_at=datetime.now(UTC) if processed.deidentified else None,
                model_arm_id=arm_row.id if arm_row else None,
            )
        )
        stored.append(upload.filename)

    return stored, rejected


# ── background scoring ───────────────────────────────────────────────────────


async def score_application(application_id: UUID) -> None:
    """Run the pipeline over a stored application and record the result.

    Runs after the response has been sent, on its own session — the request's
    session is closed by then. Never raises: a failure here has to leave the row
    in a state the underwriter can act on, not die quietly in a worker.
    """
    async with AsyncSessionLocal() as db:
        try:
            application = await db.get(Application, application_id)
            if application is None:
                log.error("Application %s vanished before scoring", application_id)
                return

            application.status = ApplicationStatus.PROCESSING
            started_at = datetime.now(UTC)
            application.processing_started_at = started_at
            await db.commit()

            evidence = await db.execute(
                select(EvidenceFile).where(EvidenceFile.application_id == application_id)
            )
            payloads = [
                (storage.read(row.storage_path), row.original_filename or "evidence.png")
                for row in evidence.scalars().all()
            ]

            applicant = await db.get(Applicant, application.applicant_id)
            declared = (application.declared_history or {}).get(SCORING_ARM, {})

            # Inference is CPU-bound and takes seconds. Left on the event loop it
            # would block every other request for the duration, so it runs on a
            # worker thread.
            evaluation = await asyncio.to_thread(
                evaluate,
                payloads,
                declared,
                _age_from(applicant.date_of_birth if applicant else None),
            )

            await persistence.save_evaluation(db, application, evaluation, started_at)
            await persistence.append_audit(
                db,
                tenant_id=application.tenant_id,
                application_id=application.id,
                actor_user_id=None,  # the system scored it, not a person
                event_type="scoring_completed",
                payload={
                    "status": evaluation.status,
                    "crs": evaluation.crs,
                    "tier": evaluation.tier,
                    "adjustments": [a.key for a in evaluation.adjustments],
                    "errors": evaluation.errors,
                },
            )
            await _notify_tenant(
                db,
                application,
                NotificationType.PROCESSING_COMPLETE,
                _scoring_message(evaluation.status, evaluation.tier),
            )
            await db.commit()

        except Exception:
            log.exception("Scoring failed for application %s", application_id)
            await db.rollback()
            await _mark_failed(db, application_id)


async def _mark_failed(db: AsyncSession, application_id: UUID) -> None:
    """Leave a failed application in a state the underwriter can act on."""
    try:
        application = await db.get(Application, application_id)
        if application is None:
            return
        application.status = ApplicationStatus.INSUFFICIENT_EVIDENCE
        application.evaluated_at = datetime.now(UTC)
        await persistence.append_audit(
            db,
            tenant_id=application.tenant_id,
            application_id=application.id,
            event_type="scoring_failed",
            payload={"detail": "The scoring pipeline did not complete."},
        )
        await db.commit()
    except Exception:
        log.exception("Could not record the scoring failure for %s", application_id)
        await db.rollback()


def _scoring_message(status_value: str, tier: str) -> str:
    if status_value != "scored":
        return "Could not score this application — more evidence is needed"
    return f"Scoring complete — {tier.replace('_', ' ')} risk, ready for review"


def _age_from(born: date | None) -> int | None:
    if born is None:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


async def _notify_tenant(
    db: AsyncSession,
    application: Application,
    kind: NotificationType,
    message: str,
) -> None:
    """One in-app notification per active user in the tenant.

    Phase 1 has no per-user routing: everyone underwriting for this carrier
    should see that an application moved. `notification_preferences` is seeded
    but not read yet — when it is, this is the one place to filter.
    """
    users = await db.execute(
        select(User).where(User.tenant_id == application.tenant_id, User.is_active.is_(True))
    )
    for user in users.scalars().all():
        db.add(
            Notification(
                tenant_id=application.tenant_id,
                user_id=user.id,
                application_id=application.id,
                notification_type=kind,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=message,
            )
        )


# ── queue ────────────────────────────────────────────────────────────────────


@router.get("/applications", response_model=QueueSchema, summary="The review queue")
async def list_applications(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, description="Match a reference or applicant name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> QueueSchema:
    """Newest first, scoped to the signed-in user's carrier."""
    # The latest composite score per application. A left join, because an
    # application that has not been scored yet still belongs in the queue.
    latest = (
        select(
            CompositeScore.application_id,
            func.max(CompositeScore.version).label("version"),
        )
        .where(CompositeScore.tenant_id == principal.tenant_id)
        .group_by(CompositeScore.application_id)
        .subquery()
    )

    base = (
        select(Application, Applicant, CompositeScore)
        .join(Applicant, Applicant.id == Application.applicant_id)
        .outerjoin(
            latest,
            latest.c.application_id == Application.id,
        )
        .outerjoin(
            CompositeScore,
            (CompositeScore.application_id == latest.c.application_id)
            & (CompositeScore.version == latest.c.version),
        )
        .where(Application.tenant_id == principal.tenant_id)
    )

    if status_filter and status_filter != "all":
        base = base.where(Application.status == status_filter)

    if q:
        pattern = f"%{q.strip()}%"
        base = base.where(
            Applicant.external_ref.ilike(pattern) | Applicant.name.ilike(pattern)
        )

    rows = await db.execute(
        base.order_by(Application.submitted_at.desc()).limit(limit).offset(offset)
    )

    items = [
        QueueItemSchema(
            id=application.id,
            reference=applicant.external_ref,
            applicant_name=applicant.name,
            submitted_at=application.submitted_at,
            status=application.status,
            crs=float(score.crs_value) if score else None,
            tier=score.tier.value if score else None,
        )
        for application, applicant, score in rows.all()
    ]

    counts_result = await db.execute(
        select(Application.status, func.count())
        .where(Application.tenant_id == principal.tenant_id)
        .group_by(Application.status)
    )
    counts = {row_status.value: count for row_status, count in counts_result.all()}

    return QueueSchema(items=items, total=sum(counts.values()), counts=counts)


# ── detail ───────────────────────────────────────────────────────────────────


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetailSchema,
    summary="Everything the review screen needs, in one call",
)
async def get_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ApplicationDetailSchema:
    application, applicant = await _load_owned(db, application_id, principal)

    score_row = (
        await db.execute(
            select(CompositeScore)
            .where(CompositeScore.application_id == application.id)
            .order_by(CompositeScore.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    runs = (
        await db.execute(
            select(ModelRun, SubScore)
            .outerjoin(SubScore, SubScore.model_run_id == ModelRun.id)
            .where(ModelRun.application_id == application.id)
            .order_by(ModelRun.started_at)
        )
    ).all()

    findings: list[FindingSchema] = []
    model_info: ModelInfoSchema | None = None
    errors: list[str] = []
    vision_score: float | None = None

    for run, sub in runs:
        if run.error_message:
            errors.append(run.error_message)
        if sub is None:
            continue

        details = sub.details or {}
        probabilities = details.get("findings") or {}
        contributions = details.get("contributions") or {}
        # Every label the arm reported, whichever half of the pair it came from.
        for label in sorted(set(probabilities) | set(contributions)):
            findings.append(
                FindingSchema(
                    label=label,
                    probability=float(probabilities.get(label, 0.0)),
                    contribution=float(contributions.get(label, 0.0)),
                )
            )
        vision_score = float(sub.calibrated_score)
        model_info = ModelInfoSchema(
            scorer=details.get("scorer"),
            backbone=details.get("backbone"),
            validation=details.get("validation"),
            cv_auc=details.get("cv_auc"),
        )

    files = await _list_files(db, application)

    decision_row = (
        await db.execute(
            select(UnderwriterDecision, User)
            .outerjoin(User, User.id == UnderwriterDecision.underwriter_id)
            .where(UnderwriterDecision.application_id == application.id)
        )
    ).first()

    decision = None
    if decision_row is not None:
        record, underwriter = decision_row
        decision = DecisionSchema(
            decision=record.decision,
            final_premium=record.final_premium,
            decided_at=record.decided_at,
            underwriter_name=underwriter.full_name if underwriter else None,
        )

    return ApplicationDetailSchema(
        id=application.id,
        reference=applicant.external_ref,
        status=application.status,
        submitted_at=application.submitted_at,
        evaluated_at=application.evaluated_at,
        applicant=ApplicantIn(
            name=applicant.name or "",
            phone=applicant.phone or "",
            date_of_birth=applicant.date_of_birth,
            sex=applicant.sex,
        ),
        coverage=CoverageIn(
            coverage_type=application.coverage_type,
            coverage_amount=application.coverage_amount,
            policy_term=application.policy_term,
        ),
        models_requested=application.models_requested or [],
        declared_history=application.declared_history or {},
        score=(
            ScoreSchema(
                crs=float(score_row.crs_value),
                tier=score_row.tier.value,
                method=score_row.method,
                thresholds=score_row.tier_thresholds or {},
                vision_score=vision_score,
                computed_at=score_row.computed_at,
            )
            if score_row
            else None
        ),
        adjustments=[
            AdjustmentSchema(
                key=a.get("key", ""),
                points=float(a.get("points", 0)),
                reason=a.get("reason", ""),
            )
            for a in (score_row.adjustments or [])
        ]
        if score_row
        else [],
        findings=findings,
        model_info=model_info,
        files=files,
        decision=decision,
        errors=errors,
    )


async def _list_files(db: AsyncSession, application: Application) -> list[FileSchema]:
    """Evidence images and any heatmaps produced for them."""
    evidence = (
        await db.execute(
            select(EvidenceFile).where(EvidenceFile.application_id == application.id)
        )
    ).scalars().all()

    artifacts = (
        await db.execute(
            select(ExplanationArtifact)
            .join(ModelRun, ModelRun.id == ExplanationArtifact.model_run_id)
            .where(ModelRun.application_id == application.id)
        )
    ).scalars().all()

    return [
        FileSchema(
            id=row.id,
            kind="evidence",
            filename=row.original_filename,
            mime_type=row.mime_type,
        )
        for row in evidence
    ] + [
        FileSchema(
            id=row.id,
            kind=row.artifact_type.value,
            filename=None,
            mime_type="image/png",
        )
        for row in artifacts
    ]


async def _load_owned(
    db: AsyncSession, application_id: UUID, principal: Principal
) -> tuple[Application, Applicant]:
    """Fetch an application, or 404 if it is not this carrier's.

    404 rather than 403 on a tenant mismatch: telling one carrier that another
    carrier's application id exists is itself a leak.
    """
    row = (
        await db.execute(
            select(Application, Applicant)
            .join(Applicant, Applicant.id == Application.applicant_id)
            .where(
                Application.id == application_id,
                Application.tenant_id == principal.tenant_id,
            )
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No such application.",
        )
    return row


# ── decision ─────────────────────────────────────────────────────────────────


@router.post(
    "/applications/{application_id}/decision",
    response_model=DecisionSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Record the underwriter's decision (write-once)",
)
async def record_decision(
    application_id: UUID,
    payload: DecisionIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> DecisionSchema:
    """One decision per application, enforced by the database.

    The built-in admin cannot decide: `underwriter_id` is a real foreign key,
    and a decision has to be attributable to a person who can be held to it.
    """
    application, _ = await _load_owned(db, application_id, principal)

    if payload.decision.value == "approved_with_adjustment" and not payload.final_premium:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="An adjusted approval needs a final premium.",
        )

    underwriter = await db.get(User, principal.user_id)
    if underwriter is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This account has no user record, so a decision could not be "
                "attributed to it. Sign in with a real account to decide."
            ),
        )

    record = UnderwriterDecision(
        tenant_id=principal.tenant_id,
        application_id=application.id,
        underwriter_id=underwriter.id,
        decision=payload.decision,
        final_premium=payload.final_premium,
    )
    db.add(record)
    application.status = ApplicationStatus.DECIDED

    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=underwriter.id,
        event_type="decision_recorded",
        payload={
            "decision": payload.decision.value,
            "final_premium": float(payload.final_premium) if payload.final_premium else None,
        },
    )
    await _notify_tenant(
        db,
        application,
        NotificationType.DECISION_RECORDED,
        f"Decision recorded: {payload.decision.value.replace('_', ' ')}",
    )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application has already been decided. Decisions cannot be changed.",
        ) from exc

    await db.refresh(record)
    return DecisionSchema(
        decision=record.decision,
        final_premium=record.final_premium,
        decided_at=record.decided_at,
        underwriter_name=underwriter.full_name,
    )


# ── audit ────────────────────────────────────────────────────────────────────


@router.get(
    "/applications/{application_id}/audit",
    response_model=AuditTrailSchema,
    summary="The audit trail, with its hash chain verified",
)
async def get_audit_trail(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> AuditTrailSchema:
    """Verification runs on every read rather than on a schedule — an audit
    trail nobody checks is decoration."""
    await _load_owned(db, application_id, principal)

    rows = (
        await db.execute(
            select(AuditLog, User)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .where(AuditLog.application_id == application_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        )
    ).all()

    ok, reason = audit_chain.verify(
        [
            audit_chain.Entry(
                event_type=row.event_type,
                payload=row.payload,
                prev_hash=row.prev_hash or audit_chain.GENESIS,
                payload_hash=row.payload_hash,
            )
            for row, _ in rows
        ]
    )

    return AuditTrailSchema(
        entries=[
            AuditEntrySchema(
                id=row.id,
                event_type=row.event_type,
                payload=row.payload or {},
                actor_name=actor.full_name if actor else None,
                created_at=row.created_at,
            )
            for row, actor in rows
        ],
        intact=ok,
        broken_at=reason,
    )


# ── files ────────────────────────────────────────────────────────────────────


@router.get("/files/{file_id}", summary="Serve one stored image")
async def get_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> FileResponse:
    """Evidence images and heatmaps, by id.

    Files are served through the API rather than from a static folder so that
    every read is checked against the caller's tenant. Health data on a public
    URL would be a breach whatever the filename.
    """
    evidence = (
        await db.execute(
            select(EvidenceFile).where(
                EvidenceFile.id == file_id,
                EvidenceFile.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()

    path = evidence.storage_path if evidence else None

    if path is None:
        artifact = (
            await db.execute(
                select(ExplanationArtifact).where(
                    ExplanationArtifact.id == file_id,
                    ExplanationArtifact.tenant_id == principal.tenant_id,
                )
            )
        ).scalar_one_or_none()
        path = artifact.storage_path if artifact else None

    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such file.")

    try:
        absolute = storage.resolve(path)
    except ValueError as exc:
        log.error("Refused to serve %s: %s", path, exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such file."
        ) from exc

    if not absolute.exists():
        # The row survived but the file did not — say which, rather than
        # returning a broken image.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The record exists but its file is missing from storage.",
        )

    return FileResponse(absolute, media_type="image/png")
