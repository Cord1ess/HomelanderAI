"""Smoke tests for the scaffold.

Kept deliberately small — their job is to prove the app boots and the test
harness works, so the next person has a pattern to copy.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["uptime_seconds"] >= 0


def test_openapi_schema_is_served() -> None:
    """The frontend generates its TypeScript types from this document."""
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
