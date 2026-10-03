"""Policies: issued when an application is approved, cancelled only by the owner.

An approval used to be the end of the line. It now issues a policy the client
can see on their portal: the plan, what they pay each month, what is paid out
on a claim (the sum assured), and for how long. Each month's premium is
recorded as it is paid, so both sides can see what has been paid and what is
due (`app/policies.py` works the schedule out).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mailer, outbox, persistence, plans
from app import policies as rules
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import (
    Applicant,
    Application,
    InsurancePolicy,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    PremiumPayment,
    Tenant,
    UnderwriterDecision,
    User,
    UserRole,
)
from app.schemas.policy import CancelIn, InstallmentSchema, PaymentIn, PolicySchema

router = APIRouter(tags=["Policies"])

# ── issuing ──────────────────────────────────────────────────────────────────


async def issue_policy(
    db: AsyncSession,
    application: Application,
    applicant: Applicant,
    decision: UnderwriterDecision,
) -> InsurancePolicy | None:
    """The policy an approval issues, added to the caller's session.

    None for a decision that approves nothing, or an application with no cover
    amount to insure (there is nothing to pay out).
    """
    plan_name = rules.PLAN_FOR_DECISION.get(decision.decision.value)
    if plan_name is None or not application.coverage_amount:
        return None

    premium = decision.final_premium
    if premium is None:
        tenant = await db.get(Tenant, application.tenant_id)
        policy = plans.Policy.from_tenant(tenant) if tenant else plans.DEFAULT_POLICY
        computed = plans.monthly_premium("low", float(application.coverage_amount), policy)
        premium = Decimal(str(computed)) if computed is not None else None
    if premium is None:
        return None

    years = rules.term_years(application.policy_term)
    start = (decision.decided_at or datetime.now(UTC)).date()
    row = InsurancePolicy(
        tenant_id=application.tenant_id,
        application_id=application.id,
        applicant_id=applicant.id,
        policy_number=f"P-{applicant.external_ref}",
        plan_name=plan_name,
        coverage_type=application.coverage_type,
        sum_assured_bdt=application.coverage_amount,
        monthly_premium_bdt=Decimal(premium),
        term_years=years,
        start_date=start,
        end_date=rules.end_date(start, years),
        status="active",
    )
    db.add(row)
    return row


# ── reading ──────────────────────────────────────────────────────────────────


async def describe(
    db: AsyncSession, rows: list[InsurancePolicy], *, with_installments: bool = True
) -> list[PolicySchema]:
    """Each policy with its payment schedule and totals, as of today."""
    if not rows:
        return []
    ids = [r.id for r in rows]
    payments = (
        (await db.execute(select(PremiumPayment).where(PremiumPayment.policy_id.in_(ids))))
        .scalars()
        .all()
    )
    paid: dict[UUID, dict[date, tuple[date, str]]] = {}
    for p in payments:
        paid.setdefault(p.policy_id, {})[p.due_date] = (p.paid_at.date(), p.method)

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
    out: list[PolicySchema] = []
    for r in rows:
        installments = rules.schedule(
            r.start_date,
            r.end_date,
            Decimal(r.monthly_premium_bdt),
            paid.get(r.id, {}),
            today,
            cancelled_on=r.cancelled_at.date() if r.cancelled_at else None,
        )
        summary = rules.summarise(installments, r.term_years)
        applicant = applicants.get(r.applicant_id)
        monthly = Decimal(r.monthly_premium_bdt)
        out.append(
            PolicySchema(
                id=r.id,
                policy_number=r.policy_number,
                application_id=r.application_id,
                client_id=r.applicant_id,
                client_reference=applicant.external_ref if applicant else None,
                client_name=applicant.name if applicant else None,
                plan_name=r.plan_name,
                coverage_type=r.coverage_type,
                sum_assured_bdt=Decimal(r.sum_assured_bdt),
                monthly_premium_bdt=monthly,
                yearly_premium_bdt=monthly * 12,
                total_premium_bdt=monthly * 12 * r.term_years,
                term_years=r.term_years,
                start_date=r.start_date,
                end_date=r.end_date,
                status=r.status,
                cancelled_at=r.cancelled_at,
                cancel_reason=r.cancel_reason,
                cancelled_by_name=names.get(r.cancelled_by) if r.cancelled_by else None,
                paid_count=summary.paid_count,
                paid_total_bdt=summary.paid_total,
                overdue_count=summary.overdue_count if r.status == "active" else 0,
                overdue_total_bdt=summary.overdue_total if r.status == "active" else Decimal(0),
                next_due=summary.next_due if r.status == "active" else None,
                next_amount_bdt=summary.next_amount if r.status == "active" else None,
                months_total=summary.months_total,
                installments=[
                    InstallmentSchema(
                        number=i.number,
                        due_date=i.due_date,
                        amount_bdt=i.amount,
                        status=i.status,
                        paid_on=i.paid_on,
                        method=i.method,
                    )
                    for i in installments
                ]
                if with_installments
                else [],
            )
        )
    return out


def _owner_only(principal: Principal, what: str) -> None:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only the company owner (an administrator) can {what}.",
        )


async def _load(db: AsyncSession, policy_id: UUID, principal: Principal) -> InsurancePolicy:
    row = (
        await db.execute(
            select(InsurancePolicy).where(
                InsurancePolicy.id == policy_id, InsurancePolicy.tenant_id == principal.tenant_id
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
    return await describe(db, list(rows), with_installments=False)


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
    return (await describe(db, [await _load(db, policy_id, principal)]))[0]


async def _notify_staff(db: AsyncSession, tenant_id: UUID, application_id: UUID, message: str):
    """Underwriters and administrators: a policy is their business, not a doctor's."""
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
                notification_type=NotificationType.POLICY_CANCELLED,
                channel=NotificationChannel.IN_APP,
                status=NotificationStatus.SENT,
                message=message,
            )
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
    row = await _load(db, policy_id, principal)
    if row.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This policy is already cancelled."
        )
    row.status = "cancelled"
    row.cancelled_at = datetime.now(UTC)
    row.cancelled_by = principal.user_id
    row.cancel_reason = payload.reason.strip()

    applicant = await db.get(Applicant, row.applicant_id)
    await persistence.append_audit(
        db,
        tenant_id=row.tenant_id,
        application_id=row.application_id,
        actor_user_id=principal.user_id,
        event_type="policy_cancelled",
        payload={"policy_number": row.policy_number, "reason": row.cancel_reason},
    )
    await _notify_staff(
        db,
        row.tenant_id,
        row.application_id,
        f"Policy {row.policy_number} was cancelled. Reason: {row.cancel_reason}",
    )
    await db.commit()
    await db.refresh(row)

    if applicant and applicant.email:
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
    return (await describe(db, [row]))[0]


@router.post(
    "/policies/{policy_id}/payments",
    response_model=PolicySchema,
    status_code=status.HTTP_201_CREATED,
    summary="Record a month's premium as paid (owner only)",
)
async def record_payment(
    policy_id: UUID,
    payload: PaymentIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> PolicySchema:
    _owner_only(principal, "record a payment")
    row = await _load(db, policy_id, principal)
    if row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This policy is cancelled; no premium is due on it.",
        )

    [current] = await describe(db, [row])
    unpaid = [i for i in current.installments if i.status != "paid"]
    if payload.due_date is None:
        if not unpaid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Nothing is due on this policy."
            )
        target = unpaid[0]
    else:
        target = next((i for i in current.installments if i.due_date == payload.due_date), None)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No premium falls due on that date.",
            )
        if target.status == "paid":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="That month is already paid."
            )

    db.add(
        PremiumPayment(
            tenant_id=row.tenant_id,
            policy_id=row.id,
            due_date=target.due_date,
            amount_bdt=target.amount_bdt,
            method=payload.method,
            reference=(payload.reference or "").strip() or None,
            recorded_by=principal.user_id,
        )
    )
    await persistence.append_audit(
        db,
        tenant_id=row.tenant_id,
        application_id=row.application_id,
        actor_user_id=principal.user_id,
        event_type="premium_paid",
        payload={
            "policy_number": row.policy_number,
            "due_date": target.due_date.isoformat(),
            "amount": float(target.amount_bdt),
            "method": payload.method,
        },
    )
    await db.commit()
    return (await describe(db, [row]))[0]
