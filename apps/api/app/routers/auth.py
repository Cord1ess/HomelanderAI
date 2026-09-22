"""FastAPI Authentication and Carrier Onboarding Router.

Handles tenant registration, login credentials, httpOnly session cookies,
and current user session verification.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import AsyncSessionLocal, get_db
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthResponseSchema,
    ChangePasswordSchema,
    RegisterStaffSchema,
    RegisterTenantSchema,
    StaffStatusIn,
    TenantSchema,
    UpdateProfileSchema,
    UserLoginSchema,
    UserSchema,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_NAME = "session_token"

log = logging.getLogger(__name__)

# ── Built-in accounts ────────────────────────────────────────────────────────
#
# Three accounts, one per staff role, all with the password in
# `settings.admin_password`. They work with no database at all, so a demo
# survives the database machine being unreachable. Development only — see
# settings.admin_login_enabled.
#
# Fixed IDs so a session is recognisable in logs and can never collide with a
# real row.
ADMIN_TENANT_ID = UUID("00000000-0000-0000-0000-0000000000c0")


@dataclass(frozen=True)
class BuiltInAccount:
    username: str
    user_id: UUID
    full_name: str
    role: UserRole


BUILT_IN_ACCOUNTS: tuple[BuiltInAccount, ...] = (
    BuiltInAccount(
        "underwriter",
        UUID("00000000-0000-0000-0000-0000000000b1"),
        "Underwriter",
        UserRole.UNDERWRITER,
    ),
    BuiltInAccount(
        "medical",
        UUID("00000000-0000-0000-0000-0000000000b2"),
        "Medical Professional",
        UserRole.MEDICAL_PROFESSIONAL,
    ),
    # Same id as before this rework, so everything the account already did
    # (applications, decisions, audit entries) stays attributed to it. The old
    # `senior` username is gone.
    BuiltInAccount(
        "admin",
        UUID("00000000-0000-0000-0000-0000000000ad"),
        "Administrator",
        UserRole.ADMIN,
    ),
)


def _built_in(user_id: str | None = None, username: str | None = None) -> BuiltInAccount | None:
    """Find a built-in account by token subject or by what was typed at sign-in.

    Returns None when nothing matches. It used to fall through to the admin
    account, which handed the most powerful identity to any unrecognised token.
    """
    uname = username.strip().lower() if username else None
    for account in BUILT_IN_ACCOUNTS:
        if user_id is not None and user_id == str(account.user_id):
            return account
        if uname is not None and uname == account.username:
            return account
    return None


def _demo_session(account: BuiltInAccount) -> AuthResponseSchema:
    """The user and company this account presents as. Built fresh on each call."""
    now = datetime.now(UTC)
    return AuthResponseSchema(
        user=UserSchema(
            id=account.user_id,
            tenant_id=ADMIN_TENANT_ID,
            full_name=account.full_name,
            email=account.username,
            role=account.role,
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
    if _built_in(username=username) is None:
        return False
    return secrets.compare_digest(password.encode(), settings.admin_password.encode())


def _require_built_in(token_data: dict) -> BuiltInAccount:
    """The built-in account behind a fallback token, or a 401."""
    account = _built_in(user_id=token_data.get("sub")) if settings.admin_login_enabled else None
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The built-in sign-in is no longer enabled. Sign in again.",
        )
    return account


async def _ensure_built_in_rows() -> None:
    """Give the built-in accounts real rows, so what they do can be attributed.

    A decision's `underwriter_id` and an audit entry's actor are foreign keys.
    Without a row, a built-in account can sign in and look around but is refused
    the moment it decides anything. Only the old `admin` was ever seeded, so the
    other two accounts were broken in exactly that way.

    Runs in the background after a built-in sign-in, so it never delays one and
    a missing database never fails one. It is an upsert, so a row seeded
    earlier is brought up to date rather than duplicated.

    The stored hash is of a random value that is thrown away. These accounts
    authenticate through `_is_demo_login` alone. If the rows held the real
    password, clearing ADMIN_PASSWORD would not switch them off: the ordinary
    database sign-in would still accept it.
    """
    try:
        unusable = hash_password(secrets.token_urlsafe(32))
        async with AsyncSessionLocal() as db:
            await db.execute(
                pg_insert(Tenant)
                .values(
                    id=ADMIN_TENANT_ID,
                    name=settings.admin_company_name,
                    subscription_tier="demo",
                )
                .on_conflict_do_nothing(index_elements=[Tenant.id])
            )
            for account in BUILT_IN_ACCOUNTS:
                row = {
                    "full_name": account.full_name,
                    "email": account.username,
                    "role": account.role,
                    "password_hash": unusable,
                    "is_active": True,
                }
                await db.execute(
                    pg_insert(User)
                    .values(id=account.user_id, tenant_id=ADMIN_TENANT_ID, **row)
                    .on_conflict_do_update(index_elements=[User.id], set_=row)
                )
            await db.commit()
    except (SQLAlchemyError, OSError) as exc:
        log.warning(
            "Could not create rows for the built-in accounts (%s). They can sign in, "
            "but cannot record a decision until the database is reachable.",
            exc,
        )


async def _built_in_row(db: AsyncSession, user_id: str) -> User | None:
    """A built-in account's own row, or None with no database or no row yet."""
    try:
        return await db.get(User, UUID(user_id))
    except (SQLAlchemyError, OSError, ValueError):
        return None


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
    background: BackgroundTasks,
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
        account = _built_in(username=payload.email)
        assert account is not None  # _is_demo_login just matched it
        session = _demo_session(account)
        background.add_task(_ensure_built_in_rows)
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

    # Anything that is not a built-in account needs the database. Say so
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
        # 401 when the switch was turned off while a cookie was still live, or
        # when the token names an account that no longer exists (`senior`).
        return _demo_session(_require_built_in(payload))

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
        session = _demo_session(_require_built_in(token_data))
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
    """The staff list when there is no database: the three built-in accounts.

    It used to include three invented people. A staff screen should never show
    someone who cannot sign in.
    """
    now = datetime.now(UTC)
    return [
        UserSchema(
            id=account.user_id,
            tenant_id=ADMIN_TENANT_ID,
            full_name=account.full_name,
            email=account.username,
            role=account.role,
            license_number=None,
            created_at=now,
        )
        for account in BUILT_IN_ACCOUNTS
    ]


_demo_staff_cache: list[UserSchema] = []


@router.patch(
    "/users/{user_id}/status",
    response_model=UserSchema,
    summary="Deactivate or reactivate a staff account (admin only)",
)
async def set_staff_status(
    user_id: UUID,
    payload: StaffStatusIn,
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    """A deactivated account keeps its rows and its history, which is the
    point: decisions stay attributed to the person who made them. It can no
    longer sign in. An administrator cannot deactivate their own account, so a
    company can never lock itself out."""
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

    caller = await db.get(User, UUID(token_data["sub"]))
    if caller is None or not caller.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Caller not found or deactivated.",
        )
    if caller.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can change who may sign in.",
        )
    if caller.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You cannot deactivate your own account.",
        )

    target = await db.get(User, user_id)
    if target is None or target.tenant_id != caller.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No such account at your company.",
        )

    target.is_active = payload.is_active
    await db.commit()
    await db.refresh(target)
    return UserSchema.model_validate(target)


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
        _require_built_in(token_data)
        # With the database up, a built-in account has a real row and sees the
        # real staff of its tenant. The in-memory list is only for when there
        # is no database to ask.
        if await _built_in_row(db, token_data["sub"]) is None:
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
    """Add a staff account to the caller's tenant. Administrators only."""
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
        # This check used to be missing, so the built-in underwriter could add
        # staff.
        if _require_built_in(token_data).role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an administrator can add staff.",
            )
        # With the database up, the built-in admin has a real row: fall through
        # and create the account for real, so the new person can sign in. Only
        # with no database is it kept in memory, so the screen still works in an
        # outage demo.
        if await _built_in_row(db, token_data["sub"]) is None:
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
            detail="Only an administrator can add staff.",
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
