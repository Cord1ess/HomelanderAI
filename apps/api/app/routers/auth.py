"""FastAPI Authentication and Carrier Onboarding Router.

Handles tenant registration, login credentials, httpOnly session cookies,
and current user session verification.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
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
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthResponseSchema,
    RegisterTenantSchema,
    TenantSchema,
    UserLoginSchema,
    UserSchema,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_NAME = "session_token"

log = logging.getLogger(__name__)

# ── Built-in admin sign-in ───────────────────────────────────────────────────
#
# Username `admin`, password `admin123`. Works with no database at all, so a
# demo survives the database machine being unreachable. Development only —
# see settings.admin_login_enabled.
#
# Fixed IDs so the session is recognisable in logs and can never collide with a
# real row.
ADMIN_USER_ID = UUID("00000000-0000-0000-0000-0000000000ad")
ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000c0")


def _admin_session() -> AuthResponseSchema:
    """The user and company this account presents as. Never stored anywhere."""
    now = datetime.now(UTC)
    return AuthResponseSchema(
        user=UserSchema(
            id=ADMIN_USER_ID,
            tenant_id=ADMIN_TENANT_ID,
            full_name=settings.admin_display_name,
            email=settings.admin_username,
            role=UserRole.ADMIN,
            license_number=None,
            created_at=now,
        ),
        tenant=TenantSchema(
            id=ADMIN_TENANT_ID,
            name=settings.admin_company_name,
            subscription_tier="demo",
            created_at=now,
        ),
    )


def _is_admin_login(username: str, password: str) -> bool:
    if not settings.admin_login_enabled:
        return False
    return (
        username.strip().lower() == settings.admin_username.lower()
        and password == settings.admin_password
    )


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
    # Checked first and without the database, so this still works when the
    # database machine is unreachable — which is the whole point of it.
    if _is_admin_login(payload.email, payload.password):
        log.warning(
            "Built-in '%s' sign-in used. This bypasses the database and is only "
            "available in development.",
            settings.admin_username,
        )
        session = _admin_session()
        _set_auth_cookie(
            response,
            create_access_token(
                subject=str(session.user.id),
                tenant_id=str(session.tenant.id),
                role=session.user.role.value,
                fallback=True,
            ),
        )
        return session

    # Anything that is not the built-in admin needs the database. Say so
    # plainly rather than surfacing a driver traceback as a 500.
    try:
        result = await db.execute(
            select(User).where(User.email == payload.email.lower())
        )
    except (SQLAlchemyError, OSError) as exc:
        log.error("Database unreachable during sign-in: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Cannot reach the database. Check its address, or sign in with "
                "the built-in admin account."
            ),
        ) from exc

    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password.",
        )

    # Accounts are switched off rather than deleted, so this check is what
    # actually stops a retired user signing in.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact your administrator.",
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

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

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

    if payload.get("fallback"):
        if not settings.admin_login_enabled:
            # The switch was turned off while a cookie was still live.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="The built-in admin sign-in is no longer enabled.",
            )
        return _admin_session()

    user_id = payload["sub"]
    try:
        result = await db.execute(select(User).where(User.id == user_id))
    except (SQLAlchemyError, OSError) as exc:
        log.error("Database unreachable while checking the session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot reach the database.",
        ) from exc
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with session not found or no longer active.",
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
