"""Clients and analytics: the company's applicants, and the shape of its book.

Both read only what the company already holds. Analytics is computed in
Python over the company's rows rather than in SQL: at the scale of one
carrier's queue it is instant, and every figure is defined in one readable
place. Each figure is something a real row backs; nothing here is estimated.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import turnaround
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import (
    Applicant,
    Application,
    ApplicationStatus,
    CompositeScore,
    DoctorReview,
    InsurancePolicy,
    ModelArm,
    ModelRun,
    PremiumPayment,
    SubScore,
    UnderwriterDecision,
    UnderwriterDecisionType,
    UserRole,
)
from app.routers.access import access_to, can_see
from app.schemas.insights import (
    AnalyticsSchema,
    ArmActivitySchema,
    BusinessSchema,
    ClientApplicationSchema,
    ClientProfileSchema,
    ClientSchema,
    CountSchema,
    CoverTypeSchema,
    MonthMoneySchema,
    WeekSchema,
)

router = APIRouter(tags=["Insights"])


def _is_doctor(principal: Principal) -> bool:
    return principal.role == UserRole.MEDICAL_PROFESSIONAL.value


async def _verdicts(db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    """The newest doctor's verdict per application."""
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


async def _latest_scores(db: AsyncSession, tenant_id: UUID) -> dict[UUID, CompositeScore]:
    """The newest composite score per application."""
    latest = (
        select(
            CompositeScore.application_id,
            func.max(CompositeScore.version).label("version"),
        )
        .where(CompositeScore.tenant_id == tenant_id)
        .group_by(CompositeScore.application_id)
        .subquery()
    )
    rows = await db.execute(
        select(CompositeScore).join(
            latest,
            (CompositeScore.application_id == latest.c.application_id)
            & (CompositeScore.version == latest.c.version),
        )
    )
    return {s.application_id: s for s in rows.scalars().all()}


@router.get("/clients", response_model=list[ClientSchema], summary="Every client of this company")
async def list_clients(
    q: str | None = Query(default=None, max_length=100),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[ClientSchema]:
    """Each applicant once, with their latest application. Newest first."""
    stmt = select(Applicant).where(Applicant.tenant_id == principal.tenant_id)
    if _is_doctor(principal):
        stmt = stmt.where(
            Applicant.id.in_(
                select(Application.applicant_id).where(Application.sent_to_doctor_at.is_not(None))
            )
        )
    if q:
        needle = f"%{q.strip()}%"
        match = Applicant.name.ilike(needle) | Applicant.external_ref.ilike(needle)
        # Only the owner searches by phone or email: a match would otherwise
        # confirm a detail the searcher was not given.
        if principal.role == UserRole.ADMIN.value:
            match = match | Applicant.phone.ilike(needle) | Applicant.email.ilike(needle)
        stmt = stmt.where(match)
    applicants = (await db.execute(stmt.order_by(Applicant.created_at.desc()))).scalars().all()
    if not applicants:
        return []

    ids = [a.id for a in applicants]
    applications = (
        await db.execute(
            select(Application)
            .where(
                Application.applicant_id.in_(ids),
                *([Application.sent_to_doctor_at.is_not(None)] if _is_doctor(principal) else []),
            )
            .order_by(Application.submitted_at.desc())
        )
    ).scalars().all()
    scores = await _latest_scores(db, principal.tenant_id)
    access = await access_to(db, principal, ids)

    by_applicant: dict[UUID, list[Application]] = defaultdict(list)
    for app in applications:
        by_applicant[app.applicant_id].append(app)

    out: list[ClientSchema] = []
    for a in applicants:
        apps = by_applicant.get(a.id, [])
        latest = apps[0] if apps else None
        score = scores.get(latest.id) if latest else None
        state, until = access[a.id]
        visible = can_see(state)
        out.append(
            ClientSchema(
                id=a.id,
                reference=a.external_ref,
                name=a.name,
                phone=a.phone if visible else None,
                email=a.email if visible else None,
                portal_id=a.portal_id if visible else None,
                access=state,
                access_until=until,
                created_at=a.created_at,
                applications=len(apps),
                latest_application_id=latest.id if latest else None,
                latest_status=latest.status if latest else None,
                latest_tier=score.tier.value if score else None,
                latest_crs=float(score.crs_value) if score else None,
                coverage_type=latest.coverage_type if latest else None,
                coverage_amount=latest.coverage_amount if latest else None,
                expected_by=latest.expected_by if latest else None,
                overdue=(
                    turnaround.is_overdue(latest.expected_by, latest.status.value)
                    if latest
                    else False
                ),
            )
        )
    return out


@router.get(
    "/clients/{client_id}",
    response_model=ClientProfileSchema,
    summary="One client's profile and every application they made",
)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> ClientProfileSchema:
    """404, not 403, for another company's client: saying that an id exists
    elsewhere is itself a leak."""
    applicant = (
        await db.execute(
            select(Applicant).where(
                Applicant.id == client_id, Applicant.tenant_id == principal.tenant_id
            )
        )
    ).scalar_one_or_none()
    if applicant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such client.")

    applications = (
        await db.execute(
            select(Application)
            .where(
                Application.applicant_id == applicant.id,
                *([Application.sent_to_doctor_at.is_not(None)] if _is_doctor(principal) else []),
            )
            .order_by(Application.submitted_at.desc())
        )
    ).scalars().all()
    # A doctor may open only a client who was sent to them.
    if _is_doctor(principal) and not applications:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such client.")
    # Everyone but the owner asks first, with a reason (routers/access.py).
    state, _ = (await access_to(db, principal, [applicant.id]))[applicant.id]
    if not can_see(state):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ask an administrator to see this client's details, with your reason.",
        )
    scores = await _latest_scores(db, principal.tenant_id)
    verdicts = await _verdicts(db, [a.id for a in applications])
    decisions = {
        d.application_id: d
        for d in (
            await db.execute(
                select(UnderwriterDecision).where(
                    UnderwriterDecision.application_id.in_([a.id for a in applications])
                )
            )
        ).scalars().all()
    } if applications else {}

    from app.routers.policies import describe

    issued = (
        await db.execute(
            select(InsurancePolicy)
            .where(InsurancePolicy.applicant_id == applicant.id)
            .order_by(InsurancePolicy.created_at.desc())
        )
    ).scalars().all()

    return ClientProfileSchema(
        policies=await describe(db, list(issued)),
        id=applicant.id,
        reference=applicant.external_ref,
        name=applicant.name,
        phone=applicant.phone,
        email=applicant.email,
        portal_id=applicant.portal_id,
        date_of_birth=applicant.date_of_birth,
        sex=applicant.sex,
        height_cm=applicant.height_cm,
        weight_kg=applicant.weight_kg,
        created_at=applicant.created_at,
        applications=[
            ClientApplicationSchema(
                id=app.id,
                # The HL- reference is the client's, and every application of
                # theirs carries it — the same number the portal and the
                # doctor see.
                reference=applicant.external_ref,
                submitted_at=app.submitted_at,
                status=app.status,
                crs=float(scores[app.id].crs_value) if app.id in scores else None,
                tier=scores[app.id].tier.value if app.id in scores else None,
                coverage_type=app.coverage_type,
                coverage_amount=app.coverage_amount,
                policy_term=app.policy_term,
                expected_by=app.expected_by,
                overdue=turnaround.is_overdue(app.expected_by, app.status.value),
                decision=decisions[app.id].decision.value if app.id in decisions else None,
                decided_at=decisions[app.id].decided_at if app.id in decisions else None,
                doctor_verdict=verdicts.get(app.id),
            )
            for app in applications
        ],
    )


@router.get(
    "/analytics", response_model=AnalyticsSchema, summary="The shape of this company's book"
)
async def analytics(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> AnalyticsSchema:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analytics is for the company owner (an administrator).",
        )
    tenant_id = principal.tenant_id
    applications = (
        await db.execute(
            select(Application)
            .where(Application.tenant_id == tenant_id)
            .order_by(Application.submitted_at)
        )
    ).scalars().all()
    scores = await _latest_scores(db, tenant_id)
    decisions = {
        d.application_id: d
        for d in (
            await db.execute(
                select(UnderwriterDecision).where(UnderwriterDecision.tenant_id == tenant_id)
            )
        ).scalars().all()
    }

    # ── counts ──
    by_status = Counter(app.status.value for app in applications)
    by_tier = Counter(scores[app.id].tier.value for app in applications if app.id in scores)
    by_decision = Counter(d.decision.value for d in decisions.values())

    approvals = [
        d
        for d in decisions.values()
        if d.decision
        in (
            UnderwriterDecisionType.CONFIRMED_FAST_TRACK,
            UnderwriterDecisionType.APPROVED_WITH_ADJUSTMENT,
        )
    ]
    decided = [app for app in applications if app.id in decisions]

    # ── money: what was asked for, what was approved, what it earns a month ──
    cover_requested = sum((app.coverage_amount or Decimal(0)) for app in applications)
    cover_approved = sum(
        (app.coverage_amount or Decimal(0))
        for app in applications
        if app.id in decisions and decisions[app.id] in approvals
    )
    monthly_premium_book = sum((d.final_premium or Decimal(0)) for d in approvals)

    # ── by cover type ──
    covers: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": Decimal(0), "approved": 0})
    for app in applications:
        key = app.coverage_type or "unspecified"
        covers[key]["count"] += 1
        covers[key]["amount"] += app.coverage_amount or Decimal(0)
        if app.id in decisions and decisions[app.id] in approvals:
            covers[key]["approved"] += 1

    # ── time: how long a decision takes, and whether the promise was kept ──
    days_to_decide: list[float] = []
    on_time = late = 0
    for app in decided:
        d = decisions[app.id]
        days_to_decide.append((d.decided_at - app.submitted_at).total_seconds() / 86400)
        if app.expected_by is not None:
            if d.decided_at.date() <= app.expected_by:
                on_time += 1
            else:
                late += 1

    # ── applications per week, last eight weeks ──
    today = date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=7)
    weeks: list[WeekSchema] = []
    for i in range(8):
        week_start = start + timedelta(weeks=i)
        week_end = week_start + timedelta(days=7)
        taken = [
            app for app in applications if week_start <= app.submitted_at.date() < week_end
        ]
        weeks.append(
            WeekSchema(
                week_of=week_start,
                applications=len(taken),
                decided=sum(1 for app in taken if app.id in decisions),
            )
        )

    # ── the readers: how often each ran, how it scored, how often it failed ──
    runs = (
        await db.execute(
            select(ModelArm.name, ModelRun.error_message, SubScore.calibrated_score)
            .join(ModelRun, ModelRun.model_arm_id == ModelArm.id)
            .outerjoin(SubScore, SubScore.model_run_id == ModelRun.id)
            .where(ModelRun.tenant_id == tenant_id)
        )
    ).all()
    per_arm: dict[str, dict] = defaultdict(lambda: {"runs": 0, "failed": 0, "scores": []})
    for name, error, score in runs:
        per_arm[name]["runs"] += 1
        if error:
            per_arm[name]["failed"] += 1
        if score is not None:
            per_arm[name]["scores"].append(float(score))

    crs_values = [float(s.crs_value) for s in scores.values()]
    business = await _business(db, tenant_id)

    return AnalyticsSchema(
        applications=len(applications),
        decided=len(decided),
        approved=len(approvals),
        escalated=by_status.get(ApplicationStatus.ESCALATED.value, 0),
        waiting=len(applications) - len(decided),
        average_crs=round(sum(crs_values) / len(crs_values), 1) if crs_values else None,
        by_status=[CountSchema(key=k, count=v) for k, v in sorted(by_status.items())],
        by_tier=[CountSchema(key=k, count=v) for k, v in sorted(by_tier.items())],
        by_decision=[CountSchema(key=k, count=v) for k, v in sorted(by_decision.items())],
        cover_requested_bdt=cover_requested,
        cover_approved_bdt=cover_approved,
        monthly_premium_book_bdt=monthly_premium_book,
        by_cover_type=[
            CoverTypeSchema(
                coverage_type=k, count=v["count"], amount_bdt=v["amount"], approved=v["approved"]
            )
            for k, v in sorted(covers.items())
        ],
        average_days_to_decide=(
            round(sum(days_to_decide) / len(days_to_decide), 1) if days_to_decide else None
        ),
        decided_on_time=on_time,
        decided_late=late,
        weeks=weeks,
        arms=[
            ArmActivitySchema(
                arm=name,
                runs=v["runs"],
                failed=v["failed"],
                average_score=(
                    round(sum(v["scores"]) / len(v["scores"]), 1) if v["scores"] else None
                ),
            )
            for name, v in sorted(per_arm.items())
        ],
        business=business,
    )


async def _business(db: AsyncSession, tenant_id: UUID) -> BusinessSchema:
    """Premiums in, payouts owed. Expected income is what active policies are
    due to pay; collected is what was recorded as paid. A claim pays the sum
    assured, so the sum over active policies is the most the company could owe."""
    from app.policies import add_months
    from app.routers.policies import describe

    clients = (
        await db.execute(select(func.count()).where(Applicant.tenant_id == tenant_id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(InsurancePolicy)
            .where(InsurancePolicy.tenant_id == tenant_id)
            .order_by(InsurancePolicy.created_at.desc())
        )
    ).scalars().all()
    described = await describe(db, list(rows))
    active = [p for p in described if p.status == "active"]

    payments = (
        await db.execute(
            select(PremiumPayment.paid_at, PremiumPayment.amount_bdt).where(
                PremiumPayment.tenant_id == tenant_id
            )
        )
    ).all()
    today = date.today()
    this_month = today.replace(day=1)
    zero = Decimal(0)
    collected_month = sum(
        (a for paid, a in payments if paid.date() >= this_month), zero
    )
    collected_year = sum(
        (a for paid, a in payments if paid.date().year == today.year), zero
    )
    collected_all = sum((a for _, a in payments), zero)

    # The last twelve months: due from each policy in force that month, and paid.
    months: list[MonthMoneySchema] = []
    for back in range(11, -1, -1):
        start = add_months(this_month, -back)
        end = add_months(start, 1)
        expected = zero
        for p in described:
            stop = p.cancelled_at.date() if p.cancelled_at else p.end_date
            if p.start_date < end and stop > start:
                expected += p.monthly_premium_bdt
        collected = sum((a for paid, a in payments if start <= paid.date() < end), zero)
        months.append(MonthMoneySchema(month=start, expected_bdt=expected, collected_bdt=collected))

    payouts = [p.sum_assured_bdt for p in active]
    monthly = sum((p.monthly_premium_bdt for p in active), zero)
    return BusinessSchema(
        clients=clients,
        policies_active=len(active),
        policies_cancelled=sum(1 for p in described if p.status == "cancelled"),
        premium_monthly_bdt=monthly,
        premium_yearly_bdt=monthly * 12,
        collected_this_month_bdt=collected_month,
        collected_this_year_bdt=collected_year,
        collected_all_time_bdt=collected_all,
        overdue_bdt=sum((p.overdue_total_bdt for p in active), zero),
        overdue_policies=sum(1 for p in active if p.overdue_count),
        sum_assured_in_force_bdt=sum(payouts, zero),
        largest_payout_bdt=max(payouts) if payouts else None,
        average_payout_bdt=(sum(payouts, zero) / len(payouts)).quantize(Decimal("1"))
        if payouts
        else None,
        months=months,
        policies=[p.model_copy(update={"installments": []}) for p in described],
    )
