"""Unit tests for core security, password hashing, and JWT tokens."""

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    """Test Argon2id password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_generation_and_decoding() -> None:
    """Test JWT access token generation and payload verification."""
    user_id = "11111111-2222-3333-4444-555555555555"
    tenant_id = "99999999-8888-7777-6666-555555555555"
    role = "admin"

    token = create_access_token(subject=user_id, tenant_id=tenant_id, role=role)
    assert isinstance(token, str)

    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == user_id
    assert decoded["tenant_id"] == tenant_id
    assert decoded["role"] == role


def test_invalid_jwt_token_returns_none() -> None:
    """Test decoding an invalid JWT token string."""
    assert decode_access_token("invalid.jwt.token") is None
