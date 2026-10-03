"""Deleting a client's personal data at their request.

The Personal Data Protection Ordinance 2025 gives a person the right to have
their data erased. Here a client asks from their portal; an administrator
approves (or declines, saying why); the data is erased on the thirtieth day
after the request, automatically. Until then the client can change their mind.

**What is erased:** name, phone, email, date of birth, sex, height and weight,
NID, nominee, portal sign-in; every file (evidence, heatmaps, face photo, NID
card, claim documents); the declared health answers; the readers' detailed
findings; doctors' messages and notes; requested documents. The client can no
longer sign in.

**What is kept, anonymised:** that an application, a decision, a policy and
any claim existed, with their dates and amounts. Insurance and tax law need
those records, and without the person attached they identify no one. The
hash-chained audit log is not rewritten (that is its whole point); it holds
references and event names, not health data.

**When it is refused:** while the client has a policy in force or a claim
open. Erasing them would leave a policy no one can claim on; the policy is
cancelled first (which the administrator can do) or allowed to end.
"""

import asyncio
import contextlib
import logging
import shutil
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import persistence
from app.config import settings
from app.db.session import AsyncSessionLocal, get_db
from app.deps import Principal, current_principal
from app.models import (
    Applicant,
    Application,
    Claim,
    ClaimDocument,
    ClientMessage,
    DataDeletionRequest,
    DoctorReview,
    EvidenceFile,
    InsurancePolicy,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RequestedDocument,
    User,
    UserRole,
)
from app.schemas.auth import BaseSchema

router = APIRouter(tags=["Data deletion"])
log = logging.getLogger(__name__)

DELETE_AFTER_DAYS = 30


class DeletionSchema(BaseSchema):
    id: UUID
    client_id: UUID
    client_reference: str | None = None
    client_name: str | None = None
    reason: str | None = None
    # pending | approved | declined | withdrawn | completed
    status: str
    requested_at: datetime
    delete_on: date
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decline_reason: str | None = None
    completed_at: datetime | None = None
    # Why it cannot be approved yet, if it cannot.
    blockers: list[str] = Field(default_factory=list)


class DeletionDecisionIn(BaseSchema):
    approve: bool
    reason: str | None = Field(default=None, max_length=1000)
    # Erase now rather than on the thirtieth day.
    now: bool = False


async def blockers(db: AsyncSession, applicant_id: UUID) -> list[str]:
    out: list[str] = []
    today = date.today()
    policies = (
        (
            await db.execute(
                select(InsurancePolicy).where(InsurancePolicy.applicant_id == applicant_id)
            )
        )
        .scalars()
        .all()
    )
    for p in policies:
        if p.status == "active" and p.end_date > today:
            out.append(f"Policy {p.policy_number} is in force. Cancel it first.")
    open_claims = (
        (
            await db.execute(
                select(Claim.claim_number).where(
                    Claim.applicant_id == applicant_id,
                    Claim.status.in_(
                        ("submitted", "documents_requested", "under_review", "approved")
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for number in open_claims:
        out.append(f"Claim {number} is still open.")
    return out


async def describe(db: AsyncSession, rows: list[DataDeletionRequest]) -> list[DeletionSchema]:
    if not rows:
        return []
    applicants = {
        a.id: a
        for a in (
            await db.execute(
                select(Applicant).where(Applicant.id.in_({r.applicant_id for r in rows}))
            )
        ).scalars()
    }
    deciders = {r.decided_by for r in rows if r.decided_by}
    names = (
        {
            u.id: u.full_name
            for u in (await db.execute(select(User).where(User.id.in_(deciders)))).scalars()
        }
        if deciders
        else {}
    )
    out = []
    for r in rows:
        a = applicants.get(r.applicant_id)
        out.append(
            DeletionSchema(
                id=r.id,
                client_id=r.applicant_id,
                client_reference=a.external_ref if a else None,
                client_name=a.name if a else None,
                reason=r.reason,
                status=r.status,
                requested_at=r.requested_at,
                delete_on=r.delete_on,
                decided_by_name=names.get(r.decided_by) if r.decided_by else None,
                decided_at=r.decided_at,
                decline_reason=r.decline_reason,
                completed_at=r.completed_at,
                blockers=await blockers(db, r.applicant_id)
                if r.status in ("pending", "approved")
                else [],
            )
        )
    return out


# ── the client's side (called from routers/portal.py) ─────────────────────────


async def request(
    db: AsyncSession, applicant: Applicant, reason: str | None
) -> DataDeletionRequest:
    existing = (
        await db.execute(
            select(DataDeletionRequest).where(
                DataDeletionRequest.applicant_id == applicant.id,
                DataDeletionRequest.status.in_(("pending", "approved")),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You have already asked for this."
        )
    row = DataDeletionRequest(
        tenant_id=applicant.tenant_id,
        applicant_id=applicant.id,
        reason=(reason or "").strip() or None,
        status="pending",
        delete_on=date.today() + timedelta(days=DELETE_AFTER_DAYS),
    )
    db.add(row)
    admins = (
        (
            await db.execute(
                select(User.id).where(
                    User.tenant_id == applicant.tenant_id,
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    for admin in admins:
        db.add(
            Notification(
                tenant_id=applicant.tenant_id,
                user_id=admin,
                application_id=None,
                notification_type=NotificationType.DELETION_REQUESTED,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=f"{applicant.external_ref} asked for their data to be deleted. "
                f"It is due by {row.delete_on:%d %b %Y}.",
            )
        )
    return row


async def latest_for(db: AsyncSession, applicant_id: UUID) -> DataDeletionRequest | None:
    return (
        await db.execute(
            select(DataDeletionRequest)
            .where(DataDeletionRequest.applicant_id == applicant_id)
            .order_by(DataDeletionRequest.requested_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _application_of(db: AsyncSession, applicant_id: UUID) -> UUID | None:
    """The application whose audit chain a deletion is written to."""
    return (
        await db.execute(
            select(Application.id).where(Application.applicant_id == applicant_id).limit(1)
        )
    ).scalar_one_or_none()


# ── the administrator's side ─────────────────────────────────────────────────


def _owner(principal: Principal) -> None:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator handles requests to delete data.",
        )


@router.get(
    "/deletion-requests", response_model=list[DeletionSchema], summary="Requests to delete data"
)
async def list_requests(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[DeletionSchema]:
    _owner(principal)
    # Anything due is carried out before the list is shown.
    await run_due(db)
    rows = (
        (
            await db.execute(
                select(DataDeletionRequest)
                .where(DataDeletionRequest.tenant_id == principal.tenant_id)
                .order_by(DataDeletionRequest.requested_at.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    return await describe(db, list(rows))


@router.post(
    "/deletion-requests/{request_id}/decision",
    response_model=DeletionSchema,
    summary="Approve or decline a request to delete data",
)
async def decide(
    request_id: UUID,
    payload: DeletionDecisionIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> DeletionSchema:
    _owner(principal)
    row = (
        await db.execute(
            select(DataDeletionRequest).where(
                DataDeletionRequest.id == request_id,
                DataDeletionRequest.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such request.")
    if row.status != "pending" and not (
        payload.approve and payload.now and row.status == "approved"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"This request is already {row.status}."
        )
    if payload.approve:
        stopping = await blockers(db, row.applicant_id)
        if stopping:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=" ".join(stopping))
        row.status = "approved"
    else:
        if not (payload.reason or "").strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Say why; the client reads it.",
            )
        row.status = "declined"
        row.decline_reason = payload.reason.strip()
    row.decided_by = principal.user_id
    row.decided_at = datetime.now(UTC)
    chain = await _application_of(db, row.applicant_id)
    if chain:
        await persistence.append_audit(
            db,
            tenant_id=row.tenant_id,
            application_id=chain,
            actor_user_id=principal.user_id,
            event_type="deletion_approved" if payload.approve else "deletion_declined",
            payload={"request": str(row.id)},
        )
    if payload.approve and payload.now:
        row.delete_on = date.today()
    await db.commit()
    if payload.approve and row.delete_on <= date.today():
        await run_due(db)
    await db.refresh(row)
    return (await describe(db, [row]))[0]


# ── carrying it out ──────────────────────────────────────────────────────────


async def erase(db: AsyncSession, applicant: Applicant) -> None:
    """Erase one client's personal data, keeping anonymised records."""
    applications = (
        (await db.execute(select(Application).where(Application.applicant_id == applicant.id)))
        .scalars()
        .all()
    )
    app_ids = [a.id for a in applications]

    for a in applications:
        folder = settings.data_dir / str(a.tenant_id) / str(a.id)
        if folder.exists():
            await asyncio.to_thread(shutil.rmtree, folder, True)
        a.declared_history = {}
        a.expected_by_note = None
    if app_ids:
        await db.execute(
            update(EvidenceFile)
            .where(EvidenceFile.application_id.in_(app_ids))
            .values(original_filename=None, storage_path="deleted")
        )
        await db.execute(delete(ClientMessage).where(ClientMessage.application_id.in_(app_ids)))
        await db.execute(
            delete(RequestedDocument).where(RequestedDocument.application_id.in_(app_ids))
        )
        await db.execute(
            update(DoctorReview).where(DoctorReview.application_id.in_(app_ids)).values(note=None)
        )
        from app.models import ModelRun, SubScore

        runs = select(ModelRun.id).where(ModelRun.application_id.in_(app_ids))
        await db.execute(update(SubScore).where(SubScore.model_run_id.in_(runs)).values(details={}))
    claim_ids = select(Claim.id).where(Claim.applicant_id == applicant.id)
    await db.execute(delete(ClaimDocument).where(ClaimDocument.claim_id.in_(claim_ids)))
    await db.execute(
        update(Claim)
        .where(Claim.applicant_id == applicant.id)
        .values(
            description="Deleted at the client's request",
            hospital=None,
            claimant_name=None,
            documents_note=None,
        )
    )

    applicant.name = "Deleted client"
    # The column is required; a dash says "erased", not "never given".
    applicant.phone = "—"
    applicant.email = None
    applicant.date_of_birth = None
    applicant.sex = None
    applicant.height_cm = None
    applicant.weight_kg = None
    applicant.face_photo_path = None
    applicant.portal_id = None
    applicant.password_hash = None
    applicant.nid_number = None
    applicant.nid_name = None
    applicant.nid_date_of_birth = None
    applicant.nid_image_path = None
    applicant.nominee_name = None
    applicant.nominee_relation = None
    applicant.nominee_phone = None
    applicant.deleted_at = datetime.now(UTC)


async def run_due(db: AsyncSession) -> int:
    """Carry out every approved request whose day has come. Returns how many."""
    due = (
        (
            await db.execute(
                select(DataDeletionRequest).where(
                    DataDeletionRequest.status == "approved",
                    DataDeletionRequest.delete_on <= date.today(),
                )
            )
        )
        .scalars()
        .all()
    )
    done = 0
    for row in due:
        applicant = await db.get(Applicant, row.applicant_id)
        if applicant is None:
            continue
        if await blockers(db, applicant.id):
            # Something started after approval (a claim, say): wait for it.
            continue
        chain = await _application_of(db, applicant.id)
        await erase(db, applicant)
        row.status = "completed"
        row.completed_at = datetime.now(UTC)
        if chain:
            await persistence.append_audit(
                db,
                tenant_id=row.tenant_id,
                application_id=chain,
                actor_user_id=None,
                event_type="data_deleted",
                payload={"request": str(row.id)},
            )
        done += 1
    if done:
        await db.commit()
    return done


async def scheduler(stop: asyncio.Event) -> None:
    """Runs in the API process: checks for due deletions every hour."""
    while not stop.is_set():
        try:
            async with AsyncSessionLocal() as db:
                count = await run_due(db)
                if count:
                    log.info("Erased the data of %d client(s) on schedule.", count)
        except Exception as exc:  # the database may be down; try again later
            log.warning("Scheduled data deletion did not run: %s", exc)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=3600)
