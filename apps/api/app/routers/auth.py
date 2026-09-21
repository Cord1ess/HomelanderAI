"""FastAPI Authentication and Carrier Onboarding Router.

Handles tenant registration, login credentials, httpOnly session cookies,
and current user session verification.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthResponseSchema,
    ChangePasswordSchema,
    RegisterStaffSchema,
    RegisterTenantSchema,
    TenantSchema,
    UpdateProfileSchema,
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
SENIOR_USER_ID = UUID("00000000-0000-0000-0000-0000000000b2")
UNDERWRITER_USER_ID = UUID("00000000-0000-0000-0000-0000000000b1")
ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000c0")


def _demo_session(user_id: str | None = None, username: str | None = None) -> AuthResponseSchema:
    """The user and company this account presents as. Never stored anywhere."""
    now = datetime.now(UTC)
    uname = username.strip().lower() if username else None

    if user_id == str(SENIOR_USER_ID) or uname == settings.senior_username.lower():
        uid = SENIOR_USER_ID
        full_name = settings.senior_display_name
        email = settings.senior_username
        role = UserRole.SENIOR_UNDERWRITER
    elif user_id == str(UNDERWRITER_USER_ID) or uname == settings.underwriter_username.lower():
        uid = UNDERWRITER_USER_ID
        full_name = settings.underwriter_display_name
        email = settings.underwriter_username
        role = UserRole.UNDERWRITER
    else:
        uid = ADMIN_USER_ID
        full_name = settings.admin_display_name
        email = settings.admin_username
        role = UserRole.ADMIN

    return AuthResponseSchema(
        user=UserSchema(
            id=uid,
            tenant_id=ADMIN_TENANT_ID,
            full_name=full_name,
            email=email,
            role=role,
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


def _is_demo_login(username: str, password: str) -> bool:
    if not settings.admin_login_enabled:
        return False

    uname = username.strip().lower()
    return (
        (uname == settings.admin_username.lower() and password == settings.admin_password)
        or (uname == settings.senior_username.lower() and password == settings.senior_password)
        or (
            uname == settings.underwriter_username.lower()
            and password == settings.underwriter_password
        )
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
    if _is_demo_login(payload.email, payload.password):
        log.warning(
            "Built-in demo sign-in used. This bypasses the database and is only "
            "available in development."
        )
        session = _demo_session(username=payload.email)
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
    except Exception as exc:
        log.error("Database unreachable during sign-in: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Cannot reach the database. Check its address, or sign in with "
                "one of the built-in demo accounts."
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
                detail="The built-in demo sign-in is no longer enabled.",
            )
        return _demo_session(user_id=payload.get("sub"))

    user_id = payload["sub"]
    try:
        result = await db.execute(select(User).where(User.id == user_id))
    except Exception as exc:
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


@router.patch(
    "/profile",
    response_model=UserSchema,
    summary="Update Profile Details",
)
async def update_profile(
    payload: UpdateProfileSchema,
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    """Update authenticated operator profile attributes."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active session cookie found.",
        )

    token_data = decode_access_token(session_token)
    if not token_data or "sub" not in token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session cookie.",
        )

    if token_data.get("fallback"):
        session = _admin_session()
        if payload.full_name is not None and payload.full_name.strip():
            session.user.full_name = payload.full_name.strip()
        if payload.license_number is not None:
            session.user.license_number = payload.license_number.strip() or None
        return session.user

    user_id = token_data["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated.",
        )

    if payload.full_name is not None and payload.full_name.strip():
        user.full_name = payload.full_name.strip()
    if payload.license_number is not None:
        stripped = payload.license_number.strip()
        user.license_number = stripped or None

    await db.commit()
    await db.refresh(user)
    return UserSchema.model_validate(user)


@router.post(
    "/profile/change-password",
    summary="Change Account Password",
)
async def change_password(
    payload: ChangePasswordSchema,
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Change authenticated operator password with current credential verification."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active session cookie found.",
        )

    token_data = decode_access_token(session_token)
    if not token_data or "sub" not in token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session cookie.",
        )

    if token_data.get("fallback"):
        if payload.current_password != settings.admin_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        return {"status": "ok"}

    user_id = token_data["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated.",
        )

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"status": "ok"}


# ── Staff Management (Admin Governance) ──────────────────────────────────────


def _demo_staff() -> list[UserSchema]:
    now = datetime.now(UTC)
    return [
        UserSchema(
            id=ADMIN_USER_ID,
            tenant_id=ADMIN_TENANT_ID,
            full_name=settings.admin_display_name,
            email=settings.admin_username,
            role=UserRole.ADMIN,
            license_number="ADM-001-HQ",
            created_at=now,
        ),
        UserSchema(
            id=UUID("00000000-0000-0000-0000-0000000000b1"),
            tenant_id=ADMIN_TENANT_ID,
            full_name="Dr. Aris Thorne",
            email="aris.thorne@homelander.ai",
            role=UserRole.SENIOR_UNDERWRITER,
            license_number="HL-MED-2026-SR",
            created_at=now,
        ),
        UserSchema(
            id=UUID("00000000-0000-0000-0000-0000000000c2"),
            tenant_id=ADMIN_TENANT_ID,
            full_name="Fatima Al-Zahra",
            email="fatima.zahra@homelander.ai",
            role=UserRole.UNDERWRITER,
            license_number="HL-UW-REG-4412",
            created_at=now,
        ),
        UserSchema(
            id=UUID("00000000-0000-0000-0000-0000000000d3"),
            tenant_id=ADMIN_TENANT_ID,
            full_name="Rahim Chowdhury",
            email="rahim.c@homelander.ai",
            role=UserRole.UNDERWRITER,
            license_number="HL-UW-REG-9821",
            created_at=now,
        ),
    ]


_demo_staff_cache: list[UserSchema] = []


@router.get(
    "/users",
    response_model=list[UserSchema],
    summary="List Carrier Tenant Staff",
)
async def list_tenant_staff(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> list[UserSchema]:
    """Retrieve all staff members associated with the caller's carrier tenant."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active session cookie found.",
        )

    token_data = decode_access_token(session_token)
    if not token_data or "sub" not in token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session cookie.",
        )

    if token_data.get("fallback"):
        global _demo_staff_cache
        if not _demo_staff_cache:
            _demo_staff_cache = _demo_staff()
        return _demo_staff_cache

    user_id = token_data["sub"]
    user_result = await db.execute(select(User).where(User.id == user_id))
    caller = user_result.scalar_one_or_none()
    if not caller or not caller.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Caller account not found or deactivated.",
        )

    staff_result = await db.execute(
        select(User).where(User.tenant_id == caller.tenant_id).order_by(User.created_at.desc())
    )
    users = staff_result.scalars().all()
    return [UserSchema.model_validate(u) for u in users]


@router.post(
    "/users",
    response_model=UserSchema,
    summary="Provision New Staff Operator",
)
async def provision_staff(
    payload: RegisterStaffSchema,
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    """Provision a new underwriter or senior underwriter within the tenant."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active session cookie found.",
        )

    token_data = decode_access_token(session_token)
    if not token_data or "sub" not in token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session cookie.",
        )

    if token_data.get("fallback"):
        global _demo_staff_cache
        if not _demo_staff_cache:
            _demo_staff_cache = _demo_staff()
        new_operator = UserSchema(
            id=uuid4(),
            tenant_id=ADMIN_TENANT_ID,
            full_name=payload.full_name.strip(),
            email=payload.email.strip().lower(),
            role=payload.role,
            license_number=payload.license_number.strip() if payload.license_number else None,
            created_at=datetime.now(UTC),
        )
        _demo_staff_cache.insert(0, new_operator)
        return new_operator

    caller_id = token_data["sub"]
    caller_result = await db.execute(select(User).where(User.id == caller_id))
    caller = caller_result.scalar_one_or_none()
    if not caller or not caller.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Caller not found or deactivated.",
        )

    if caller.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators may provision staff operators.",
        )

    # Check unique email
    existing = await db.execute(select(User).where(User.email == payload.email.strip().lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    new_user = User(
        tenant_id=caller.tenant_id,
        full_name=payload.full_name.strip(),
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        license_number=payload.license_number.strip() if payload.license_number else None,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return UserSchema.model_validate(new_user)
