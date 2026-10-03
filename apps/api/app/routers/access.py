"""Asking to see a client's personal details, and the owner answering.

A client's phone, email, portal sign-in, date of birth and test results are the
company owner's to hand out. An underwriter or a doctor sees each client's name
and reference, and asks, with a reason, for the rest. Every administrator is
told; one of them approves or declines, and the person who asked is told.

An approval opens that one client to that one person for `ACCESS_HOURS`. An
administrator never needs to ask.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import (
    Applicant,
    Application,
    ClientAccessRequest,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    User,
    UserRole,
)
from app.schemas.auth import BaseSchema

router = APIRouter(tags=["Client access"])

# How long an approval lasts. A day covers the piece of work it was asked for,
# and a stale approval does not quietly become standing access.
ACCESS_HOURS = 24

_ROLE_WORDS = {
    UserRole.UNDERWRITER.value: "Underwriter",
    UserRole.MEDICAL_PROFESSIONAL.value: "Doctor",
    UserRole.ADMIN.value: "Administrator",
}


class AccessRequestIn(BaseSchema):
    reason: str = Field(..., min_length=5, max_length=1000)


class AccessDecisionIn(BaseSchema):
    approve: bool


class AccessRequestSchema(BaseSchema):
    id: UUID
    client_id: UUID
    client_reference: str
    client_name: str | None = None
    requester_name: str | None = None
    requester_role: str | None = None
    reason: str
    status: str
    created_at: datetime
    decided_at: datetime | None = None
    decided_by_name: str | None = None
    # Until when an approval lets them see the client. None unless approved.
    expires_at: datetime | None = None


# ── who may see what ─────────────────────────────────────────────────────────


def is_admin(principal: Principal) -> bool:
    return principal.role == UserRole.ADMIN.value


def _cutoff() -> datetime:
    return datetime.now(UTC) - timedelta(hours=ACCESS_HOURS)


async def access_to(
    db: AsyncSession, principal: Principal, applicant_ids: list[UUID]
) -> dict[UUID, tuple[str, datetime | None]]:
    """Per client: ("full" | "granted" | "pending" | "declined" | "none", until).

    "full" is an administrator; "granted" is an approval still running, with the
    moment it ends. The newest request decides a client's state.
    """
    if is_admin(principal):
        return {i: ("full", None) for i in applicant_ids}
    out: dict[UUID, tuple[str, datetime | None]] = {i: ("none", None) for i in applicant_ids}
    if not applicant_ids:
        return out
    rows = (
        await db.execute(
            select(ClientAccessRequest)
            .where(
                ClientAccessRequest.tenant_id == principal.tenant_id,
                ClientAccessRequest.requester_id == principal.user_id,
                ClientAccessRequest.applicant_id.in_(applicant_ids),
            )
            .order_by(ClientAccessRequest.created_at.desc())
        )
    ).scalars().all()
    seen: set[UUID] = set()
    cutoff = _cutoff()
    for r in rows:
        if r.applicant_id in seen:
            continue
        seen.add(r.applicant_id)
        if r.status == "approved" and r.decided_at and r.decided_at > cutoff:
            out[r.applicant_id] = ("granted", r.decided_at + timedelta(hours=ACCESS_HOURS))
        elif r.status == "pending":
            out[r.applicant_id] = ("pending", None)
        elif r.status == "declined":
            out[r.applicant_id] = ("declined", None)
    return out


def can_see(state: str) -> bool:
    return state in ("full", "granted")


# ── endpoints ────────────────────────────────────────────────────────────────


async def _notify(
    db: AsyncSession, tenant_id: UUID, user_ids: list[UUID], kind: NotificationType, message: str
) -> None:
    for user_id in user_ids:
        db.add(
            Notification(
                tenant_id=tenant_id,
                user_id=user_id,
                application_id=None,
                notification_type=kind,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=message,
            )
        )


async def _schema(db: AsyncSession, rows: list[ClientAccessRequest]) -> list[AccessRequestSchema]:
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
    people = {r.requester_id for r in rows} | {r.decided_by for r in rows if r.decided_by}
    users = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_(people)))).scalars()
    }
    out = []
    for r in rows:
        applicant = applicants.get(r.applicant_id)
        requester = users.get(r.requester_id)
        decider = users.get(r.decided_by) if r.decided_by else None
        out.append(
            AccessRequestSchema(
                id=r.id,
                client_id=r.applicant_id,
                client_reference=applicant.external_ref if applicant else "—",
                client_name=applicant.name if applicant else None,
                requester_name=requester.full_name if requester else None,
                requester_role=_ROLE_WORDS.get(requester.role.value) if requester else None,
                reason=r.reason,
                status=r.status,
                created_at=r.created_at,
                decided_at=r.decided_at,
                decided_by_name=decider.full_name if decider else None,
                expires_at=(
                    r.decided_at + timedelta(hours=ACCESS_HOURS)
                    if r.status == "approved" and r.decided_at
                    else None
                ),
            )
        )
    return out


@router.post(
    "/clients/{client_id}/access-requests",
    response_model=AccessRequestSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Ask to see a client's details, with a reason",
)
async def request_access(
    client_id: UUID,
    payload: AccessRequestIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> AccessRequestSchema:
    if is_admin(principal):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An administrator already sees every client.",
        )
    applicant = (
        await db.execute(
            select(Applicant).where(
                Applicant.id == client_id, Applicant.tenant_id == principal.tenant_id
            )
        )
    ).scalar_one_or_none()
    # A doctor may ask only about a client who was sent to them; any other is,
    # to them, not there at all.
    if applicant is not None and principal.role == UserRole.MEDICAL_PROFESSIONAL.value:
        sent = (
            await db.execute(
                select(Application.id).where(
                    Application.applicant_id == applicant.id,
                    Application.sent_to_doctor_at.is_not(None),
                )
            )
        ).first()
        if sent is None:
            applicant = None
    if applicant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such client.")

    state, _ = (await access_to(db, principal, [applicant.id]))[applicant.id]
    if state == "granted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You can already see this client's details.",
        )
    if state == "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already asked. An administrator has been told.",
        )

    row = ClientAccessRequest(
        tenant_id=principal.tenant_id,
        applicant_id=applicant.id,
        requester_id=principal.user_id,
        reason=payload.reason.strip(),
        status="pending",
    )
    db.add(row)

    requester = await db.get(User, principal.user_id)
    who = requester.full_name if requester else "Someone"
    role = _ROLE_WORDS.get(principal.role, principal.role)
    admins = (
        await db.execute(
            select(User.id).where(
                User.tenant_id == principal.tenant_id,
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
    ).scalars().all()
    await _notify(
        db,
        principal.tenant_id,
        list(admins),
        NotificationType.ACCESS_REQUESTED,
        f"{who} ({role}) asked to see the details of {applicant.external_ref}. "
        f"Reason: {row.reason}",
    )
    await db.commit()
    await db.refresh(row)
    return (await _schema(db, [row]))[0]


@router.get(
    "/access-requests",
    response_model=list[AccessRequestSchema],
    summary="Requests to see client details: all of them for an administrator, your own otherwise",
)
async def list_access_requests(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[AccessRequestSchema]:
    stmt = select(ClientAccessRequest).where(ClientAccessRequest.tenant_id == principal.tenant_id)
    if not is_admin(principal):
        stmt = stmt.where(ClientAccessRequest.requester_id == principal.user_id)
    rows = (
        await db.execute(stmt.order_by(ClientAccessRequest.created_at.desc()).limit(200))
    ).scalars().all()
    return await _schema(db, list(rows))


@router.post(
    "/access-requests/{request_id}/decision",
    response_model=AccessRequestSchema,
    summary="Approve or decline a request to see a client's details",
)
async def decide_access_request(
    request_id: UUID,
    payload: AccessDecisionIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> AccessRequestSchema:
    if not is_admin(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator answers requests to see client details.",
        )
    row = (
        await db.execute(
            select(ClientAccessRequest).where(
                ClientAccessRequest.id == request_id,
                ClientAccessRequest.tenant_id == principal.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such request.")
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request was already {row.status}.",
        )

    row.status = "approved" if payload.approve else "declined"
    row.decided_by = principal.user_id
    row.decided_at = datetime.now(UTC)

    applicant = await db.get(Applicant, row.applicant_id)
    reference = applicant.external_ref if applicant else "the client"
    await _notify(
        db,
        principal.tenant_id,
        [row.requester_id],
        NotificationType.ACCESS_DECIDED,
        (
            f"You can now see the details of {reference} for the next {ACCESS_HOURS} hours."
            if payload.approve
            else f"Your request to see the details of {reference} was declined."
        ),
    )
    await db.commit()
    await db.refresh(row)
    return (await _schema(db, [row]))[0]
