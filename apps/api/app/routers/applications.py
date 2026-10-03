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
from decimal import Decimal, InvalidOperation
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
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit as audit_chain
from app import (
    catalogue,
    mailer,
    outbox,
    persistence,
    plans,
    pricing,
    progress,
    storage,
    triage,
    turnaround,
)
from app import decline as decline_rules
from app import ecg as ecg_signal
from app import evidence as evidence_kinds
from app import policies as pricing_dates
from app.arms import arm_for_intake, arms_for, form_arms
from app.core.security import generate_password, generate_portal_id, hash_password
from app.db.session import AsyncSessionLocal, get_db
from app.deps import Principal, current_principal
from app.evidence import EvidenceKind
from app.intake import IntakeError, dicom_to_png, is_dicom, process_upload
from app.models import (
    Applicant,
    Application,
    ApplicationStatus,
    AuditLog,
    ClientMessage,
    CompositeScore,
    DoctorReview,
    EvidenceFile,
    EvidenceFileType,
    ExplanationArtifact,
    InsurancePolicy,
    ModelArm,
    ModelArmType,
    ModelRun,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RequestedDocument,
    RiskTier,
    SubScore,
    Tenant,
    UnderwriterDecision,
    UnderwriterDecisionType,
    User,
    UserRole,
)
from app.pipeline import evaluate
from app.schemas.application import (
    AdjustmentSchema,
    ApplicantIn,
    ApplicationDetailSchema,
    ArmRunSchema,
    AuditEntrySchema,
    AuditTrailSchema,
    ClassifiedFileSchema,
    ClassifyResponseSchema,
    ClientMessageIn,
    ClientMessageSchema,
    CoverageIn,
    DecisionIn,
    DecisionSchema,
    DoctorReviewIn,
    DoctorReviewSchema,
    EscalateIn,
    EvidenceChoiceSchema,
    FileSchema,
    FindingSchema,
    IntakeIn,
    ModelInfoSchema,
    ModelSchema,
    PlanSchema,
    PortalCredentialsSchema,
    QueueItemSchema,
    QueueSchema,
    QuoteIn,
    QuoteSchema,
    RequestedDocumentSchema,
    RequestEvidenceIn,
    ScoreSchema,
    SubmitResponseSchema,
    TurnaroundIn,
)
from app.scoring import Thresholds

router = APIRouter(tags=["Applications"])

log = logging.getLogger(__name__)

# The arm whose declared-history block feeds the scoring rules. The form nests
# history per model; `scoring.py` reads `symptoms` and `history` at the top
# level, so exactly one arm's block is unwrapped and passed through.
SCORING_ARM = "cxr_lung"

# Face photos are identity, not evidence, and no model reads them.
MAX_FACE_BYTES = 10 * 1024 * 1024


def _thresholds_for(tenant: Tenant | None) -> Thresholds:
    """The company's tier boundaries, or the defaults with no company row."""
    if tenant is None:
        return Thresholds()
    return Thresholds(
        low_max=float(tenant.tier_low_max), moderate_max=float(tenant.tier_moderate_max)
    )


@router.post(
    "/evidence/classify",
    response_model=ClassifyResponseSchema,
    summary="Work out what each uploaded file is, before anything is scored",
)
async def classify_evidence(
    files: list[UploadFile] = File(default=[]),
    principal: Principal = Depends(current_principal),
) -> ClassifyResponseSchema:
    """Identify dropped files so the operator can confirm where each one goes.

    Stores nothing and creates no application: this runs while the operator is
    still filling in the form, so the review screen is instant when they submit.
    The kinds it proposes are only acted on after the operator confirms them.
    """
    _not_for_doctors(principal, "identifying evidence for a new application")
    classified: list[ClassifiedFileSchema] = []

    for upload in files:
        if not upload.filename:
            continue
        raw = await upload.read()

        # De-identify first. Classification reads pixels, and the original
        # bytes carry the DICOM header we make a point of never storing.
        tags: dict = {}
        thumbnail = None
        try:
            processed = process_upload(raw, upload.filename)
            tags = processed.clinical_tags
            thumbnail = _thumbnail(processed.data)
            pixels = processed.data
        except IntakeError:
            # Unreadable as an image. Still classified, because a PDF is
            # recognised by its name and is a perfectly good document.
            pixels = raw

        verdict = triage.classify(pixels, upload.filename, tags)
        readers = arms_for(verdict.kind)

        classified.append(
            ClassifiedFileSchema(
                filename=upload.filename,
                kind=verdict.kind.value,
                kind_label=evidence_kinds.label(verdict.kind),
                reason=verdict.reason,
                # The catalogue id (the form's model id), not the arm's internal name,
                # so the screen can switch the right reader on.
                arms=[a.intake_id for a in readers],
                needs_choice=not verdict.certain,
                thumbnail=thumbnail,
            )
        )

    return ClassifyResponseSchema(
        files=classified,
        choices=[
            EvidenceChoiceSchema(
                kind=kind.value,
                label=evidence_kinds.label(kind),
                arms=[a.intake_id for a in arms_for(kind)],
            )
            for kind in EvidenceKind
            if kind is not EvidenceKind.UNKNOWN
        ],
    )


def _thumbnail(png_bytes: bytes, size: int = 96) -> str | None:
    """A small data URI, so the operator confirms a document and not a filename.

    Inline rather than a stored file with a URL: these are previews of evidence
    that has not been submitted yet, so there is nothing to serve them from and
    nothing to clean up if the operator abandons the form.
    """
    from base64 import b64encode
    from io import BytesIO

    from PIL import Image

    try:
        # A stored mammogram is a DICOM; a stored ECG is a signal. Draw
        # either first, then shrink the drawing.
        if is_dicom(png_bytes):
            png_bytes = dicom_to_png(png_bytes)
        if ecg_signal.is_canonical(png_bytes):
            png_bytes = ecg_signal.render(
                ecg_signal.from_bytes(png_bytes), width=480, row_height=24
            )
        image = Image.open(BytesIO(png_bytes))
        image.load()
        image.thumbnail((size, size))
        buffer = BytesIO()
        image.convert("L" if image.mode in ("L", "1") else "RGB").save(
            buffer, format="JPEG", quality=70
        )
        return "data:image/jpeg;base64," + b64encode(buffer.getvalue()).decode()
    except Exception:
        # A missing preview is a worse review screen, not a failed upload.
        return None


@router.get(
    "/models",
    response_model=list[ModelSchema],
    summary="Which models the intake form may offer, and which actually run",
)
async def list_models(
    _: Principal = Depends(current_principal),
) -> list[ModelSchema]:
    """The form used to offer seven models as though all seven worked. One does.

    `available` comes from the arm registry rather than a hand-kept list, so the
    menu cannot claim a model that would silently produce nothing.
    """
    return [ModelSchema.model_validate(entry) for entry in catalogue.as_dicts()]


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
    # What the operator confirmed each file is, on the review screen. Parallel
    # to `files`. Takes precedence over `file_arms`, which only says which form
    # panel it was attached to.
    file_kinds: list[str] = Form(default=[]),
    face_photo: UploadFile | None = File(default=None),
    # The front of the client's national ID card. Identity, like the face
    # photo: stored, never read by a model.
    nid_image: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> SubmitResponseSchema:
    """Store the application and its evidence, then score it in the background.

    Scoring is not done inline: model inference takes seconds, and the operator
    has a client sitting opposite. They get a reference immediately, and the
    queue shows the result when it lands.
    """
    _not_for_doctors(principal, "taking an application")

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

    email = (intake.applicant.email or "").strip().lower() or None
    if email and "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That email address does not look right.",
        )

    # Health data is sensitive personal data: nothing is taken without the
    # client's agreement, recorded with the time it was given.
    if not intake.applicant.consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The client has to agree to their health data being used before an "
            "application can be taken.",
        )
    product = pricing.product_for(intake.coverage.coverage_type)
    if product == "life" and not (intake.applicant.nominee_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Life cover needs a nominee: the person paid if the client dies.",
        )
    # The products' age limits are not checked here: an application outside
    # them can still be taken (the intake screen warns first), and it cannot be
    # approved — the underwriter declines it as outside the limits.
    nid_number = "".join(ch for ch in (intake.applicant.nid_number or "") if ch.isdigit()) or None
    if nid_number and len(nid_number) not in (10, 13, 17):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="An NID number has 10, 13 or 17 digits.",
        )
    if nid_number:
        already = (
            await db.execute(
                select(Applicant.external_ref).where(
                    Applicant.tenant_id == principal.tenant_id,
                    Applicant.nid_number == nid_number,
                )
            )
        ).scalar_one_or_none()
        if already:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A client with this NID already exists ({already}). Open their profile "
                "instead of taking them again.",
            )

    # The applicant's portal sign-in. The password exists in this request only:
    # its hash is stored, and it is emailed or handed to the operator below.
    portal_password = generate_password()

    applicant = Applicant(
        tenant_id=principal.tenant_id,
        name=intake.applicant.name.strip(),
        phone=intake.applicant.phone.strip(),
        date_of_birth=intake.applicant.date_of_birth,
        sex=intake.applicant.sex,
        email=email,
        portal_id=generate_portal_id(),
        password_hash=hash_password(portal_password),
        nid_number=nid_number,
        nid_name=(intake.applicant.nid_name or "").strip() or None,
        nid_date_of_birth=intake.applicant.nid_date_of_birth,
        nominee_name=(intake.applicant.nominee_name or "").strip() or None,
        nominee_relation=(intake.applicant.nominee_relation or "").strip() or None,
        nominee_phone=(intake.applicant.nominee_phone or "").strip() or None,
        consent_at=datetime.now(UTC),
    )
    db.add(applicant)
    # The reference comes from a BEFORE INSERT trigger, so it only exists after
    # the flush — never build one client-side.
    await db.flush()
    await db.refresh(applicant)

    # The date the applicant is told to expect an answer, from this carrier's
    # default. Fixed here rather than computed on read, so changing the default
    # later does not silently move a promise that has already been made.
    tenant = await db.get(Tenant, principal.tenant_id)
    business_days = (
        tenant.turnaround_business_days if tenant else turnaround.DEFAULT_BUSINESS_DAYS
    )

    application = Application(
        tenant_id=principal.tenant_id,
        applicant_id=applicant.id,
        status=ApplicationStatus.SUBMITTED,
        coverage_type=intake.coverage.coverage_type,
        coverage_amount=intake.coverage.coverage_amount,
        policy_term=intake.coverage.policy_term if product == "life" else "1",
        payment_mode=intake.coverage.payment_mode,
        models_requested=intake.models_requested,
        declared_history=intake.declared_history,
        # Local date, not UTC. Working days are calendar days where the
        # operator and applicant are; at 2 a.m. in Dhaka the UTC date is still
        # yesterday, which would promise a day earlier than intended.
        expected_by=turnaround.add_business_days(date.today(), business_days),
    )
    db.add(application)
    await db.flush()

    # Optional. It is the most sensitive thing the form can collect — biometric,
    # and no model reads it — so it is never required and never shown beside a
    # risk score, where a face could only bias the decision (SPEC §10).
    if face_photo is not None and face_photo.filename:
        raw = await face_photo.read()
        if len(raw) > MAX_FACE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The face photo is larger than 10 MB.",
            )
        if raw:
            try:
                # Re-encoded rather than stored as uploaded: that is what
                # actually strips EXIF, which on a phone photo carries the
                # device and often the GPS coordinates it was taken at.
                photo = process_upload(raw, face_photo.filename)
            except IntakeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"The identity photo could not be read: {exc}",
                ) from exc

            applicant.face_photo_path = storage.write(
                principal.tenant_id, application.id, f"face-{applicant.id}.png", photo.data
            )

    if nid_image is not None and nid_image.filename:
        raw = await nid_image.read()
        if len(raw) > MAX_FACE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The NID card image is larger than 10 MB.",
            )
        if raw:
            try:
                card = process_upload(raw, nid_image.filename)
            except IntakeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"The NID card image could not be read: {exc}",
                ) from exc
            applicant.nid_image_path = storage.write(
                principal.tenant_id, application.id, f"nid-{applicant.id}.png", card.data
            )

    _apply_measurements(applicant, intake.declared_history)

    stored, rejected = await _store_evidence(
        db, principal, application, files, file_arms, file_kinds
    )

    # An arm that reads the form has something to do even with no file: the
    # operator's answers are its evidence.
    scoreable = bool(stored) or any(
        arm.intake_id in intake.models_requested for arm in form_arms()
    )
    if not scoreable:
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

    if scoreable:
        background.add_task(score_application, application.id)

    # Emailed when there is an address and a mail server; otherwise handed to
    # the operator here, once, because the client is sitting in front of them.
    # Sending runs on a worker thread so a slow mail server cannot stall the
    # event loop, and a failure to send is never a failure to submit.
    emailed = False
    if applicant.email:
        emailed = await asyncio.to_thread(
            mailer.send_credentials,
            applicant.email,
            applicant.name or "",
            applicant.external_ref,
            applicant.portal_id,
            portal_password,
        )
        outbox.record(
            db,
            principal.tenant_id,
            application.id,
            "portal_sign_in",
            applicant.email,
            f"Your application {applicant.external_ref}",
            emailed,
        )
        await db.commit()

    return SubmitResponseSchema(
        id=application.id,
        reference=applicant.external_ref,
        status=application.status,
        portal=PortalCredentialsSchema(
            portal_id=applicant.portal_id,
            password=None if emailed else portal_password,
            emailed=emailed,
            email=applicant.email,
        ),
    )


def _apply_measurements(applicant: Applicant, declared: dict) -> None:
    """Copy height and weight onto the applicant.

    The form collects them inside the tabular model's panel, so they arrive
    nested in `declared_history`. `applicants` has columns for both and they
    were being left null — the data was in the database but not where anything
    would look for it, and BMI is a demographic fact about the person, not an
    answer to one model's questionnaire.
    """
    measurements = (declared or {}).get("xgboost") or {}
    for field in ("height_cm", "weight_kg"):
        value = measurements.get(field)
        if value is None:
            continue
        try:
            setattr(applicant, field, Decimal(str(value)))
        except (InvalidOperation, ValueError):
            log.warning("Ignoring unreadable %s: %r", field, value)


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
    file_kinds: list[str] | None = None,
    created: list[EvidenceFile] | None = None,
) -> tuple[list[str], list[str]]:
    """De-identify each upload and save it. Returns (stored, rejected). The
    rows themselves are appended to `created` when the caller passes a list.

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

        # Each stored form keeps its own extension: what is on disk is what
        # the arm read — a PNG, an ECG signal, or a note's text.
        extension = {"ecg": "npy", "document": "txt", "mammogram": "dcm"}.get(
            processed.source_format, "png"
        )
        path = storage.write(
            principal.tenant_id,
            application.id,
            f"{processed.content_hash}.{extension}",
            processed.data,
        )

        # `file_arms[i]` is the form's panel id (e.g. "cxr_lung"), not the arm's
        # registry key. Matching it against ARMS directly always missed, which
        # left every evidence row with a null model_arm_id.
        intake_id = file_arms[index] if index < len(file_arms) else None
        arm = arm_for_intake(intake_id) if intake_id else None
        arm_row = await persistence.register_arm(db, arm) if arm else None

        # What the operator confirmed this is. Falls back to what the arm
        # accepts, so a caller that predates the review screen still works.
        kind: str | None = None
        if file_kinds and index < len(file_kinds):
            try:
                kind = EvidenceKind(file_kinds[index]).value
            except ValueError:
                log.warning("Ignoring unknown evidence kind %r", file_kinds[index])
        if kind is None and arm is not None:
            accepted = next(iter(arm.accepts), None)
            kind = accepted.value if accepted else None
        # UNKNOWN is stored as nothing: no model should read a file whose kind
        # was never established.
        if kind == EvidenceKind.UNKNOWN.value:
            kind = None

        row = EvidenceFile(
                tenant_id=principal.tenant_id,
                application_id=application.id,
                file_type={
                    "dicom": EvidenceFileType.DICOM,
                    "mammogram": EvidenceFileType.DICOM,
                    "ecg": EvidenceFileType.ECG,
                    "document": EvidenceFileType.CLINICAL_NOTE,
                }.get(processed.source_format, EvidenceFileType.IMAGE),
                storage_path=path,
                original_filename=upload.filename,
                mime_type=processed.mime_type,
                size_bytes=len(processed.data),
                content_hash=processed.content_hash,
                deidentified_at=datetime.now(UTC) if processed.deidentified else None,
                evidence_kind=kind,
                model_arm_id=arm_row.id if arm_row else None,
            )
        db.add(row)
        if created is not None:
            created.append(row)
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
            progress.start(application_id)
            started_at = datetime.now(UTC)
            application.processing_started_at = started_at
            await db.commit()

            evidence = await db.execute(
                select(EvidenceFile).where(EvidenceFile.application_id == application_id)
            )
            rows = evidence.scalars().all()
            payloads = [
                (storage.read(row.storage_path), row.original_filename or "evidence.png")
                for row in rows
            ]

            # What each file is, as confirmed by the operator at intake. A file
            # with no kind is deliberately absent from this map: the pipeline
            # stores it and records that nothing read it, rather than handing it
            # to a model that will answer regardless.
            kinds: dict[str, EvidenceKind] = {}
            for row in rows:
                if not row.evidence_kind or not row.content_hash:
                    continue
                try:
                    kinds[row.content_hash] = EvidenceKind(row.evidence_kind)
                except ValueError:
                    log.warning(
                        "Evidence %s has an unrecognised kind %r; not scoring it",
                        row.id,
                        row.evidence_kind,
                    )

            applicant = await db.get(Applicant, application.applicant_id)
            # The company's tier boundaries. Snapshotted onto the score by
            # save_evaluation, so a later change cannot re-tier this one.
            thresholds = _thresholds_for(await db.get(Tenant, application.tenant_id))
            raw_declared = application.declared_history or {}
            declared = dict(raw_declared.get(SCORING_ARM, {}))
            for k, v in raw_declared.items():
                if isinstance(v, dict):
                    declared.update(v)
                else:
                    declared[k] = v

            # Inference is CPU-bound and takes seconds. Left on the event loop it
            # would block every other request for the duration, so it runs on a
            # worker thread.
            evaluation = await asyncio.to_thread(
                evaluate,
                payloads,
                declared,
                _age_from(applicant.date_of_birth if applicant else None),
                thresholds,
                kinds,
                applicant.sex if applicant else None,
                list(application.models_requested or []),
                lambda done, total, step: progress.update(application_id, done, total, step),
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
        finally:
            progress.finish(application_id)


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

    Everyone underwriting for this carrier should see that an application
    moved. A doctor hears only about the applications sent to a doctor: they
    see nothing else, so a notice about anything else would lead nowhere.
    """
    users = await db.execute(
        select(User).where(User.tenant_id == application.tenant_id, User.is_active.is_(True))
    )
    for user in users.scalars().all():
        if user.role == UserRole.MEDICAL_PROFESSIONAL and application.sent_to_doctor_at is None:
            continue
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
    mine: bool = Query(default=False, description="Only the cases I have taken"),
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
    if _is_doctor(principal):
        base = base.where(Application.sent_to_doctor_at.is_not(None))

    if status_filter and status_filter != "all":
        base = base.where(Application.status == status_filter)
    if mine:
        base = base.where(Application.assigned_to == principal.user_id)

    if q:
        pattern = f"%{q.strip()}%"
        base = base.where(
            Applicant.external_ref.ilike(pattern) | Applicant.name.ilike(pattern)
        )

    rows = await db.execute(
        base.order_by(Application.submitted_at.desc()).limit(limit).offset(offset)
    )

    listed = rows.all()
    verdicts = await _latest_verdicts(db, [a.id for a, _, _ in listed])
    issued = {
        application_id: (number, state)
        for application_id, number, state in (
            await db.execute(
                select(
                    InsurancePolicy.application_id,
                    InsurancePolicy.policy_number,
                    InsurancePolicy.status,
                ).where(InsurancePolicy.application_id.in_([a.id for a, _, _ in listed]))
            )
        ).all()
    } if listed else {}
    ids = [a.id for a, _, _ in listed]
    declined = set(
        (
            await db.execute(
                select(UnderwriterDecision.application_id).where(
                    UnderwriterDecision.application_id.in_(ids),
                    UnderwriterDecision.decision == UnderwriterDecisionType.DECLINED,
                )
            )
        ).scalars().all()
    ) if ids else set()
    holder_ids = {a.assigned_to for a, _, _ in listed if a.assigned_to}
    holders = {
        u.id: u.full_name
        for u in (await db.execute(select(User).where(User.id.in_(holder_ids)))).scalars()
    } if holder_ids else {}
    items = []
    for application, applicant, score in listed:
        running = progress.get(application.id)
        holder = holders.get(application.assigned_to) if application.assigned_to else None
        items.append(QueueItemSchema(
            id=application.id,
            reference=applicant.external_ref,
            applicant_name=applicant.name,
            submitted_at=application.submitted_at,
            status=application.status,
            crs=float(score.crs_value) if score else None,
            tier=score.tier.value if score else None,
            coverage_amount=application.coverage_amount,
            models_requested=application.models_requested or [],
            expected_by=application.expected_by,
            overdue=turnaround.is_overdue(application.expected_by, application.status.value),
            doctor_verdict=verdicts.get(application.id),
            progress_done=running.done if running else None,
            progress_total=running.total if running else None,
            progress_step=running.step if running else None,
            policy_number=issued.get(application.id, (None, None))[0],
            policy_status=issued.get(application.id, (None, None))[1],
            declined=application.id in declined,
            assigned_to_id=application.assigned_to,
            assigned_to_name=holder,
        ))

    counted = select(Application.status, func.count()).where(
        Application.tenant_id == principal.tenant_id
    )
    if _is_doctor(principal):
        counted = counted.where(Application.sent_to_doctor_at.is_not(None))
    counts_result = await db.execute(counted.group_by(Application.status))
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
    tenant = await db.get(Tenant, principal.tenant_id)
    rates = pricing.Rates.from_tenant(tenant) if tenant else pricing.DEFAULT_RATES
    product = pricing.product_for(application.coverage_type)
    age = pricing.age_on(applicant.date_of_birth, date.today())
    smoker = pricing.is_smoker(application.declared_history)

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
            select(ModelRun, SubScore, ModelArm)
            .outerjoin(SubScore, SubScore.model_run_id == ModelRun.id)
            .join(ModelArm, ModelArm.id == ModelRun.model_arm_id)
            .where(ModelRun.application_id == application.id)
            .order_by(ModelRun.started_at)
        )
    ).all()

    findings: list[FindingSchema] = []
    model_info: ModelInfoSchema | None = None
    errors: list[str] = []
    vision_score: float | None = None
    arms: list[ArmRunSchema] = []

    for run, sub, arm_row in runs:
        if run.error_message:
            errors.append(run.error_message)
        arms.append(
            ArmRunSchema(
                arm=arm_row.name,
                arm_type=arm_row.arm_type.value,
                version=arm_row.version,
                score=float(sub.calibrated_score) if sub is not None else None,
                details=(sub.details or {}) if sub is not None else {},
                error=run.error_message,
            )
        )
        # The image panel reads one vision arm: the one with the governing
        # score, since the highest reading is what the tier was set from.
        if sub is None or arm_row.arm_type is not ModelArmType.VISION:
            continue
        if vision_score is not None and float(sub.calibrated_score) <= vision_score:
            continue

        details = sub.details or {}
        probabilities = details.get("findings") or {}
        contributions = details.get("contributions") or {}
        # Every label the arm reported, whichever half of the pair it came from.
        findings = [
            FindingSchema(
                label=label,
                probability=float(probabilities.get(label, 0.0)),
                contribution=float(contributions.get(label, 0.0)),
            )
            for label in sorted(set(probabilities) | set(contributions))
        ]
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

    requested_rows = (
        await db.execute(
            select(RequestedDocument, User)
            .outerjoin(User, User.id == RequestedDocument.requested_by)
            .where(RequestedDocument.application_id == application.id)
            .order_by(RequestedDocument.requested_at)
        )
    ).all()
    requested = [
        RequestedDocumentSchema(
            id=row.id,
            description=row.description,
            requested_at=row.requested_at,
            requested_by_name=who.full_name if who else None,
            fulfilled_at=row.fulfilled_at,
            fulfilled_by_file_id=row.fulfilled_by,
        )
        for row, who in requested_rows
    ]

    decision = None
    if decision_row is not None:
        record, underwriter = decision_row
        decision = _decision_schema(record, underwriter.full_name if underwriter else None)

    return ApplicationDetailSchema(
        id=application.id,
        reference=applicant.external_ref,
        status=application.status,
        submitted_at=application.submitted_at,
        evaluated_at=application.evaluated_at,
        expected_by=application.expected_by,
        expected_by_note=application.expected_by_note,
        overdue=turnaround.is_overdue(application.expected_by, application.status.value),
        applicant=ApplicantIn(
            name=applicant.name or "",
            phone=applicant.phone or "",
            date_of_birth=applicant.date_of_birth,
            sex=applicant.sex,
            nid_number=applicant.nid_number,
            nid_name=applicant.nid_name,
            nid_date_of_birth=applicant.nid_date_of_birth,
            nominee_name=applicant.nominee_name,
            nominee_relation=applicant.nominee_relation,
            nominee_phone=applicant.nominee_phone,
            consent=applicant.consent_at is not None,
        ),
        coverage=CoverageIn(
            coverage_type=application.coverage_type,
            coverage_amount=application.coverage_amount,
            policy_term=application.policy_term,
            payment_mode=(
                "yearly" if application.payment_mode == "yearly" else "monthly"
            ),
        ),
        product=product,
        age=age,
        smoker=smoker,
        suggested_exclusions=pricing.suggested_exclusions(
            _arm_tiers(arms, score_row), application.declared_history
        ),
        assigned_to_id=application.assigned_to,
        assigned_to_name=(
            (await db.get(User, application.assigned_to)).full_name
            if application.assigned_to
            else None
        ),
        models_requested=application.models_requested or [],
        declared_history=application.declared_history or {},
        plan=(
            PlanSchema.model_validate(
                plans.for_tier(
                    score_row.tier.value if score_row else application.status.value,
                    product,
                    float(application.coverage_amount) if application.coverage_amount else None,
                    pricing.term_years(application.policy_term),
                    age,
                    applicant.sex,
                    smoker,
                    rates,
                )
            )
            if (score_row or application.status == ApplicationStatus.INSUFFICIENT_EVIDENCE)
            else None
        ),
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
        arms=arms,
        files=files,
        decision=decision,
        requested_documents=requested,
        sent_to_doctor_at=application.sent_to_doctor_at,
        doctor_reviews=[
            DoctorReviewSchema(
                verdict=review.verdict,
                note=review.note,
                doctor_name=name,
                created_at=review.created_at,
            )
            for review, name in (
                await db.execute(
                    select(DoctorReview, User.full_name)
                    .outerjoin(User, User.id == DoctorReview.doctor_id)
                    .where(DoctorReview.application_id == application.id)
                    .order_by(DoctorReview.created_at.desc())
                )
            ).all()
        ],
        client_messages=[
            ClientMessageSchema(
                urgency=message.urgency,
                message=message.message,
                sender_name=name,
                emailed=message.emailed,
                created_at=message.created_at,
            )
            for message, name in (
                await db.execute(
                    select(ClientMessage, User.full_name)
                    .outerjoin(User, User.id == ClientMessage.sender_id)
                    .where(ClientMessage.application_id == application.id)
                    .order_by(ClientMessage.created_at.desc())
                )
            ).all()
        ],
        policy=await _policy_of(db, application.id),
        errors=errors,
    )


async def _policy_of(db: AsyncSession, application_id: UUID):
    """The policy an approval issued for this application, if any."""
    from app.routers.policies import describe

    row = (
        await db.execute(
            select(InsurancePolicy).where(InsurancePolicy.application_id == application_id)
        )
    ).scalar_one_or_none()
    return (await describe(db, [row]))[0] if row else None


async def _list_files(db: AsyncSession, application: Application) -> list[FileSchema]:
    """Evidence images and any heatmaps produced for them."""
    evidence = (
        await db.execute(
            select(EvidenceFile).where(EvidenceFile.application_id == application.id)
        )
    ).scalars().all()

    artifacts = (
        await db.execute(
            select(ExplanationArtifact, ModelRun.model_arm_id, SubScore.details)
            .join(ModelRun, ModelRun.id == ExplanationArtifact.model_run_id)
            .outerjoin(SubScore, SubScore.model_run_id == ModelRun.id)
            .where(ModelRun.application_id == application.id)
        )
    ).all()

    # A heatmap belongs to the evidence its reader read. Each run records the
    # content hash of that file, which is the exact link. Files dropped into
    # the drop zone carry no reader, so pairing by arm alone left every heatmap
    # unpaired; it is kept only as the fallback for older runs without a hash.
    by_hash: dict[str, UUID] = {row.content_hash: row.id for row in evidence if row.content_hash}
    by_arm: dict[UUID, UUID] = {
        row.model_arm_id: row.id for row in evidence if row.model_arm_id is not None
    }

    def image_for(arm_id: UUID, details: dict | None) -> UUID | None:
        read = (details or {}).get("evidence_hash")
        return by_hash.get(read) if read in by_hash else by_arm.get(arm_id)

    return [
        FileSchema(
            id=row.id,
            kind="evidence",
            filename=row.original_filename,
            mime_type=row.mime_type,
            uploaded_at=row.uploaded_at,
            evidence_kind=row.evidence_kind,
            evidence_label=evidence_kinds.label(row.evidence_kind) if row.evidence_kind else None,
        )
        for row in evidence
    ] + [
        FileSchema(
            id=artifact.id,
            kind=artifact.artifact_type.value,
            filename=None,
            mime_type="image/png",
            of_file_id=image_for(arm_id, details),
        )
        for artifact, arm_id, details in artifacts
    ]


def _is_doctor(principal: Principal) -> bool:
    return principal.role == UserRole.MEDICAL_PROFESSIONAL.value


def _medical_or_owner(principal: Principal) -> bool:
    """A doctor's work: a doctor, or the administrator, who owns the company
    and may do anything in it. Never an underwriter."""
    return principal.role in (UserRole.MEDICAL_PROFESSIONAL.value, UserRole.ADMIN.value)


def _not_for_doctors(principal: Principal, what: str) -> None:
    """A doctor reviews results; the policy and the paperwork are the underwriter's."""
    if _is_doctor(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"A doctor reviews the results; {what} is for the underwriter.",
        )


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

    # A doctor sees only what was sent to a doctor. 404, not 403, for the
    # same reason as another company's application: saying it exists is a leak.
    if row is None or (_is_doctor(principal) and row[0].sent_to_doctor_at is None):
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
    background: BackgroundTasks,
    application_id: UUID,
    payload: DecisionIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> DecisionSchema:
    """One decision per application, enforced by the database.

    The built-in admin cannot decide: `underwriter_id` is a real foreign key,
    and a decision has to be attributable to a person who can be held to it.
    """
    application, applicant = await _load_owned(db, application_id, principal)

    # Asking for documents is a pause, not an outcome. Decisions are
    # write-once, so recording it here would decide the application forever
    # the moment a document was requested, and nothing could be decided once
    # it arrived. There is a separate endpoint for it.
    if payload.decision == UnderwriterDecisionType.REQUESTED_ADDITIONAL_EVIDENCE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Requesting evidence does not decide the application. Use "
                "POST /applications/{id}/evidence-request and name what is needed."
            ),
        )

    # Escalating is a hand-over, not an outcome. Recording it here used to
    # spend the write-once decision, so the doctor it was handed
    # to could never decide it. There is a separate endpoint for it.
    if payload.decision == UnderwriterDecisionType.ESCALATED_SENIOR_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Sending to a doctor does not decide the application. Use "
                "POST /applications/{id}/escalate; a doctor then checks the results."
            ),
        )

    _not_for_doctors(principal, "the insurance decision")

    # While a doctor has it, an underwriter does not decide: the doctor's
    # verdict is what the decision is waiting for. The administrator owns the
    # company and may override that.
    if application.status == ApplicationStatus.ESCALATED and principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is with a doctor. It can be decided once they send it back.",
        )

    approving = payload.decision in (
        UnderwriterDecisionType.CONFIRMED_FAST_TRACK,
        UnderwriterDecisionType.APPROVED_WITH_ADJUSTMENT,
    )
    declining = payload.decision == UnderwriterDecisionType.DECLINED
    product = pricing.product_for(application.coverage_type)
    rating = payload.rating_pct
    exclusions = [e.strip() for e in payload.exclusions if e and e.strip()]
    if payload.decision == UnderwriterDecisionType.CONFIRMED_FAST_TRACK:
        rating, exclusions = 0, []
    if approving and rating not in pricing.RATINGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The rating must be one of {', '.join(f'+{r}%' for r in pricing.RATINGS)}.",
        )
    if exclusions and product != "health":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Exclusions apply to hospital cover. For life cover, rate the premium instead.",
        )
    if payload.decision == UnderwriterDecisionType.APPROVED_WITH_ADJUSTMENT and not (
        rating or exclusions
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="An adjusted approval needs a rating, an exclusion, or both. With neither, "
            "approve at standard rates.",
        )
    if declining and payload.decline_reason not in decline_rules.REASONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Say why the application is declined.",
        )
    priced = None
    if approving:
        tenant = await db.get(Tenant, application.tenant_id)
        priced = pricing.quote(
            product,
            float(application.coverage_amount or 0),
            pricing.term_years(application.policy_term),
            pricing.age_on(applicant.date_of_birth, date.today()),
            applicant.sex,
            pricing.is_smoker(application.declared_history),
            rating,
            pricing.Rates.from_tenant(tenant) if tenant else pricing.DEFAULT_RATES,
        )
        if not application.coverage_amount or not priced.eligible:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(priced.reason or "There is no cover amount to insure.")
                + " Decline it as outside the product's limits instead.",
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

    # An underwriter may not approve an elevated case until a doctor has checked
    # its results. The review screen hides those buttons, but a
    # rule that exists only in the browser is not a rule: the same request sent
    # directly would have been accepted.
    if principal.role == UserRole.UNDERWRITER.value and (approving or declining):
        latest_score = (
            await db.execute(
                select(CompositeScore)
                .where(CompositeScore.application_id == application.id)
                .order_by(CompositeScore.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        reviewed = (await _latest_verdicts(db, [application.id])).get(application.id)
        if latest_score is not None and latest_score.tier == RiskTier.ELEVATED and not reviewed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "This application is elevated risk. Send it to a doctor first; "
                    "once they have checked the results you can decide it, either way."
                ),
            )

    record = UnderwriterDecision(
        tenant_id=principal.tenant_id,
        application_id=application.id,
        underwriter_id=underwriter.id,
        decision=payload.decision,
        final_premium=Decimal(str(priced.monthly_bdt)) if priced else None,
        rating_pct=rating if approving else 0,
        exclusions=exclusions if approving else [],
        decline_reason=payload.decline_reason if declining else None,
        decline_note=(payload.decline_note or "").strip() or None if declining else None,
        reapply_after=(
            pricing_dates.add_months(date.today(), payload.reapply_after_months)
            if declining and payload.reapply_after_months
            else None
        ),
    )
    db.add(record)
    application.status = ApplicationStatus.DECIDED
    # An approval issues the policy the client then sees on their portal.
    from app.routers.policies import issue_policy

    issued = await issue_policy(db, application, applicant, record, priced) if priced else None

    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=underwriter.id,
        event_type="decision_recorded",
        payload={
            "decision": payload.decision.value,
            "rating_pct": record.rating_pct,
            "exclusions": record.exclusions,
            "decline_reason": record.decline_reason,
            "annual_premium": priced.annual_bdt if priced else None,
            "policy_number": issued.policy_number if issued else None,
        },
    )
    await _notify_tenant(
        db,
        application,
        NotificationType.DECISION_RECORDED,
        f"{applicant.external_ref}: "
        + (
            f"declined ({decline_rules.staff_label(record.decline_reason)})"
            if declining
            else f"approved, policy {issued.policy_number}" if issued else "decision recorded"
        ),
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

    # Tell the applicant there is something to see. The message carries no
    # outcome, because email is not a confidential channel; it links to the
    # portal. Sent after the response so a slow mail server never delays the
    # underwriter.
    if applicant.email:
        background.add_task(
            outbox.send_logged,
            application.tenant_id,
            application.id,
            "decision_notice",
            applicant.email,
            f"An update on your application {applicant.external_ref}",
            mailer.send_decision_notice,
            applicant.email,
            applicant.name or "",
            applicant.external_ref,
        )

    return _decision_schema(record, underwriter.full_name)


def _decision_schema(record: UnderwriterDecision, name: str | None) -> DecisionSchema:
    return DecisionSchema(
        decision=record.decision,
        final_premium=record.final_premium,
        decided_at=record.decided_at,
        underwriter_name=name,
        rating_pct=record.rating_pct or 0,
        exclusions=list(record.exclusions or []),
        decline_reason=record.decline_reason,
        decline_reason_label=decline_rules.staff_label(record.decline_reason),
        decline_note=record.decline_note,
        reapply_after=record.reapply_after,
    )


def _arm_tiers(arms: list, score_row) -> dict[str, str]:
    """Each reader's tier, by the boundaries its application was scored with."""
    limits = (score_row.tier_thresholds or {}) if score_row else {}
    low = float(limits.get("low_max", Thresholds().low_max))
    moderate = float(limits.get("moderate_max", Thresholds().moderate_max))
    out: dict[str, str] = {}
    for run in arms:
        if run.score is None:
            continue
        out[run.arm] = (
            "low" if run.score <= low else "moderate" if run.score <= moderate else "elevated"
        )
    return out


# ── pricing one application ──────────────────────────────────────────────────


@router.post(
    "/applications/{application_id}/quote",
    response_model=QuoteSchema,
    summary="The premium for this client at a given rating",
)
async def quote_application(
    application_id: UUID,
    payload: QuoteIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> QuoteSchema:
    application, applicant = await _load_owned(db, application_id, principal)
    if payload.rating_pct not in pricing.RATINGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown rating."
        )
    tenant = await db.get(Tenant, principal.tenant_id)
    q = pricing.quote(
        pricing.product_for(application.coverage_type),
        float(application.coverage_amount or 0),
        pricing.term_years(application.policy_term),
        pricing.age_on(applicant.date_of_birth, date.today()),
        applicant.sex,
        pricing.is_smoker(application.declared_history),
        payload.rating_pct,
        pricing.Rates.from_tenant(tenant) if tenant else pricing.DEFAULT_RATES,
    )
    return _quote_schema(q)


def _quote_schema(q: pricing.Quote) -> QuoteSchema:
    return QuoteSchema(
        product=q.product,
        sum_assured_bdt=q.sum_assured,
        term_years=q.term_years,
        age=q.age,
        annual_bdt=q.annual_bdt,
        monthly_bdt=q.monthly_bdt,
        total_bdt=q.total_bdt,
        expected_claims_bdt=q.expected_claims_bdt,
        rating_pct=q.rating_pct,
        smoker=q.smoker,
        eligible=q.eligible,
        reason=q.reason,
    )


# ── who has the case ─────────────────────────────────────────────────────────


@router.post(
    "/applications/{application_id}/assign",
    response_model=ApplicationDetailSchema,
    summary="Take the case (or hand it back with release=true)",
)
async def assign_application(
    application_id: UUID,
    release: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ApplicationDetailSchema:
    """One underwriter takes a case so two do not work it at once. Anyone may
    see it; the queue says who has it. An administrator can take it over."""
    _not_for_doctors(principal, "taking a case")
    application, _ = await _load_owned(db, application_id, principal)
    me = await db.get(User, principal.user_id)
    if me is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No user record.")
    if release:
        if application.assigned_to not in (None, me.id) and principal.role != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only the person who has it can hand it back.",
            )
        application.assigned_to = None
        application.assigned_at = None
    else:
        if (
            application.assigned_to not in (None, me.id)
            and principal.role != UserRole.ADMIN.value
        ):
            holder = await db.get(User, application.assigned_to)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{holder.full_name if holder else 'Someone'} already has this case.",
            )
        application.assigned_to = me.id
        application.assigned_at = datetime.now(UTC)
    await persistence.append_audit(
        db,
        tenant_id=application.tenant_id,
        application_id=application.id,
        actor_user_id=me.id,
        event_type="case_released" if release else "case_taken",
        payload={"by": me.full_name},
    )
    await db.commit()
    return await get_application(application_id, db, principal)


# ── turnaround ───────────────────────────────────────────────────────────────


@router.patch(
    "/applications/{application_id}/turnaround",
    response_model=ApplicationDetailSchema,
    summary="Revise when the applicant can expect an answer",
)
async def revise_turnaround(
    application_id: UUID,
    payload: TurnaroundIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ApplicationDetailSchema:
    """Move the expected date, with a reason the applicant will see.

    Any underwriter on the case may do this: they are the one who knows the
    answer will be late, so they should be the one who can say so. The old and
    new dates and the reason go into the audit trail.
    """
    _not_for_doctors(principal, "the promised date")
    application, _ = await _load_owned(db, application_id, principal)

    if application.status == ApplicationStatus.DECIDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application has already been decided.",
        )

    # Local date, for the same reason as at submit: early in the morning the
    # UTC date is still yesterday, and "yesterday" would pass as not-yet-past.
    today = date.today()
    if payload.expected_by < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The expected date cannot be in the past.",
        )

    previous = application.expected_by
    application.expected_by = payload.expected_by
    application.expected_by_note = payload.reason.strip()

    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=await _actor_id(db, principal),
        event_type="turnaround_revised",
        payload={
            "from": previous.isoformat() if previous else None,
            "to": payload.expected_by.isoformat(),
            "reason": payload.reason.strip(),
        },
    )
    await db.commit()

    return await get_application(application_id, db, principal)


# ── requested documents ──────────────────────────────────────────────────────


@router.post(
    "/applications/{application_id}/evidence-request",
    response_model=list[RequestedDocumentSchema],
    status_code=status.HTTP_201_CREATED,
    summary="Ask the applicant for specific documents",
)
async def request_evidence(
    application_id: UUID,
    payload: RequestEvidenceIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[RequestedDocumentSchema]:
    """Name what is missing, in the underwriter's own words.

    Moves the application to `awaiting_evidence` and leaves the decision open:
    this is a pause, not an outcome. The list is what the applicant will see,
    so each item is stored verbatim.
    """
    _not_for_doctors(principal, "asking the client for documents")
    application, applicant = await _load_owned(db, application_id, principal)

    if application.status == ApplicationStatus.DECIDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application has already been decided.",
        )

    items = [text.strip() for text in payload.items if text.strip()]
    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name at least one document. A request for nothing tells the applicant nothing.",
        )

    actor = await _actor_id(db, principal)
    rows = [
        RequestedDocument(
            tenant_id=principal.tenant_id,
            application_id=application.id,
            requested_by=actor,
            description=item,
        )
        for item in items
    ]
    db.add_all(rows)
    application.status = ApplicationStatus.AWAITING_EVIDENCE

    plural = "s" if len(items) != 1 else ""
    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=actor,
        event_type="evidence_requested",
        payload={"items": items, "note": payload.note},
    )
    await _notify_tenant(
        db,
        application,
        NotificationType.EVIDENCE_REQUESTED,
        f"{applicant.external_ref}: {len(items)} document{plural} requested from the applicant",
    )
    await db.commit()
    for row in rows:
        await db.refresh(row)

    requester = await db.get(User, actor) if actor else None
    return [
        RequestedDocumentSchema(
            id=row.id,
            description=row.description,
            requested_at=row.requested_at,
            requested_by_name=requester.full_name if requester else None,
            fulfilled_at=None,
        )
        for row in rows
    ]


@router.post(
    "/applications/{application_id}/escalate",
    response_model=ApplicationDetailSchema,
    summary="Hand the application to a doctor",
)
async def escalate_application(
    application_id: UUID,
    payload: EscalateIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ApplicationDetailSchema:
    """Pass the application up without deciding it.

    The decision stays open: a doctor checks the results and sends it back,
    and the underwriter decides.
    Every doctor in the company is told. The clock the client
    was given keeps running: the company still holds the case.
    """
    _not_for_doctors(principal, "sending to a doctor")
    application, _ = await _load_owned(db, application_id, principal)

    if application.status == ApplicationStatus.DECIDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application has already been decided.",
        )
    if application.status == ApplicationStatus.ESCALATED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is already with a doctor.",
        )
    if application.status == ApplicationStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The models are reading the evidence now. Wait for them to finish.",
        )

    application.status = ApplicationStatus.ESCALATED
    # Kept once set: an application sent to a doctor stays visible to them
    # after they return it, so they can see what became of it.
    application.sent_to_doctor_at = application.sent_to_doctor_at or datetime.now(UTC)
    actor = await _actor_id(db, principal)
    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=actor,
        event_type="escalated",
        payload={"note": payload.note, "by_role": principal.role},
    )

    # Told to the doctors, who now own the decision, and to no
    # one else: the rest of the company sees the status change in the queue.
    medics = await db.execute(
        select(User).where(
            User.tenant_id == application.tenant_id,
            User.is_active.is_(True),
            User.role == UserRole.MEDICAL_PROFESSIONAL,
        )
    )
    reference = (await db.get(Applicant, application.applicant_id)).external_ref
    for user in medics.scalars().all():
        db.add(
            Notification(
                tenant_id=application.tenant_id,
                user_id=user.id,
                application_id=application.id,
                notification_type=NotificationType.TIER_ESCALATION,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=f"{reference} has been sent to you to check the results."
                + (f" Note: {payload.note}" if payload.note else ""),
            )
        )
    await db.commit()
    return await get_application(application_id, db, principal)


async def _latest_verdicts(db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    """The newest doctor's verdict per application, for those that have one."""
    if not ids:
        return {}
    rows = await db.execute(
        select(DoctorReview.application_id, DoctorReview.verdict)
        .where(DoctorReview.application_id.in_(ids))
        .order_by(DoctorReview.created_at.desc())
    )
    out: dict[UUID, str] = {}
    for application_id, verdict in rows.all():
        out.setdefault(application_id, verdict)
    return out


@router.post(
    "/applications/{application_id}/doctor-review",
    response_model=ApplicationDetailSchema,
    summary="A doctor returns the application with a verdict on the results",
)
async def review_as_doctor(
    application_id: UUID,
    payload: DoctorReviewIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ApplicationDetailSchema:
    """The doctor says whether the readers' results are medically right, and
    the application goes back to the underwriter carrying that verdict. The
    doctor decides nothing about the policy."""
    if not _medical_or_owner(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a doctor can return a verdict on the results.",
        )
    application, applicant = await _load_owned(db, application_id, principal)
    if application.status != ApplicationStatus.ESCALATED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application is not waiting for a doctor.",
        )

    doctor = await db.get(User, principal.user_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has no user record, so the review could not be attributed.",
        )
    note = (payload.note or "").strip() or None
    db.add(
        DoctorReview(
            tenant_id=principal.tenant_id,
            application_id=application.id,
            doctor_id=doctor.id,
            verdict=payload.verdict,
            note=note,
        )
    )
    application.status = ApplicationStatus.SCORED
    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=doctor.id,
        event_type="doctor_reviewed",
        payload={"verdict": payload.verdict, "note": note},
    )

    found = "accurate" if payload.verdict == "accurate" else "inaccurate"
    underwriters = await db.execute(
        select(User).where(
            User.tenant_id == application.tenant_id,
            User.is_active.is_(True),
            User.role == UserRole.UNDERWRITER,
        )
    )
    for user in underwriters.scalars().all():
        db.add(
            Notification(
                tenant_id=application.tenant_id,
                user_id=user.id,
                application_id=application.id,
                notification_type=NotificationType.DOCTOR_REVIEWED,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=(
                    f"{applicant.external_ref}: a doctor found the results {found}. "
                    "It is back with you to decide."
                    + (f" Note: {note}" if note else "")
                ),
            )
        )
    await db.commit()
    return await get_application(application_id, db, principal)


@router.post(
    "/applications/{application_id}/client-message",
    response_model=ApplicationDetailSchema,
    summary="A doctor writes to the client directly",
)
async def message_client(
    application_id: UUID,
    payload: ClientMessageIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ApplicationDetailSchema:
    """For what cannot wait for the policy: "please see a doctor today". The
    client sees it on their portal, and by email when mail is set up. It
    carries the doctor's words only — never a score."""
    if not _medical_or_owner(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a doctor can write to the client about their health.",
        )
    application, applicant = await _load_owned(db, application_id, principal)
    doctor = await db.get(User, principal.user_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has no user record, so the message could not be attributed.",
        )

    text = payload.message.strip()
    emailed = False
    if applicant.email:
        emailed = mailer.send_doctor_message(
            applicant.email, applicant.name or "", applicant.external_ref, payload.urgency, text
        )
        outbox.record(
            db,
            principal.tenant_id,
            application.id,
            "doctor_message",
            applicant.email,
            f"A doctor's note about your application {applicant.external_ref}",
            emailed,
        )
    db.add(
        ClientMessage(
            tenant_id=principal.tenant_id,
            application_id=application.id,
            sender_id=doctor.id,
            urgency=payload.urgency,
            message=text,
            emailed=emailed,
        )
    )
    await persistence.append_audit(
        db,
        tenant_id=principal.tenant_id,
        application_id=application.id,
        actor_user_id=doctor.id,
        event_type="doctor_messaged_client",
        payload={"urgency": payload.urgency, "emailed": emailed},
    )
    await db.commit()
    return await get_application(application_id, db, principal)


async def settle_after_receipt(db: AsyncSession, application: Application) -> None:
    """Once nothing asked for is outstanding, the application goes back to
    the underwriter. Shared by the staff tick-off and the client's upload."""
    # The session does not autoflush, so without this the count below still
    # sees the row just ticked as outstanding and the application never leaves
    # awaiting_evidence. The test for this endpoint caught exactly that.
    await db.flush()

    outstanding = (
        await db.execute(
            select(func.count()).where(
                RequestedDocument.application_id == application.id,
                RequestedDocument.fulfilled_at.is_(None),
            )
        )
    ).scalar_one()

    if outstanding == 0 and application.status == ApplicationStatus.AWAITING_EVIDENCE:
        has_score = (
            await db.execute(
                select(func.count()).where(CompositeScore.application_id == application.id)
            )
        ).scalar_one()
        application.status = (
            ApplicationStatus.SCORED if has_score else ApplicationStatus.INSUFFICIENT_EVIDENCE
        )


@router.post(
    "/applications/{application_id}/evidence-request/{document_id}/fulfil",
    response_model=RequestedDocumentSchema,
    summary="Mark a requested document as received",
)
async def fulfil_evidence_request(
    application_id: UUID,
    document_id: UUID,
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> RequestedDocumentSchema:
    """Tick off one item, attaching the document if it is in hand. When nothing
    is outstanding, the application goes back to the underwriter.

    An attached file is stored with the application and linked to the request
    (`fulfilled_by`), so the record shows which document answered it. It is
    not re-scored: an existing score stands.
    """
    _not_for_doctors(principal, "marking documents received")
    application, _ = await _load_owned(db, application_id, principal)

    row = (
        await db.execute(
            select(RequestedDocument).where(
                RequestedDocument.id == document_id,
                RequestedDocument.application_id == application.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such request.")

    # Idempotent: ticking something already ticked is not an error.
    if row.fulfilled_at is None:
        row.fulfilled_at = datetime.now(UTC)
        if file is not None and file.filename:
            created: list[EvidenceFile] = []
            stored, rejected = await _store_evidence(
                db, principal, application, [file], [""], ["document"], created
            )
            if rejected:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"The file could not be stored: {rejected[0]}",
                )
            await db.flush()
            row.fulfilled_by = created[0].id if created else None
        await persistence.append_audit(
            db,
            tenant_id=principal.tenant_id,
            application_id=application.id,
            actor_user_id=await _actor_id(db, principal),
            event_type="evidence_received",
            payload={"document_id": str(row.id), "description": row.description},
        )

    await settle_after_receipt(db, application)
    await db.commit()
    await db.refresh(row)

    requester = await db.get(User, row.requested_by) if row.requested_by else None
    return RequestedDocumentSchema(
        id=row.id,
        description=row.description,
        requested_at=row.requested_at,
        requested_by_name=requester.full_name if requester else None,
        fulfilled_at=row.fulfilled_at,
        fulfilled_by_file_id=row.fulfilled_by,
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

    if path is not None and _is_doctor(principal):
        owner = evidence.application_id if evidence else (
            await db.execute(
                select(ModelRun.application_id)
                .join(ExplanationArtifact, ExplanationArtifact.model_run_id == ModelRun.id)
                .where(ExplanationArtifact.id == file_id)
            )
        ).scalar_one_or_none()
        sent = (
            await db.execute(select(Application.sent_to_doctor_at).where(Application.id == owner))
        ).scalar_one_or_none()
        if sent is None:
            path = None

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

    # A stored mammogram is a de-identified DICOM; the screen gets a PNG of it.
    if absolute.suffix == ".dcm":
        try:
            return Response(content=dicom_to_png(absolute.read_bytes()), media_type="image/png")
        except Exception as exc:
            log.error("Could not draw mammogram %s: %s", path, exc)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The stored mammogram could not be drawn.",
            ) from exc

    # A note is served as the text it is, for the underwriter to read.
    if absolute.suffix == ".txt":
        return Response(content=absolute.read_bytes(), media_type="text/plain; charset=utf-8")

    # A stored ECG is a signal array. The review screen asks for a picture, so
    # it is drawn on the way out; the signal itself is what the model read.
    if absolute.suffix == ".npy":
        try:
            drawn = ecg_signal.render(ecg_signal.from_bytes(absolute.read_bytes()))
        except Exception as exc:
            log.error("Could not draw ECG %s: %s", path, exc)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="The stored ECG could not be drawn."
            ) from exc
        return Response(content=drawn, media_type="image/png")

    return FileResponse(absolute, media_type="image/png")
