"""Built-in `admin` / `admin123` sign-in.

This account bypasses the database, so the tests that matter most are the ones
proving it stays off outside development.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.routers.auth import COOKIE_NAME, _is_admin_login


@pytest.fixture
def dev(monkeypatch):
    """Development, with the shipped defaults."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "admin123")
    return settings


# ── the guards ───────────────────────────────────────────────────────────────


def test_off_outside_development(monkeypatch):
    """The one check that stops this reaching a real deployment."""
    monkeypatch.setattr(settings, "admin_password", "admin123")

    for environment in ("production", "staging", "prod", ""):
        monkeypatch.setattr(settings, "environment", environment)
        assert settings.admin_login_enabled is False
        assert _is_admin_login("admin", "admin123") is False


def test_off_when_password_cleared(monkeypatch):
    """Clearing the password is the manual off switch — and empty must never
    mean 'any password'."""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_password", "")

    assert settings.admin_login_enabled is False
    assert _is_admin_login("admin", "") is False
    assert _is_admin_login("admin", "anything") is False


def test_wrong_password_rejected(dev):
    for wrong in ("admin", "admin1234", "Admin123", "", "admin12"):
        assert _is_admin_login("admin", wrong) is False


def test_wrong_username_rejected(dev):
    assert _is_admin_login("administrator", "admin123") is False
    assert _is_admin_login("root", "admin123") is False


def test_username_is_case_and_space_insensitive(dev):
    assert _is_admin_login("ADMIN", "admin123") is True
    assert _is_admin_login("  admin  ", "admin123") is True


def test_correct_credentials_accepted(dev):
    assert _is_admin_login("admin", "admin123") is True


# ── end to end, with no database ─────────────────────────────────────────────


def test_signs_in_and_stays_signed_in_without_a_database(dev):
    """The whole point: no database is touched, so this holds even when the
    database machine is unreachable."""
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", json={"email": "admin", "password": "admin123"}
        )
        assert login.status_code == 200, login.text

        body = login.json()
        assert body["user"]["email"] == "admin"
        assert body["user"]["role"] == "admin"
        assert COOKIE_NAME in login.cookies

        # The follow-up call is where a database lookup would otherwise happen.
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["user"]["email"] == "admin"


def test_session_dies_when_the_switch_is_turned_off(dev, monkeypatch):
    """A cookie issued during a demo must not outlive the setting."""
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"email": "admin", "password": "admin123"})
        assert client.get("/api/auth/me").status_code == 200

        monkeypatch.setattr(settings, "admin_password", "")
        assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_never_yields_a_session(dev):
    """A failed sign-in must fail, not quietly hand out access.

    With no database reachable the answer is 503 ("cannot reach the database"),
    and with one it is 401. Never 200, and never a cookie.
    """
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login", json={"email": "admin", "password": "wrong"}
        )

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


# ── database url is assembled from the parts ─────────────────────────────────


def test_database_url_follows_db_host(monkeypatch):
    """Changing DB_HOST must be enough to point at another machine."""
    monkeypatch.setattr(settings, "db_host", "192.168.0.42")

    assert settings.database_url == (
        "postgresql+asyncpg://homelander:devpassword@192.168.0.42:5432/homelander"
    )
