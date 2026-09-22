"""Company settings: the defaults every application this company takes follows.

Three groups, one endpoint. The turnaround promise, the risk-score tier
boundaries, and the pricing policy are all per company, all set by an
administrator, and all recorded when they change, with who changed them and
what they were before.

**A change here never rewrites the past.** Turnaround is copied onto each
application as a date at submit. Every score snapshots the boundaries it was
tiered with. So changing a setting affects applications taken, and scores
computed, from now on. That was agreed explicitly (2026-09-22) over re-tiering
open cases.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import Tenant, TenantSettingsChange, User
from app.models.user import UserRole
from app.schemas.application import (
    SettingsChangeSchema,
    TenantSettingsIn,
    TenantSettingsSchema,
)

router = APIRouter(prefix="/tenant", tags=["Tenant"])

# The columns an administrator may change, in the order the history shows them.
EDITABLE = (
    "turnaround_business_days",
    "tier_low_max",
    "tier_moderate_max",
    "premium_low_bdt",
    "premium_moderate_bdt",
    "reference_cover_bdt",
)


async def _tenant_for(db: AsyncSession, principal: Principal) -> Tenant:
    tenant = await db.get(Tenant, principal.tenant_id)
    if tenant is None:
        # The built-in accounts' tenant is created on their first sign-in, so
        # this only happens when that has not run yet. Say that rather than 500.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company record for this session. Sign out and in again.",
        )
    return tenant


def _as_schema(tenant: Tenant) -> TenantSettingsSchema:
    return TenantSettingsSchema(
        name=tenant.name,
        turnaround_business_days=tenant.turnaround_business_days,
        tier_low_max=float(tenant.tier_low_max),
        tier_moderate_max=float(tenant.tier_moderate_max),
        premium_low_bdt=float(tenant.premium_low_bdt),
        premium_moderate_bdt=float(tenant.premium_moderate_bdt),
        reference_cover_bdt=float(tenant.reference_cover_bdt),
    )


def _plain(value: object) -> float | int | None:
    """A JSON-safe number for the change log."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value  # type: ignore[return-value]


@router.get("/settings", response_model=TenantSettingsSchema, summary="This company's settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> TenantSettingsSchema:
    return _as_schema(await _tenant_for(db, principal))


@router.patch(
    "/settings",
    response_model=TenantSettingsSchema,
    summary="Change this company's settings (admin only)",
)
async def update_settings(
    payload: TenantSettingsIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> TenantSettingsSchema:
    """Only an administrator changes company defaults. Fields left out are left
    alone. The relationship between the two tier boundaries is checked against
    what will be stored, so sending one without the other cannot cross them."""
    # Compared through the enum, not a bare string: a string here survives a
    # role rename silently and locks everyone out.
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can change company settings.",
        )

    tenant = await _tenant_for(db, principal)
    incoming = payload.model_dump(exclude_none=True)
    if not incoming:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nothing to change: send at least one setting.",
        )

    low = incoming.get("tier_low_max", float(tenant.tier_low_max))
    moderate = incoming.get("tier_moderate_max", float(tenant.tier_moderate_max))
    if low >= moderate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"The low boundary ({low:g}) must be below the moderate boundary "
                f"({moderate:g}); otherwise the moderate tier cannot exist."
            ),
        )

    # Record what changed, from what, before writing it.
    changes: dict[str, dict[str, float | int | None]] = {}
    for field in EDITABLE:
        if field not in incoming:
            continue
        before = _plain(getattr(tenant, field))
        after = _plain(incoming[field])
        if before != after:
            changes[field] = {"from": before, "to": after}
            setattr(
                tenant,
                field,
                Decimal(str(after)) if isinstance(getattr(tenant, field), Decimal) else after,
            )

    if changes:
        # The built-in accounts have rows once they have signed in with the
        # database up; a session with no row is recorded as nobody rather than
        # failing the change.
        actor = await db.get(User, principal.user_id)
        db.add(
            TenantSettingsChange(
                tenant_id=tenant.id,
                actor_user_id=actor.id if actor else None,
                changes=changes,
            )
        )
        await db.commit()
        await db.refresh(tenant)

    return _as_schema(tenant)


@router.get(
    "/settings/history",
    response_model=list[SettingsChangeSchema],
    summary="Who changed which setting, and from what",
)
async def settings_history(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[SettingsChangeSchema]:
    """Newest first, the last 50. Any member of the company may read it: the
    settings apply to everyone's work, so their history is not secret."""
    rows = (
        await db.execute(
            select(TenantSettingsChange, User.full_name)
            .outerjoin(User, User.id == TenantSettingsChange.actor_user_id)
            .where(TenantSettingsChange.tenant_id == principal.tenant_id)
            .order_by(TenantSettingsChange.changed_at.desc())
            .limit(50)
        )
    ).all()
    return [
        SettingsChangeSchema(changed_at=change.changed_at, actor_name=name, changes=change.changes)
        for change, name in rows
    ]

