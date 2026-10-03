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

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import persistence, plans, turnaround
from app.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.deps import PORTAL_COOKIE_NAME, PortalPrincipal, current_applicant
from app.evidence import label as kind_label
from app.models import (
    Applicant,
    Application,
    ClientMessage,
    EvidenceFile,
    InsurancePolicy,
    NotificationType,
    RequestedDocument,
    Tenant,
    UnderwriterDecision,
    UnderwriterDecisionType,
)
from app.schemas.portal import (
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
    UnderwriterDecisionType.CONFIRMED_FAST_TRACK: ("Approved at the standard rate", "low"),
    UnderwriterDecisionType.APPROVED_WITH_ADJUSTMENT: (
        "Approved with an adjusted premium",
        "moderate",
    ),
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
        outcome, plan_key = _OUTCOMES[decision.decision]
        # The premium the underwriter recorded wins. An adjusted approval always
        # has one (the decision endpoint requires it); a fast-track usually does
        # not, and means the standard rate for the cover that was asked for.
        premium = decision.final_premium
        if premium is None:
            tenant = await db.get(Tenant, applicant.tenant_id)
            policy = plans.Policy.from_tenant(tenant) if tenant else plans.DEFAULT_POLICY
            premium = plans.monthly_premium(
                plan_key,
                float(application.coverage_amount) if application.coverage_amount else None,
                policy,
            )
        offer = PortalOfferSchema(
            outcome=outcome,
            plan_name=plans.PLANS[plan_key].name,
            monthly_premium_bdt=premium,
            decided_at=decision.decided_at,
        )

    from app.routers.policies import describe

    issued = (
        await db.execute(
            select(InsurancePolicy).where(InsurancePolicy.application_id == application.id)
        )
    ).scalar_one_or_none()

    return PortalStatusSchema(
        policy=(await describe(db, [issued]))[0] if issued else None,
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
