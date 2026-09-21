"""The three built-in accounts: `underwriter`, `medical` and `admin`.

One per staff role, all with the password in ADMIN_PASSWORD. They bypass the
database, so the tests that matter most are the ones proving they stay off
outside development.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import create_access_token, verify_password
from app.main import app
from app.models import UserRole
from app.routers.auth import (
    ADMIN_TENANT_ID,
    BUILT_IN_ACCOUNTS,
    COOKIE_NAME,
    _is_demo_login,
)
from tests.conftest import needs_database

# username -> the role it must present as
EXPECTED = {
    "underwriter": "underwriter",
    "medical": "medical_professional",
    "admin": "admin",
}


@pytest.fixture
def dev(monkeypatch):
    """Development, with the shipped default password."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_password", "admin123")
    return settings


def sign_in(client: TestClient, username: str) -> dict:
    response = client.post("/api/auth/login", json={"email": username, "password": "admin123"})
    assert response.status_code == 200, response.text
    return response.json()


# ── what exists ──────────────────────────────────────────────────────────────


def test_there_are_exactly_three_staff_roles():
    """Applicants are deliberately not here: they have no account and no role."""
    assert {role.value for role in UserRole} == {"underwriter", "medical_professional", "admin"}


def test_there_is_exactly_one_built_in_account_per_role():
    assert {a.username: a.role.value for a in BUILT_IN_ACCOUNTS} == EXPECTED
    assert len({a.user_id for a in BUILT_IN_ACCOUNTS}) == 3


# ── the guards ───────────────────────────────────────────────────────────────


def test_off_outside_development(monkeypatch):
    """The one check that stops these reaching a real deployment."""
    monkeypatch.setattr(settings, "admin_password", "admin123")

    for environment in ("production", "staging", "prod", ""):
        monkeypatch.setattr(settings, "environment", environment)
        assert settings.admin_login_enabled is False
        for username in EXPECTED:
            assert _is_demo_login(username, "admin123") is False


def test_off_when_password_cleared(monkeypatch):
    """Clearing the password is the manual off switch for all three, and empty
    must never mean 'any password'."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_password", "")

    assert settings.admin_login_enabled is False
    for username in EXPECTED:
        assert _is_demo_login(username, "") is False
        assert _is_demo_login(username, "anything") is False


def test_wrong_password_rejected(dev):
    for wrong in ("admin", "admin1234", "Admin123", "", "admin12"):
        assert _is_demo_login("admin", wrong) is False


def test_the_old_account_is_gone(dev):
    """`senior` was a built-in account until 2026-09-22."""
    for removed in ("senior", "administrator", "root"):
        assert _is_demo_login(removed, "admin123") is False


def test_username_is_case_and_space_insensitive(dev):
    assert _is_demo_login("ADMIN", "admin123") is True
    assert _is_demo_login("  medical  ", "admin123") is True


# ── end to end, with no database ─────────────────────────────────────────────


@pytest.mark.parametrize(("username", "role"), EXPECTED.items())
def test_each_account_signs_in_with_its_own_role_without_a_database(dev, username, role):
    """The whole point: no database is touched to sign in, so this holds even
    when the database machine is unreachable."""
    with TestClient(app) as client:
        body = sign_in(client, username)
        assert body["user"]["email"] == username
        assert body["user"]["role"] == role
        assert body["tenant"]["id"] == str(ADMIN_TENANT_ID)
        assert COOKIE_NAME in client.cookies

        # The follow-up call is where a database lookup would otherwise happen,
        # and where one account could be mistaken for another.
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["user"]["email"] == username
        assert me.json()["user"]["role"] == role


def test_an_unrecognised_built_in_token_is_refused_not_promoted(dev):
    """Any built-in token that matched nothing used to be treated as the admin.
    A token left over from the removed `senior` account is exactly that."""
    token = create_access_token(
        subject=str(uuid.uuid4()),
        tenant_id=str(ADMIN_TENANT_ID),
        role="underwriter",
        fallback=True,
    )
    with TestClient(app) as client:
        client.cookies.set(COOKIE_NAME, token)
        assert client.get("/api/auth/me").status_code == 401


def test_editing_a_profile_answers_as_the_account_that_asked(dev):
    """This used to answer with the admin's identity whoever was signed in."""
    with TestClient(app) as client:
        sign_in(client, "underwriter")
        response = client.patch("/api/auth/profile", json={"fullName": "A. Underwriter"})
        assert response.status_code == 200, response.text
        assert response.json()["email"] == "underwriter"
        assert response.json()["role"] == "underwriter"


@pytest.mark.parametrize("username", ["underwriter", "medical"])
def test_only_admin_can_add_staff(dev, username):
    """The built-in path had no role check, so anyone signed in could."""
    with TestClient(app) as client:
        sign_in(client, username)
        response = client.post(
            "/api/auth/users",
            json={
                "fullName": "Should Not Exist",
                "email": f"{uuid.uuid4().hex[:10]}@test.local",
                "password": "testpassword123",
                "role": "admin",
            },
        )
        assert response.status_code == 403, response.text


def test_session_dies_when_the_switch_is_turned_off(dev, monkeypatch):
    """A cookie issued during a demo must not outlive the setting."""
    with TestClient(app) as client:
        sign_in(client, "admin")
        assert client.get("/api/auth/me").status_code == 200

        monkeypatch.setattr(settings, "admin_password", "")
        assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_never_yields_a_session(dev):
    """A failed sign-in must fail, not quietly hand out access.

    With no database reachable the answer is 503 ("cannot reach the database"),
    and with one it is 401. Never 200, and never a cookie.
    """
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": "admin", "password": "wrong"})

        assert response.status_code in (401, 503), response.text
        assert COOKIE_NAME not in response.cookies


def test_unreachable_database_reports_503_not_500(dev):
    """A driver traceback as a 500 tells an operator nothing. This path is the
    likeliest failure at the demo, so it has to name the cause."""
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "someone@carrier.com", "password": "whatever"},
        )

        # 401 once a database is actually reachable; 503 while it is not.
        assert response.status_code in (401, 503), response.text
        if response.status_code == 503:
            assert "database" in response.json()["detail"].lower()


# ── with a database: the accounts are real enough to act ─────────────────────


def _built_in_rows() -> dict[str, tuple[str, str]]:
    """email -> (role, password_hash) for the rows behind the built-in accounts."""

    async def read() -> dict[str, tuple[str, str]]:
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models import User

        ids = [a.user_id for a in BUILT_IN_ACCOUNTS]
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
            return {u.email: (u.role.value, u.password_hash) for u in rows}

    return asyncio.run(read())


@needs_database
def test_signing_in_gives_all_three_accounts_a_real_row(dev):
    """A decision and an audit entry point at their author by foreign key. Only
    the old `admin` was ever seeded, so the other two could sign in but were
    refused the moment they decided anything."""
    with TestClient(app) as client:
        sign_in(client, "underwriter")

    rows = _built_in_rows()
    assert {email: role for email, (role, _) in rows.items()} == EXPECTED


@needs_database
def test_the_stored_password_cannot_be_used(dev, monkeypatch):
    """The rows hold the hash of a discarded random value. If they held the real
    password, clearing ADMIN_PASSWORD would not switch the accounts off: the
    ordinary database sign-in would still let them in."""
    with TestClient(app) as client:
        sign_in(client, "admin")

    for _, stored in _built_in_rows().values():
        assert verify_password("admin123", stored) is False

    monkeypatch.setattr(settings, "admin_password", "")
    with TestClient(app) as client:
        for username in EXPECTED:
            response = client.post(
                "/api/auth/login", json={"email": username, "password": "admin123"}
            )
            assert response.status_code == 401, (username, response.text)


@needs_database
def test_admin_adds_a_staff_account_that_can_really_sign_in(dev):
    """Adding staff from a built-in session used to append to a list in memory,
    so the new person appeared on screen and could never sign in."""
    email = f"{uuid.uuid4().hex[:12]}@test.local"
    try:
        with TestClient(app) as client:
            sign_in(client, "admin")
            created = client.post(
                "/api/auth/users",
                json={
                    "fullName": "New Medical Reviewer",
                    "email": email,
                    "password": "testpassword123",
                    "role": "medical_professional",
                },
            )
            assert created.status_code == 200, created.text
            assert email in [u["email"] for u in client.get("/api/auth/users").json()]

        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login", json={"email": email, "password": "testpassword123"}
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["role"] == "medical_professional"
            assert login.json()["tenant"]["id"] == str(ADMIN_TENANT_ID)
    finally:

        async def remove() -> None:
            from sqlalchemy import delete

            from app.db.session import AsyncSessionLocal
            from app.models import User

            async with AsyncSessionLocal() as db:
                await db.execute(delete(User).where(User.email == email))
                await db.commit()

        asyncio.run(remove())


# ── database url is assembled from the parts ─────────────────────────────────


def test_database_url_follows_db_host(monkeypatch):
    """Changing DB_HOST must be enough to point at another machine."""
    monkeypatch.setattr(settings, "db_host", "192.168.0.42")

    assert settings.database_url == (
        "postgresql+asyncpg://homelander:devpassword@192.168.0.42:5432/homelander"
    )
