"""The client portal: an applicant reading their own application.

Read-only, and deliberately narrow. It answers three questions an applicant
actually has: where is my application, when will I hear, and do you need
anything from me. Once a person has decided, it shows the outcome.

It never shows a risk score or a model finding; see `schemas/portal.py` for why
that is structural rather than a filter.

**Isolation.** There is no application id in any URL here. Every query is pinned
to the applicant id inside the signed token, so there is nothing to tamper with:
one applicant cannot ask for another's application because the API gives them no
way to name one.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans, turnaround
from app.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.deps import PORTAL_COOKIE_NAME, PortalPrincipal, current_applicant
from app.models import (
    Applicant,
    Application,
    RequestedDocument,
    UnderwriterDecision,
    UnderwriterDecisionType,
)
from app.schemas.portal import (
    PortalDocumentSchema,
    PortalLoginIn,
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
            "Your underwriter has asked for the documents listed below. "
            "Your application continues as soon as they arrive.",
        )
    if status_value == "decided":
        if decision == UnderwriterDecisionType.ESCALATED_SENIOR_REVIEW:
            return (
                "senior_review",
                "With a senior underwriter",
                "Your application has been passed to a senior underwriter for a closer look. "
                "This is a normal step and is not a refusal.",
            )
        return ("decided", "Decided", "A decision has been recorded on your application.")
    if status_value in ("submitted", "processing"):
        return (
            "being_assessed",
            "Being assessed",
            "We have your application and documents and are working through them.",
        )
    return (
        "with_underwriter",
        "With an underwriter",
        "Your application is waiting for an underwriter to review it and decide.",
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

    code, label, detail = _stage(application.status.value, decision.decision if decision else None)

    offer = None
    if decision is not None and decision.decision in _OUTCOMES:
        outcome, plan_key = _OUTCOMES[decision.decision]
        # The premium the underwriter recorded wins. An adjusted approval always
        # has one (the decision endpoint requires it); a fast-track usually does
        # not, and means the standard rate for the cover that was asked for.
        premium = decision.final_premium
        if premium is None:
            premium = plans.monthly_premium(
                plan_key,
                float(application.coverage_amount) if application.coverage_amount else None,
            )
        offer = PortalOfferSchema(
            outcome=outcome,
            plan_name=plans.PLANS[plan_key].name,
            monthly_premium_bdt=premium,
            decided_at=decision.decided_at,
        )

    return PortalStatusSchema(
        reference=applicant.external_ref,
        applicant_name=applicant.name,
        coverage_type=application.coverage_type,
        coverage_amount=application.coverage_amount,
        submitted_at=application.submitted_at,
        stage=code,
        stage_label=label,
        stage_detail=detail,
        expected_by=application.expected_by,
        expected_by_note=application.expected_by_note,
        overdue=turnaround.is_overdue(application.expected_by, application.status.value),
        documents=[
            PortalDocumentSchema(
                description=d.description,
                requested_at=d.requested_at,
                received=d.fulfilled_at is not None,
            )
            for d in documents
        ],
        offer=offer,
    )
