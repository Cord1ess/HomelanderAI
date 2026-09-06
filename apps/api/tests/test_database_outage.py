"""What the dashboard does when the database machine is unreachable.

This is not a hypothetical: the database runs on a different laptop
(docs/DEMO_SETUP.md), so an outage is an ordinary operating condition. It was
found the hard way — pointing the app at a real, firewalled machine produced a
500 with an asyncpg stack trace on every screen, because only sign-in had been
guarded.

These tests need no database, which is the point: they describe behaviour when
there isn't one.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app

# Every read path a signed-in dashboard touches.
DATABASE_BACKED = [
    "/api/applications",
    "/api/notifications",
    f"/api/applications/{uuid.uuid4()}",
    f"/api/applications/{uuid.uuid4()}/audit",
    f"/api/files/{uuid.uuid4()}",
]


class _DeadSession:
    """A session that hands out the failure a real one does.

    Opening a session does not open a connection — SQLAlchemy connects on the
    first query. So the session must exist and its *queries* must fail, which is
    what lets sign-in reach the built-in admin check before touching the
    database at all. A fixture that failed at dependency-resolution time instead
    would test a situation that cannot occur.

    A firewalled host drops the packet rather than refusing the connection, so
    what surfaces is TimeoutError, not ConnectionRefusedError.
    """

    async def execute(self, *_, **__):
        raise TimeoutError

    async def get(self, *_, **__):
        raise TimeoutError

    async def commit(self):
        raise TimeoutError

    async def rollback(self):
        return None

    async def close(self):
        return None

    def add(self, _):
        return None


@pytest.fixture
def unreachable_database():
    async def dead_session():
        yield _DeadSession()

    app.dependency_overrides[get_db] = dead_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", DATABASE_BACKED)
def test_every_screen_answers_503_not_500(unreachable_database, path):
    """A 500 with a driver traceback tells an underwriter nothing and looks like
    the product is broken. 503 with a sentence tells them what to check."""
    with TestClient(app, raise_server_exceptions=False) as client:
        client.post("/api/auth/login", json={"email": "admin", "password": "admin123"})
        response = client.get(path)

    assert response.status_code == 503, f"{path} returned {response.status_code}"
    assert "database" in response.json()["detail"].lower()


def test_the_built_in_admin_still_signs_in(unreachable_database):
    """The whole reason that account exists."""
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/auth/login", json={"email": "admin", "password": "admin123"}
        )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "admin"


def test_the_model_catalogue_needs_no_database(unreachable_database):
    """It is read from the arm registry, so the intake form can still say which
    models exist even when nothing can be stored."""
    with TestClient(app, raise_server_exceptions=False) as client:
        client.post("/api/auth/login", json={"email": "admin", "password": "admin123"})
        response = client.get("/api/models")

    assert response.status_code == 200
    assert any(m["available"] for m in response.json())
