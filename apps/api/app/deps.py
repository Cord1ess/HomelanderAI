"""Request dependencies shared by the data endpoints.

Every endpoint below the auth layer needs the same two things: who is asking,
and which tenant's rows they may see. `current_principal` answers both from the
session cookie so no endpoint has to decode a token itself.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Cookie, HTTPException, status

from app.config import settings
from app.core.security import decode_access_token

COOKIE_NAME = "session_token"


@dataclass(frozen=True)
class Principal:
    """The signed-in user, reduced to what the endpoints actually use."""

    user_id: UUID
    tenant_id: UUID
    role: str
    # True for the built-in admin sign-in, which is issued without a database
    # lookup. Its ids are seeded (db/seed.sql), so it can still own rows.
    is_builtin_admin: bool = False


async def current_principal(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> Principal:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )

    payload = decode_access_token(session_token)
    if not payload or "sub" not in payload or "tenant_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Sign in again.",
        )

    if payload.get("fallback") and not settings.admin_login_enabled:
        # The switch was turned off while a cookie was still live.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The built-in admin sign-in is no longer enabled.",
        )

    try:
        return Principal(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=str(payload.get("role", "underwriter")),
            is_builtin_admin=bool(payload.get("fallback")),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is not valid. Sign in again.",
        ) from exc
