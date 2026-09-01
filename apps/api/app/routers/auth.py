"""FastAPI Authentication and Carrier Onboarding Router.

Handles tenant registration, login credentials, httpOnly session cookies,
and current user session verification.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    AuthResponseSchema,
    RegisterTenantSchema,
    TenantSchema,
    UserLoginSchema,
    UserSchema,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_NAME = "session_token"


def _set_auth_cookie(response: Response, token: str) -> None:
    """Utility to attach httpOnly session cookie to FastAPI response."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.access_token_ttl_minutes * 60,
        samesite="lax",
        secure=not settings.is_development,
    )


@router.post(
    "/register-tenant",
    response_model=AuthResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard Carrier Tenant & Admin",
)
async def register_tenant(
    payload: RegisterTenantSchema,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponseSchema:
    """Register a new Subscribing Carrier Tenant and initial Tenant Admin account."""
    # Check if user email already exists
    existing_user_query = await db.execute(
        select(User).where(User.email == payload.admin_email.lower())
    )
    if existing_user_query.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user account with this email address already exists.",
        )

    # 1. Create Tenant
    tenant = Tenant(
        name=payload.tenant_name,
        subscription_tier=payload.subscription_tier,
    )
    db.add(tenant)
    await db.flush()  # Generates tenant.id

    # 2. Create Admin User
    user = User(
        tenant_id=tenant.id,
        full_name=payload.admin_full_name,
        email=payload.admin_email.lower(),
        password_hash=hash_password(payload.admin_password),
        role=payload.role,
        license_number=payload.license_number,
    )
    db.add(user)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(user)

    # 3. Create & Set JWT Cookie
    token = create_access_token(
        subject=str(user.id), tenant_id=str(tenant.id), role=user.role.value
    )
    _set_auth_cookie(response, token)

    return AuthResponseSchema(
        user=UserSchema.model_validate(user),
        tenant=TenantSchema.model_validate(tenant),
    )


@router.post(
    "/login",
    response_model=AuthResponseSchema,
    summary="Authenticate User & Set Session Cookie",
)
async def login(
    payload: UserLoginSchema,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponseSchema:
    """Authenticate user with email and password, setting an httpOnly session cookie."""
    result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password.",
        )

    # Fetch Tenant
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Carrier organization tenant not found.",
        )

    # Set JWT Session Cookie
    token = create_access_token(
        subject=str(user.id), tenant_id=str(tenant.id), role=user.role.value
    )
    _set_auth_cookie(response, token)

    return AuthResponseSchema(
        user=UserSchema.model_validate(user),
        tenant=TenantSchema.model_validate(tenant),
    )


@router.get(
    "/me",
    response_model=AuthResponseSchema,
    summary="Get Current Authenticated User Session",
)
async def get_me(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> AuthResponseSchema:
    """Verify current httpOnly session cookie and return user details."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active session cookie found.",
        )

    payload = decode_access_token(session_token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session cookie.",
        )

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with session not found.",
        )

    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Carrier tenant not found.",
        )

    return AuthResponseSchema(
        user=UserSchema.model_validate(user),
        tenant=TenantSchema.model_validate(tenant),
    )


@router.post(
    "/logout",
    summary="Logout User & Clear Session Cookie",
)
async def logout(response: Response) -> dict[str, str]:
    """Clear httpOnly session cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "ok"}
