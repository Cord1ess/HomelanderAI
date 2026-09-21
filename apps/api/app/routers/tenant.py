"""Settings a carrier's admin controls for the whole company.

One setting today: how long applicants are told a decision usually takes. It
lives on the tenant row rather than in the dashboard so every screen, and later
the client portal, reads the same figure.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import Tenant
from app.models.user import UserRole
from app.schemas.application import TenantSettingsIn, TenantSettingsSchema

router = APIRouter(prefix="/tenant", tags=["Tenant"])


async def _tenant_for(db: AsyncSession, principal: Principal) -> Tenant:
    tenant = await db.get(Tenant, principal.tenant_id)
    if tenant is None:
        # The built-in admin's tenant is seeded, so this only happens when the
        # seed was never run. Say that rather than 500.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No carrier record for this session. Has db/seed.sql been loaded?",
        )
    return tenant


@router.get("/settings", response_model=TenantSettingsSchema, summary="This carrier's settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> TenantSettingsSchema:
    tenant = await _tenant_for(db, principal)
    return TenantSettingsSchema(
        name=tenant.name, turnaround_business_days=tenant.turnaround_business_days
    )


@router.patch(
    "/settings",
    response_model=TenantSettingsSchema,
    summary="Change this carrier's settings (admin only)",
)
async def update_settings(
    payload: TenantSettingsIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> TenantSettingsSchema:
    """Only an administrator sets the default. The figure is what every future
    applicant is promised, which is a company decision rather than a case one.
    Applications already submitted keep the date they were given."""
    # Compared through the enum, not a bare string: a string here survives a
    # role rename silently and locks everyone out.
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can change company settings.",
        )

    tenant = await _tenant_for(db, principal)
    tenant.turnaround_business_days = payload.turnaround_business_days
    await db.commit()
    await db.refresh(tenant)
    return TenantSettingsSchema(
        name=tenant.name, turnaround_business_days=tenant.turnaround_business_days
    )
