"""Core security, password hashing, and JWT token management.

Uses Argon2id for password hashing and PyJWT for session tokens.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash password using Argon2id algorithm."""
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        return ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(
    subject: str,
    tenant_id: str,
    role: str,
    expires_delta: timedelta | None = None,
    fallback: bool = False,
) -> str:
    """Create signed JWT access token.

    `fallback` marks a session created by the emergency sign-in, which has no
    row in the database. `/me` reads the claim so it knows not to look one up.
    """
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_ttl_minutes)

    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    if fallback:
        payload["fallback"] = True

    return jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify JWT access token. Returns payload dict or None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.PyJWTError:
        return None
