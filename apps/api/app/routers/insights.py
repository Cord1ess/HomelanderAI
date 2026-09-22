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

from fastapi import APIRouter, Depends, Query
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
    ModelArm,
    ModelRun,
    SubScore,
    UnderwriterDecision,
    UnderwriterDecisionType,
)
from app.schemas.insights import (
    AnalyticsSchema,
    ArmActivitySchema,
    ClientSchema,
    CountSchema,
    CoverTypeSchema,
    WeekSchema,
)

router = APIRouter(tags=["Insights"])


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
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            Applicant.name.ilike(needle)
            | Applicant.external_ref.ilike(needle)
            | Applicant.phone.ilike(needle)
            | Applicant.email.ilike(needle)
        )
    applicants = (await db.execute(stmt.order_by(Applicant.created_at.desc()))).scalars().all()
    if not applicants:
        return []

    ids = [a.id for a in applicants]
    applications = (
        await db.execute(
            select(Application)
            .where(Application.applicant_id.in_(ids))
            .order_by(Application.submitted_at.desc())
        )
    ).scalars().all()
    scores = await _latest_scores(db, principal.tenant_id)

    by_applicant: dict[UUID, list[Application]] = defaultdict(list)
    for app in applications:
        by_applicant[app.applicant_id].append(app)

    out: list[ClientSchema] = []
    for a in applicants:
        apps = by_applicant.get(a.id, [])
        latest = apps[0] if apps else None
        score = scores.get(latest.id) if latest else None
        out.append(
            ClientSchema(
                id=a.id,
                reference=a.external_ref,
                name=a.name,
                phone=a.phone,
                email=a.email,
                portal_id=a.portal_id,
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
    "/analytics", response_model=AnalyticsSchema, summary="The shape of this company's book"
)
async def analytics(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> AnalyticsSchema:
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
    )
