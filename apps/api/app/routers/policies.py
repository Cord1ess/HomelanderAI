"""Policies: issued when an application is approved, cancelled only by the owner.

**Dates, all derived from the day of the decision:**

* *Start*: the day the application is approved. Cover runs from then.
* *Free look*: 15 days from the start, in which the client may cancel for a
  full refund.
* *End*: life cover, the start plus the term in years; hospital cover, one
  year (it is renewed each year, at the client's new age).
* *Waiting periods*, hospital cover only: illness from 30 days after the
  start (accidents from day one), conditions the client already had from 24
  months after.
* *Premiums* fall due on the start date and every month (or year) after it,
  until the end. They are collected by the bank; this platform shows when they
  fall due, never whether they were paid.

A claim is checked against these dates (routers/claims.py).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mailer, outbox, persistence, pricing
from app import policies as rules
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import (
    Applicant,
    Application,
    Claim,
    InsurancePolicy,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    UnderwriterDecision,
    User,
    UserRole,
)
from app.schemas.policy import CancelIn, PolicySchema

router = APIRouter(tags=["Policies"])

PRODUCT_NAME = {"life": "Term life", "health": "Hospital cover"}
# Hospital cover nearing its yearly renewal: shown this many days before the end.
RENEWAL_NOTICE_DAYS = 30
OPEN_CLAIMS = ("submitted", "documents_requested", "under_review", "approved")


def plan_name(product: str, rating_pct: int, exclusions: list[str]) -> str:
    terms = "standard rates" if not rating_pct else f"rated +{rating_pct}%"
    if exclusions:
        terms += f", {len(exclusions)} exclusion{'s' if len(exclusions) != 1 else ''}"
    return f"{PRODUCT_NAME.get(product, product)}, {terms}"


# ── issuing ──────────────────────────────────────────────────────────────────


async def issue_policy(
    db: AsyncSession,
    application: Application,
    applicant: Applicant,
    decision: UnderwriterDecision,
    priced: pricing.Quote,
) -> InsurancePolicy:
    """The policy an approval issues, added to the caller's session."""
    product = priced.product
    start = date.today()
    row = InsurancePolicy(
        tenant_id=application.tenant_id,
        application_id=application.id,
        applicant_id=applicant.id,
        policy_number=f"P-{applicant.external_ref}",
        plan_name=plan_name(product, decision.rating_pct, list(decision.exclusions or [])),
        coverage_type=application.coverage_type,
        product=product,
        sum_assured_bdt=application.coverage_amount,
        annual_premium_bdt=Decimal(str(priced.annual_bdt)),
        monthly_premium_bdt=Decimal(str(priced.monthly_bdt)),
        premium_mode=application.payment_mode or "monthly",
        rating_pct=decision.rating_pct or 0,
        exclusions=list(decision.exclusions or []),
        term_years=priced.term_years,
        start_date=start,
        end_date=rules.end_date(start, priced.term_years),
        free_look_until=start + timedelta(days=pricing.FREE_LOOK_DAYS),
        waiting_until=(
            start + timedelta(days=pricing.HEALTH_ILLNESS_WAIT_DAYS)
            if product == "health"
            else None
        ),
        preexisting_until=(
            rules.add_months(start, pricing.HEALTH_PREEXISTING_WAIT_MONTHS)
            if product == "health"
            else None
        ),
        status="active",
    )
    db.add(row)
    return row


# ── reading ──────────────────────────────────────────────────────────────────


def next_due(row: InsurancePolicy, today: date) -> date | None:
    """The next day a premium falls due, from today, while the policy runs."""
    step = 12 if row.premium_mode == "yearly" else 1
    n = 0
    while True:
        due = rules.add_months(row.start_date, n * step)
        if due >= row.end_date:
            return None
        if due >= today:
            return due
        n += 1


def effective_status(row: InsurancePolicy, today: date) -> str:
    if row.status == "cancelled":
        return "cancelled"
    return "expired" if today >= row.end_date else "active"


async def describe(db: AsyncSession, rows: list[InsurancePolicy]) -> list[PolicySchema]:
    """Each policy with its dates worked out as of today, and its claims."""
    if not rows:
        return []
    ids = [r.id for r in rows]
    claims = (await db.execute(select(Claim).where(Claim.policy_id.in_(ids)))).scalars().all()
    applicants = {
        a.id: a
        for a in (
            await db.execute(
                select(Applicant).where(Applicant.id.in_({r.applicant_id for r in rows}))
            )
        ).scalars()
    }
    cancellers = {r.cancelled_by for r in rows if r.cancelled_by}
    names = (
        {
            u.id: u.full_name
            for u in (await db.execute(select(User).where(User.id.in_(cancellers)))).scalars()
        }
        if cancellers
        else {}
    )

    today = date.today()
    zero = Decimal(0)
    out: list[PolicySchema] = []
    for r in rows:
        mine = [c for c in claims if c.policy_id == r.id]
        state = effective_status(r, today)
        annual = Decimal(r.annual_premium_bdt or (r.monthly_premium_bdt * 12))
        monthly = Decimal(r.monthly_premium_bdt)
        yearly = r.premium_mode == "yearly"
        # Hospital cover: approved claims count against the year's limit.
        used = sum(
            (
                Decimal(c.approved_amount_bdt or 0)
                for c in mine
                if c.status in ("approved", "settled")
            ),
            zero,
        )
        applicant = applicants.get(r.applicant_id)
        out.append(
            PolicySchema(
                id=r.id,
                policy_number=r.policy_number,
                application_id=r.application_id,
                client_id=r.applicant_id,
                client_reference=applicant.external_ref if applicant else None,
                client_name=applicant.name if applicant else None,
                product=r.product,
                product_name=PRODUCT_NAME.get(r.product, r.product),
                plan_name=r.plan_name,
                coverage_type=r.coverage_type,
                sum_assured_bdt=Decimal(r.sum_assured_bdt),
                annual_premium_bdt=annual,
                monthly_premium_bdt=monthly,
                premium_mode=r.premium_mode,
                premium_amount_bdt=annual if yearly else monthly,
                total_premium_bdt=(annual if yearly else monthly * 12) * r.term_years,
                rating_pct=r.rating_pct or 0,
                exclusions=list(r.exclusions or []),
                term_years=r.term_years,
                start_date=r.start_date,
                end_date=r.end_date,
                status=r.status,
                effective_status=state,
                cancelled_at=r.cancelled_at,
                cancel_reason=r.cancel_reason,
                cancelled_by_name=names.get(r.cancelled_by) if r.cancelled_by else None,
                free_look_until=r.free_look_until,
                in_free_look=state == "active"
                and r.free_look_until is not None
                and today <= r.free_look_until,
                waiting_until=r.waiting_until,
                preexisting_until=r.preexisting_until,
                next_premium_due=next_due(r, today) if state == "active" else None,
                renewal_due=r.product == "health"
                and state == "active"
                and (r.end_date - today).days <= RENEWAL_NOTICE_DAYS,
                days_to_end=(r.end_date - today).days if state == "active" else None,
                claims_open=sum(1 for c in mine if c.status in OPEN_CLAIMS),
                claims_paid_bdt=sum(
                    (Decimal(c.approved_amount_bdt or 0) for c in mine if c.status == "settled"),
                    zero,
                ),
                remaining_limit_bdt=(
                    max(zero, Decimal(r.sum_assured_bdt) - used) if r.product == "health" else None
                ),
            )
        )
    return out


def _owner_only(principal: Principal, what: str) -> None:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only the company owner (an administrator) can {what}.",
        )


async def load(db: AsyncSession, policy_id: UUID, tenant_id: UUID) -> InsurancePolicy:
    row = (
        await db.execute(
            select(InsurancePolicy).where(
                InsurancePolicy.id == policy_id, InsurancePolicy.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such policy.")
    return row


@router.get("/policies", response_model=list[PolicySchema], summary="Every policy (owner only)")
async def list_policies(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[PolicySchema]:
    _owner_only(principal, "see every policy")
    rows = (
        (
            await db.execute(
                select(InsurancePolicy)
                .where(InsurancePolicy.tenant_id == principal.tenant_id)
                .order_by(InsurancePolicy.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return await describe(db, list(rows))


@router.get("/policies/{policy_id}", response_model=PolicySchema, summary="One policy")
async def get_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> PolicySchema:
    if principal.role == UserRole.MEDICAL_PROFESSIONAL.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Policies are not a doctor's."
        )
    return (await describe(db, [await load(db, policy_id, principal.tenant_id)]))[0]


async def notify_staff(
    db: AsyncSession,
    tenant_id: UUID,
    application_id: UUID | None,
    kind: NotificationType,
    message: str,
) -> None:
    """Underwriters and administrators: policies and claims are theirs."""
    users = (
        (
            await db.execute(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.is_active.is_(True),
                    User.role.in_([UserRole.UNDERWRITER, UserRole.ADMIN]),
                )
            )
        )
        .scalars()
        .all()
    )
    for user_id in users:
        db.add(
            Notification(
                tenant_id=tenant_id,
                user_id=user_id,
                application_id=application_id,
                notification_type=kind,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=message,
            )
        )


async def cancel(
    db: AsyncSession,
    row: InsurancePolicy,
    reason: str,
    actor: UUID | None,
    background: BackgroundTasks | None,
) -> None:
    """Cancel a policy, record it, tell the staff and the client."""
    row.status = "cancelled"
    row.cancelled_at = datetime.now(UTC)
    row.cancelled_by = actor
    row.cancel_reason = reason
    applicant = await db.get(Applicant, row.applicant_id)
    await persistence.append_audit(
        db,
        tenant_id=row.tenant_id,
        application_id=row.application_id,
        actor_user_id=actor,
        event_type="policy_cancelled",
        payload={"policy_number": row.policy_number, "reason": reason},
    )
    await notify_staff(
        db,
        row.tenant_id,
        row.application_id,
        NotificationType.POLICY_CANCELLED,
        f"Policy {row.policy_number} was cancelled. Reason: {reason}",
    )
    if background is not None and applicant and applicant.email:
        background.add_task(
            outbox.send_logged,
            row.tenant_id,
            row.application_id,
            "policy_update",
            applicant.email,
            f"An update about your policy ({applicant.external_ref})",
            mailer.send_policy_notice,
            applicant.email,
            applicant.name or "",
            applicant.external_ref,
        )


@router.post(
    "/policies/{policy_id}/cancel",
    response_model=PolicySchema,
    summary="Cancel an approved policy (owner only)",
)
async def cancel_policy(
    policy_id: UUID,
    payload: CancelIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> PolicySchema:
    _owner_only(principal, "cancel a policy")
    row = await load(db, policy_id, principal.tenant_id)
    if row.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This policy is already cancelled."
        )
    await cancel(db, row, payload.reason.strip(), principal.user_id, background)
    await db.commit()
    await db.refresh(row)
    return (await describe(db, [row]))[0]
