"""The client portal: an applicant reading their own application.

Deliberately narrow. It answers the questions an applicant actually has:
where is my application, when will I hear, do you need anything from me (and
a way to upload it), and has a doctor written to me. Once a person has
decided, it shows the outcome. The one thing an applicant can change is
adding a document they were asked for.

It never shows a risk score or a model finding; see `schemas/portal.py` for why
that is structural rather than a filter.

**Isolation.** There is no application id in any URL here. Every query is pinned
to the applicant id inside the signed token, so there is nothing to tamper with:
one applicant cannot ask for another's application because the API gives them no
way to name one.
"""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import decline as decline_rules
from app import persistence, turnaround
from app.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.deps import PORTAL_COOKIE_NAME, PortalPrincipal, current_applicant
from app.evidence import label as kind_label
from app.models import (
    Applicant,
    Application,
    Claim,
    ClaimDocument,
    ClientMessage,
    EvidenceFile,
    InsurancePolicy,
    NotificationType,
    RequestedDocument,
    UnderwriterDecision,
    UnderwriterDecisionType,
)
from app.routers import deletion
from app.schemas.auth import BaseSchema
from app.schemas.portal import (
    PortalClaimSchema,
    PortalDeclineSchema,
    PortalDeletionSchema,
    PortalDocumentSchema,
    PortalFileSchema,
    PortalLoginIn,
    PortalMessageSchema,
    PortalOfferSchema,
    PortalStatusSchema,
)

router = APIRouter(prefix="/portal", tags=["Client portal"])

log = logging.getLogger(__name__)

# What each recorded decision means to the person it is about: the words, and
# the plan that decision puts them on.
#
# **The plan comes from the underwriter's decision, never from the model's
# tier.** Plans map one-to-one to tiers, so a plan looked up from the tier is the
# risk score under another name, and it can contradict the decision: fast-track a
# case the model called moderate and the applicant would read "approved at the
# standard rate" beside "Standard with adjustment". This module therefore does
# not read the scores table at all, and a test holds it to that.
_OUTCOMES = {
    UnderwriterDecisionType.CONFIRMED_FAST_TRACK: "Approved at the standard rate",
    UnderwriterDecisionType.APPROVED_WITH_ADJUSTMENT: "Approved, with adjusted terms",
}


def _stage(status_value: str, decision: UnderwriterDecisionType | None) -> tuple[str, str, str]:
    """(code, label, detail) for the applicant. Plain words, no internals."""
    if status_value == "awaiting_evidence":
        return (
            "waiting_on_you",
            "We need something from you",
            "Please upload the documents listed below. "
            "We will carry on as soon as we have them.",
        )
    # An escalated application, or one decided as "escalated" before escalation
    # stopped being a decision (2026-09-22).
    if status_value == "escalated" or (
        status_value == "decided" and decision == UnderwriterDecisionType.ESCALATED_SENIOR_REVIEW
    ):
        return (
            "senior_review",
            "Taking a closer look",
            # Deliberately not "a doctor", which is who it is. Naming a
            # medical reviewer would imply a finding; a doctor who needs to
            # tell the applicant something writes to them directly.
            "Someone from our team is taking a closer look at your application. "
            "This is normal. It does not mean you have been refused.",
        )
    if status_value == "decided" and decision == UnderwriterDecisionType.DECLINED:
        return (
            "decided",
            "Decision made",
            "We are not able to offer you cover. The reason is below.",
        )
    if status_value == "decided":
        return ("decided", "Decision made", "We have made a decision. You can see it on this page.")
    if status_value in ("submitted", "processing"):
        return (
            "being_assessed",
            "Checking your tests",
            "We have your application and are looking at your test results.",
        )
    return (
        "with_underwriter",
        "Making a decision",
        "Your tests have been checked. Someone from our team will now decide on your cover.",
    )


@router.post("/login", response_model=PortalStatusSchema, summary="Applicant sign-in")
async def portal_login(
    payload: PortalLoginIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> PortalStatusSchema:
    try:
        applicant = (
            await db.execute(
                select(Applicant).where(Applicant.portal_id == payload.portal_id.strip().upper())
            )
        ).scalar_one_or_none()
    except (SQLAlchemyError, OSError) as exc:
        log.error("Database unreachable during portal sign-in: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The portal is temporarily unavailable. Please try again shortly.",
        ) from exc

    # One message for a wrong id and a wrong password, so the response does not
    # confirm which portal ids exist.
    if (
        applicant is None
        or not applicant.password_hash
        or not verify_password(payload.password, applicant.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That portal ID and password do not match.",
        )

    token = create_access_token(
        subject=str(applicant.id),
        tenant_id=str(applicant.tenant_id),
        role="applicant",
        kind="portal",
    )
    response.set_cookie(
        key=PORTAL_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.access_token_ttl_minutes * 60,
        samesite="lax",
        secure=not settings.is_development,
    )
    return await _status_for(db, applicant)


@router.get("/me", response_model=PortalStatusSchema, summary="The applicant's own application")
async def portal_me(
    db: AsyncSession = Depends(get_db),
    principal: PortalPrincipal = Depends(current_applicant),
) -> PortalStatusSchema:
    applicant = await db.get(Applicant, principal.applicant_id)
    if applicant is None or applicant.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your portal session is not valid. Sign in again.",
        )
    return await _status_for(db, applicant)


@router.post(
    "/documents/{document_id}/upload",
    response_model=PortalStatusSchema,
    summary="The applicant uploads a document they were asked for",
)
async def portal_upload(
    document_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    principal: PortalPrincipal = Depends(current_applicant),
) -> PortalStatusSchema:
    """Answer one request with a file. It is stored with the application like
    any other evidence, linked to the request, and the staff are told. Once
    nothing is outstanding the application goes back to the underwriter."""
    # Imported here: the applications router imports a great deal, and the
    # portal needs only these three pieces of it.
    from app.routers.applications import _notify_tenant, _store_evidence, settle_after_receipt

    applicant = await db.get(Applicant, principal.applicant_id)
    if applicant is None or applicant.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your portal session is not valid. Sign in again.",
        )
    # The request must be on this applicant's own application: the join is the
    # whole of the check, so another applicant's request id finds nothing.
    found = (
        await db.execute(
            select(RequestedDocument, Application)
            .join(Application, Application.id == RequestedDocument.application_id)
            .where(
                RequestedDocument.id == document_id,
                Application.applicant_id == applicant.id,
            )
        )
    ).first()
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="We could not find that request."
        )
    row, application = found
    if row.fulfilled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="We already have this document. Thank you.",
        )

    created: list[EvidenceFile] = []
    _, rejected = await _store_evidence(
        db,
        SimpleNamespace(tenant_id=applicant.tenant_id),
        application,
        [file],
        [""],
        ["document"],
        created,
    )
    if rejected or not created:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "We could not read that file. Please send a photo, a scan or a PDF "
                "(JPG, PNG or PDF)."
            ),
        )
    await db.flush()
    row.fulfilled_at = datetime.now(UTC)
    row.fulfilled_by = created[0].id
    await persistence.append_audit(
        db,
        tenant_id=applicant.tenant_id,
        application_id=application.id,
        actor_user_id=None,
        event_type="evidence_received",
        payload={
            "document_id": str(row.id),
            "description": row.description,
            "by": "client",
            "file": file.filename,
        },
    )
    await settle_after_receipt(db, application)
    await _notify_tenant(
        db,
        application,
        NotificationType.DOCUMENTS_UPLOADED,
        f"{applicant.external_ref}: the client uploaded \u201c{row.description}\u201d.",
    )
    await db.commit()
    return await _status_for(db, applicant)


async def _me(db: AsyncSession, principal: PortalPrincipal) -> Applicant:
    applicant = await db.get(Applicant, principal.applicant_id)
    if applicant is None or applicant.tenant_id != principal.tenant_id or applicant.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your portal session is not valid. Sign in again.",
        )
    return applicant


async def _my_policy(db: AsyncSession, applicant: Applicant) -> InsurancePolicy:
    policy = (
        await db.execute(
            select(InsurancePolicy)
            .where(InsurancePolicy.applicant_id == applicant.id)
            .order_by(InsurancePolicy.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="You do not have a policy to claim on."
        )
    return policy


@router.post(
    "/claims",
    response_model=PortalStatusSchema,
    summary="The client files a claim for hospital bills",
)
async def portal_claim(
    payload: str = Form(..., description="JSON matching ClaimIn"),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    principal: PortalPrincipal = Depends(current_applicant),
) -> PortalStatusSchema:
    """Hospital cover only. A death claim is made by the nominee at the office,
    with the death certificate; staff enter it."""
    from app.routers.claims import file_claim, parse_claim

    applicant = await _me(db, principal)
    policy = await _my_policy(db, applicant)
    if policy.product != "health":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A claim on life cover is made by your nominee at the office.",
        )
    if not [f for f in files if f.filename]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add the hospital bill and the discharge summary.",
        )
    await file_claim(db, policy, parse_claim(payload), files, True, None)
    await db.commit()
    return await _status_for(db, applicant)


@router.post(
    "/claims/{claim_id}/documents",
    response_model=PortalStatusSchema,
    summary="The client adds documents to their claim",
)
async def portal_claim_documents(
    claim_id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    principal: PortalPrincipal = Depends(current_applicant),
) -> PortalStatusSchema:
    from app.routers.claims import store_documents

    applicant = await _me(db, principal)
    claim = (
        await db.execute(
            select(Claim).where(Claim.id == claim_id, Claim.applicant_id == applicant.id)
        )
    ).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such claim.")
    if claim.status not in ("submitted", "documents_requested", "under_review"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This claim has already been decided."
        )
    policy = await db.get(InsurancePolicy, claim.policy_id)
    await store_documents(db, claim, policy.application_id, files, True)
    if claim.status == "documents_requested":
        claim.status = "submitted"
    await db.commit()
    return await _status_for(db, applicant)


class DeletionIn(BaseSchema):
    reason: str | None = Field(default=None, max_length=1000)


@router.post(
    "/deletion-request",
    response_model=PortalStatusSchema,
    summary="The client asks for their data to be deleted",
)
async def portal_request_deletion(
    payload: DeletionIn,
    db: AsyncSession = Depends(get_db),
    principal: PortalPrincipal = Depends(current_applicant),
) -> PortalStatusSchema:
    applicant = await _me(db, principal)
    await deletion.request(db, applicant, payload.reason)
    await db.commit()
    return await _status_for(db, applicant)


@router.delete(
    "/deletion-request",
    response_model=PortalStatusSchema,
    summary="The client withdraws their request",
)
async def portal_withdraw_deletion(
    db: AsyncSession = Depends(get_db),
    principal: PortalPrincipal = Depends(current_applicant),
) -> PortalStatusSchema:
    applicant = await _me(db, principal)
    asked = await deletion.latest_for(db, applicant.id)
    if asked is None or asked.status not in ("pending", "approved"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="There is nothing to withdraw."
        )
    asked.status = "withdrawn"
    await db.commit()
    return await _status_for(db, applicant)


@router.post("/logout", summary="Applicant sign-out")
async def portal_logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=PORTAL_COOKIE_NAME)
    return {"status": "ok"}


async def _status_for(db: AsyncSession, applicant: Applicant) -> PortalStatusSchema:
    """Everything the portal shows, for this applicant's latest application."""
    application = (
        await db.execute(
            select(Application)
            .where(Application.applicant_id == applicant.id)
            .order_by(Application.submitted_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="We could not find an application for this sign-in.",
        )

    decision = (
        await db.execute(
            select(UnderwriterDecision).where(
                UnderwriterDecision.application_id == application.id
            )
        )
    ).scalar_one_or_none()

    documents = (
        await db.execute(
            select(RequestedDocument)
            .where(RequestedDocument.application_id == application.id)
            .order_by(RequestedDocument.requested_at)
        )
    ).scalars().all()

    files = (
        await db.execute(
            select(EvidenceFile)
            .where(EvidenceFile.application_id == application.id)
            .order_by(EvidenceFile.uploaded_at)
        )
    ).scalars().all()
    file_names = {f.id: f.original_filename for f in files}

    messages = (
        await db.execute(
            select(ClientMessage)
            .where(ClientMessage.application_id == application.id)
            .order_by(ClientMessage.created_at.desc())
        )
    ).scalars().all()

    code, label, detail = _stage(application.status.value, decision.decision if decision else None)

    offer = None
    if decision is not None and decision.decision in _OUTCOMES:
        offer = PortalOfferSchema(
            outcome=_OUTCOMES[decision.decision],
            plan_name=None,
            monthly_premium_bdt=decision.final_premium,
            decided_at=decision.decided_at,
        )
    declined = None
    if decision is not None and decision.decision == UnderwriterDecisionType.DECLINED:
        declined = PortalDeclineSchema(
            reason=decline_rules.client_text(decision.decline_reason)
            or "We are not able to offer you cover at this time.",
            note=decision.decline_note,
            reapply_after=decision.reapply_after,
            decided_at=decision.decided_at,
        )

    from app.routers.policies import describe

    issued = (
        await db.execute(
            select(InsurancePolicy).where(InsurancePolicy.application_id == application.id)
        )
    ).scalar_one_or_none()

    claims = (
        (
            await db.execute(
                select(Claim).where(Claim.policy_id == issued.id).order_by(Claim.created_at.desc())
            )
        ).scalars().all()
        if issued
        else []
    )
    doc_counts = dict(
        (
            await db.execute(
                select(ClaimDocument.claim_id, func.count())
                .where(ClaimDocument.claim_id.in_([c.id for c in claims]))
                .group_by(ClaimDocument.claim_id)
            )
        ).all()
    ) if claims else {}
    asked = await deletion.latest_for(db, applicant.id)

    return PortalStatusSchema(
        policy=(await describe(db, [issued]))[0] if issued else None,
        declined=declined,
        nominee_name=applicant.nominee_name,
        claims=[
            PortalClaimSchema(
                id=c.id,
                claim_number=c.claim_number,
                event_date=c.event_date,
                claimed_amount_bdt=c.claimed_amount_bdt,
                description=c.description,
                hospital=c.hospital,
                status=c.status,
                documents_note=c.documents_note if c.status == "documents_requested" else None,
                approved_amount_bdt=c.approved_amount_bdt,
                decision_note=c.decision_note,
                settle_by=c.settle_by,
                settled_at=c.settled_at,
                documents=doc_counts.get(c.id, 0),
                created_at=c.created_at,
            )
            for c in claims
        ],
        deletion=(
            PortalDeletionSchema(
                status=asked.status,
                requested_at=asked.requested_at,
                delete_on=asked.delete_on,
                decline_reason=asked.decline_reason,
            )
            if asked
            else None
        ),
        reference=applicant.external_ref,
        applicant_name=applicant.name,
        coverage_type=application.coverage_type,
        coverage_amount=application.coverage_amount,
        policy_term=application.policy_term,
        submitted_at=application.submitted_at,
        stage=code,
        stage_label=label,
        stage_detail=detail,
        expected_by=application.expected_by,
        expected_by_note=application.expected_by_note,
        overdue=turnaround.is_overdue(application.expected_by, application.status.value),
        documents=[
            PortalDocumentSchema(
                id=d.id,
                description=d.description,
                requested_at=d.requested_at,
                received=d.fulfilled_at is not None,
                received_at=d.fulfilled_at,
                file_name=file_names.get(d.fulfilled_by) if d.fulfilled_by else None,
            )
            for d in documents
        ],
        files=[
            PortalFileSchema(
                kind=kind_label(f.evidence_kind) if f.evidence_kind else "Document",
                file_name=f.original_filename,
                uploaded_at=f.uploaded_at,
            )
            for f in files
        ],
        messages=[
            PortalMessageSchema(urgency=m.urgency, message=m.message, sent_at=m.created_at)
            for m in messages
        ],
        offer=offer,
    )
