"""Claims: a client (or someone for them) asks the policy to pay.

**How a claim runs**

1. *Filed.* Hospital bills from the client's portal; a death claim by the
   nominee at the office, which staff enter. Documents go with it: bills,
   discharge summary, death certificate.
2. *Checked* against the policy, automatically, and shown to whoever decides:
   was the policy in force on the day, is the illness still in its 30-day
   waiting period, is a pre-existing condition still in its two years, might
   an exclusion apply, is the amount within what is left of the year's limit.
   These are prompts for a person, not decisions.
3. *Documents.* Staff can ask for more. When they have everything they mark
   the documents complete, which starts the clock: by law (Insurance Act 2010)
   a claim is settled within **90 days** of the documents being complete.
4. *Decided.* Approved for an amount (never above what the policy pays), or
   rejected with a reason the client reads.
5. *Settled.* The bank pays; the administrator records that it was paid and
   the bank's reference. This platform never moves money.
"""

import mimetypes
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mailer, outbox, persistence, storage
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import (
    Applicant,
    Claim,
    ClaimDocument,
    InsurancePolicy,
    NotificationType,
    User,
    UserRole,
)
from app.routers.policies import describe, effective_status, load, notify_staff
from app.schemas.policy import ClaimActionIn, ClaimDocumentSchema, ClaimIn, ClaimSchema

router = APIRouter(tags=["Claims"])

SETTLEMENT_DAYS = 90
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
DOCUMENT_TYPES = {".pdf", ".jpg", ".jpeg", ".png"}
OPEN = ("submitted", "documents_requested", "under_review", "approved")


def _staff(principal: Principal) -> None:
    if principal.role not in (UserRole.UNDERWRITER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Claims are handled by underwriters and administrators.",
        )


# ── checking a claim against its policy ──────────────────────────────────────


def _day(d: date) -> str:
    """The way the screens show a date: Oct 3, 2026."""
    return f"{d:%b} {d.day}, {d.year}"


def checks(
    policy: InsurancePolicy,
    claim_type: str,
    event: date,
    amount: Decimal,
    accident: bool,
    remaining: Decimal | None,
) -> list[str]:
    """What the person deciding should look at. Prompts, not refusals."""
    out: list[str] = []
    stop = policy.cancelled_at.date() if policy.cancelled_at else policy.end_date
    if event < policy.start_date or event >= stop:
        out.append(
            f"The event ({_day(event)}) is outside the cover period "
            f"({_day(policy.start_date)} to {_day(stop)})."
        )
    if policy.product == "health":
        if claim_type != "hospital":
            out.append("Hospital cover pays hospital bills; a death claim is for life cover.")
        if not accident and policy.waiting_until and event < policy.waiting_until:
            out.append(
                f"Illness in the first 30 days is not covered: the waiting period lasts until "
                f"{_day(policy.waiting_until)}. Accidents are covered from day one."
            )
        if policy.preexisting_until and event < policy.preexisting_until:
            out.append(
                "If this is a condition the client had before the policy, it is not covered "
                f"until {_day(policy.preexisting_until)}."
            )
        if remaining is not None and amount > remaining:
            out.append(f"More than is left of this year's limit (৳{remaining:,.0f}).")
    else:
        if claim_type != "death":
            out.append("Term life pays on death; hospital bills are for hospital cover.")
        if amount != Decimal(policy.sum_assured_bdt):
            out.append(
                f"A death claim pays the sum assured, ৳{Decimal(policy.sum_assured_bdt):,.0f}."
            )
    for exclusion in policy.exclusions or []:
        out.append(f"Excluded on this policy: {exclusion}. Check the claim is not for it.")
    return out


async def _schema(db: AsyncSession, rows: list[Claim]) -> list[ClaimSchema]:
    if not rows:
        return []
    policies = {
        p.id: p
        for p in (
            await db.execute(
                select(InsurancePolicy).where(InsurancePolicy.id.in_({r.policy_id for r in rows}))
            )
        ).scalars()
    }
    described = {d.id: d for d in await describe(db, list(policies.values()))}
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
    documents = (
        (
            await db.execute(
                select(ClaimDocument)
                .where(ClaimDocument.claim_id.in_([r.id for r in rows]))
                .order_by(ClaimDocument.created_at)
            )
        )
        .scalars()
        .all()
    )
    today = date.today()
    out = []
    for r in rows:
        policy = policies.get(r.policy_id)
        summary = described.get(r.policy_id)
        applicant = applicants.get(r.applicant_id)
        remaining = summary.remaining_limit_bdt if summary else None
        # This claim's own approval is already counted against the limit.
        if remaining is not None and r.status in ("approved", "settled") and r.approved_amount_bdt:
            remaining += Decimal(r.approved_amount_bdt)
        payable = (
            Decimal(policy.sum_assured_bdt) if policy and policy.product == "life" else remaining
        )
        out.append(
            ClaimSchema(
                id=r.id,
                claim_number=r.claim_number,
                policy_id=r.policy_id,
                policy_number=policy.policy_number if policy else None,
                product=policy.product if policy else None,
                client_id=r.applicant_id,
                client_name=applicant.name if applicant else None,
                client_reference=applicant.external_ref if applicant else None,
                claim_type=r.claim_type,
                event_date=r.event_date,
                claimed_amount_bdt=Decimal(r.claimed_amount_bdt),
                description=r.description,
                hospital=r.hospital,
                claimant_name=r.claimant_name,
                status=r.status,
                documents_note=r.documents_note,
                documents_complete_at=r.documents_complete_at,
                settle_by=r.settle_by,
                days_left=(r.settle_by - today).days if r.settle_by and r.status in OPEN else None,
                approved_amount_bdt=r.approved_amount_bdt,
                decision_note=r.decision_note,
                decided_by_name=names.get(r.decided_by) if r.decided_by else None,
                decided_at=r.decided_at,
                settled_at=r.settled_at,
                settlement_reference=r.settlement_reference,
                filed_by_client=r.filed_by_client,
                created_at=r.created_at,
                checks=checks(
                    policy,
                    r.claim_type,
                    r.event_date,
                    Decimal(r.claimed_amount_bdt),
                    r.accident,
                    remaining,
                )
                if policy
                else [],
                payable_limit_bdt=payable,
                documents=[
                    ClaimDocumentSchema(
                        id=d.id,
                        file_name=d.original_filename,
                        uploaded_by_client=d.uploaded_by_client,
                        created_at=d.created_at,
                    )
                    for d in documents
                    if d.claim_id == r.id
                ],
            )
        )
    return out


# ── filing ───────────────────────────────────────────────────────────────────


async def store_documents(
    db: AsyncSession, claim: Claim, application_id: UUID, files: list[UploadFile], by_client: bool
) -> None:
    for upload in files:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in DOCUMENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{upload.filename}: send a photo or a PDF (JPG, PNG or PDF).",
            )
        raw = await upload.read()
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{upload.filename} is larger than 15 MB.",
            )
        path = storage.write(
            claim.tenant_id, application_id, f"claim-{claim.id}-{secrets.token_hex(6)}{suffix}", raw
        )
        db.add(
            ClaimDocument(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                storage_path=path,
                original_filename=upload.filename,
                mime_type=mimetypes.guess_type(upload.filename)[0],
                uploaded_by_client=by_client,
            )
        )


async def file_claim(
    db: AsyncSession,
    policy: InsurancePolicy,
    payload: ClaimIn,
    files: list[UploadFile],
    by_client: bool,
    filed_by: UUID | None,
) -> Claim:
    """Shared by the portal and the staff endpoint."""
    if policy.status == "cancelled" and (
        not policy.cancelled_at or payload.event_date >= policy.cancelled_at.date()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This policy was cancelled before the date of the claim.",
        )
    if payload.event_date > date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The date cannot be in the future.",
        )
    applicant = await db.get(Applicant, policy.applicant_id)
    count = (
        await db.execute(select(func.count()).where(Claim.policy_id == policy.id))
    ).scalar_one()
    claim = Claim(
        tenant_id=policy.tenant_id,
        policy_id=policy.id,
        applicant_id=policy.applicant_id,
        claim_number=f"C-{applicant.external_ref}-{count + 1}",
        claim_type="hospital" if policy.product == "health" else "death",
        event_date=payload.event_date,
        claimed_amount_bdt=payload.claimed_amount_bdt,
        description=payload.description.strip(),
        hospital=(payload.hospital or "").strip() or None,
        claimant_name=(payload.claimant_name or "").strip() or None,
        accident=payload.accident,
        status="submitted",
        filed_by_client=by_client,
        filed_by=filed_by,
    )
    db.add(claim)
    await db.flush()
    await store_documents(db, claim, policy.application_id, files, by_client)
    await persistence.append_audit(
        db,
        tenant_id=policy.tenant_id,
        application_id=policy.application_id,
        actor_user_id=filed_by,
        event_type="claim_filed",
        payload={
            "claim_number": claim.claim_number,
            "amount": float(claim.claimed_amount_bdt),
            "by": "client" if by_client else "staff",
        },
    )
    await notify_staff(
        db,
        policy.tenant_id,
        policy.application_id,
        NotificationType.CLAIM_FILED,
        f"{applicant.external_ref}: claim {claim.claim_number} filed for "
        f"৳{Decimal(claim.claimed_amount_bdt):,.0f}" + (" by the client." if by_client else "."),
    )
    return claim


def parse_claim(payload: str) -> ClaimIn:
    try:
        return ClaimIn.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The claim could not be read: " + "; ".join(e["msg"] for e in exc.errors()),
        ) from exc


@router.post(
    "/policies/{policy_id}/claims",
    response_model=ClaimSchema,
    status_code=status.HTTP_201_CREATED,
    summary="File a claim on someone's behalf (a death claim from the nominee, say)",
)
async def file_staff_claim(
    policy_id: UUID,
    payload: str = Form(..., description="JSON matching ClaimIn"),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClaimSchema:
    _staff(principal)
    policy = await load(db, policy_id, principal.tenant_id)
    claim = await file_claim(db, policy, parse_claim(payload), files, False, principal.user_id)
    await db.commit()
    return (await _schema(db, [claim]))[0]


# ── reading ──────────────────────────────────────────────────────────────────


@router.get("/claims", response_model=list[ClaimSchema], summary="Claims, newest first")
async def list_claims(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[ClaimSchema]:
    _staff(principal)
    stmt = select(Claim).where(Claim.tenant_id == principal.tenant_id)
    if status_filter == "open":
        stmt = stmt.where(Claim.status.in_(OPEN))
    elif status_filter:
        stmt = stmt.where(Claim.status == status_filter)
    rows = (await db.execute(stmt.order_by(Claim.created_at.desc()).limit(300))).scalars().all()
    return await _schema(db, list(rows))


async def _load_claim(db: AsyncSession, claim_id: UUID, tenant_id: UUID) -> Claim:
    row = (
        await db.execute(select(Claim).where(Claim.id == claim_id, Claim.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such claim.")
    return row


@router.get("/claims/{claim_id}", response_model=ClaimSchema, summary="One claim")
async def get_claim(
    claim_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClaimSchema:
    _staff(principal)
    return (await _schema(db, [await _load_claim(db, claim_id, principal.tenant_id)]))[0]


@router.get("/claims/{claim_id}/documents/{document_id}", summary="One claim document")
async def get_claim_document(
    claim_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> FileResponse:
    _staff(principal)
    claim = await _load_claim(db, claim_id, principal.tenant_id)
    doc = (
        await db.execute(
            select(ClaimDocument).where(
                ClaimDocument.id == document_id, ClaimDocument.claim_id == claim.id
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such document.")
    return FileResponse(
        storage.resolve(doc.storage_path),
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.original_filename,
    )


@router.post(
    "/claims/{claim_id}/documents",
    response_model=ClaimSchema,
    summary="Add documents to a claim",
)
async def add_claim_documents(
    claim_id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClaimSchema:
    _staff(principal)
    claim = await _load_claim(db, claim_id, principal.tenant_id)
    policy = await db.get(InsurancePolicy, claim.policy_id)
    await store_documents(db, claim, policy.application_id, files, False)
    await db.commit()
    return (await _schema(db, [claim]))[0]


# ── deciding ─────────────────────────────────────────────────────────────────


@router.post("/claims/{claim_id}/action", response_model=ClaimSchema, summary="Move a claim on")
async def act_on_claim(
    claim_id: UUID,
    payload: ClaimActionIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClaimSchema:
    _staff(principal)
    claim = await _load_claim(db, claim_id, principal.tenant_id)
    policy = await db.get(InsurancePolicy, claim.policy_id)
    applicant = await db.get(Applicant, claim.applicant_id)
    now = datetime.now(UTC)
    action = payload.action
    note = (payload.note or "").strip() or None

    def refuse(detail: str, code: int = status.HTTP_409_CONFLICT):
        raise HTTPException(status_code=code, detail=detail)

    if claim.status in ("rejected", "settled"):
        refuse(f"This claim is already {claim.status}.")

    if action == "request_documents":
        if claim.status == "approved":
            refuse("This claim is already approved.")
        if not note:
            refuse("Say which documents are needed.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        claim.status = "documents_requested"
        claim.documents_note = note
    elif action == "documents_complete":
        if claim.status == "approved":
            refuse("This claim is already approved.")
        claim.documents_complete_at = claim.documents_complete_at or now
        claim.settle_by = claim.documents_complete_at.date() + timedelta(days=SETTLEMENT_DAYS)
        claim.status = "under_review"
    elif action == "approve":
        if claim.status == "approved":
            refuse("This claim is already approved.")
        [current] = await _schema(db, [claim])
        amount = payload.approved_amount_bdt or Decimal(claim.claimed_amount_bdt)
        if current.payable_limit_bdt is not None and amount > current.payable_limit_bdt:
            refuse(
                f"The policy pays at most ৳{current.payable_limit_bdt:,.0f} on this claim.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        claim.documents_complete_at = claim.documents_complete_at or now
        claim.settle_by = claim.settle_by or (
            claim.documents_complete_at.date() + timedelta(days=SETTLEMENT_DAYS)
        )
        claim.status = "approved"
        claim.approved_amount_bdt = amount
        claim.decision_note = note
        claim.decided_by = principal.user_id
        claim.decided_at = now
    elif action == "reject":
        if claim.status == "approved":
            refuse("This claim is already approved.")
        if not note:
            refuse(
                "Say why the claim is rejected; the client reads it.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        claim.status = "rejected"
        claim.decision_note = note
        claim.decided_by = principal.user_id
        claim.decided_at = now
    elif action == "settle":
        if principal.role != UserRole.ADMIN.value:
            refuse(
                "Only an administrator records that the bank has paid.", status.HTTP_403_FORBIDDEN
            )
        if claim.status != "approved":
            refuse("Only an approved claim can be marked paid.")
        claim.status = "settled"
        claim.settled_at = now
        claim.settlement_reference = (payload.settlement_reference or "").strip() or None

    await persistence.append_audit(
        db,
        tenant_id=claim.tenant_id,
        application_id=policy.application_id,
        actor_user_id=principal.user_id,
        event_type=f"claim_{action}",
        payload={
            "claim_number": claim.claim_number,
            "status": claim.status,
            "amount": float(claim.approved_amount_bdt) if claim.approved_amount_bdt else None,
        },
    )
    await notify_staff(
        db,
        claim.tenant_id,
        policy.application_id,
        NotificationType.CLAIM_UPDATED,
        f"Claim {claim.claim_number}: {claim.status.replace('_', ' ')}.",
    )
    await db.commit()
    if applicant and applicant.email and action != "documents_complete":
        background.add_task(
            outbox.send_logged,
            claim.tenant_id,
            policy.application_id,
            "claim_update",
            applicant.email,
            f"An update about your policy ({applicant.external_ref})",
            mailer.send_policy_notice,
            applicant.email,
            applicant.name or "",
            applicant.external_ref,
        )
    return (await _schema(db, [claim]))[0]


async def claims_for_policy(db: AsyncSession, policy_id: UUID) -> list[ClaimSchema]:
    rows = (
        (
            await db.execute(
                select(Claim).where(Claim.policy_id == policy_id).order_by(Claim.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return await _schema(db, list(rows))


def can_claim(policy: InsurancePolicy) -> bool:
    return effective_status(policy, date.today()) == "active"
