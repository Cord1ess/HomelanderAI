"""What each staff role may decide.

An underwriter decides the cases the models call low or moderate. An elevated
case goes to a medical professional: the underwriter can escalate it but not
approve it. The review screen has always hidden the approve buttons, but the API
accepted the request anyway, so the rule only held for people who used the
screen.
"""

import asyncio
import json
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import app
from app.routers import applications
from tests.conftest import needs_database
from tests.test_applications import a_chest_xray, intake_payload, sign_in

pytestmark = needs_database


@pytest.fixture(autouse=True)
def skip_scoring(monkeypatch):
    """The tier is set by hand below, so the 15-second X-ray scoring is not needed."""

    async def not_scored(application_id):
        return None

    monkeypatch.setattr(applications, "score_application", not_scored)


def add_underwriter(tenant_id: uuid.UUID) -> dict:
    """A second account in the carrier's tenant, with the underwriter role."""

    async def make() -> dict:
        from app.db.session import AsyncSessionLocal
        from app.models import User, UserRole

        email = f"{uuid.uuid4().hex[:12]}@test.local"
        async with AsyncSessionLocal() as db:
            db.add(
                User(
                    tenant_id=tenant_id,
                    full_name="Test Junior Underwriter",
                    email=email,
                    password_hash=hash_password("testpassword123"),
                    role=UserRole.UNDERWRITER,
                )
            )
            await db.commit()
        return {"email": email, "password": "testpassword123"}

    return asyncio.run(make())


def set_tier(tenant_id: uuid.UUID, application_id: str, tier: str, crs: str) -> None:
    async def write() -> None:
        from app.db.session import AsyncSessionLocal
        from app.models import CompositeScore, RiskTier

        async with AsyncSessionLocal() as db:
            db.add(
                CompositeScore(
                    tenant_id=tenant_id,
                    application_id=uuid.UUID(application_id),
                    version=1,
                    crs_value=Decimal(crs),
                    tier=RiskTier(tier),
                )
            )
            await db.commit()

    asyncio.run(write())


def submit(client: TestClient) -> dict:
    response = client.post(
        "/api/applications",
        data={
            "payload": json.dumps(json.loads(intake_payload())),
            "file_arms": ["cxr_lung"],
            "file_kinds": ["chest_xray"],
        },
        files={"files": ("xray.png", a_chest_xray(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def an_application(carrier, tier: str, crs: str) -> tuple[dict, dict, dict]:
    """(medical professional, underwriter, application) in one throwaway tenant."""
    medical = asyncio.run(carrier())
    underwriter = add_underwriter(medical["tenant_id"])
    with TestClient(app) as client:
        sign_in(client, medical)
        created = submit(client)
    set_tier(medical["tenant_id"], created["id"], tier, crs)
    return medical, underwriter, created


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "confirmed_fast_track"},
        {"decision": "approved_with_adjustment", "finalPremium": 9000},
    ],
)
def test_an_underwriter_cannot_approve_an_elevated_case(carrier, body):
    _, underwriter, created = an_application(carrier, "elevated", "82.00")

    with TestClient(app) as client:
        sign_in(client, underwriter)
        refused = client.post(f"/api/applications/{created['id']}/decision", json=body)
        assert refused.status_code == 403, refused.text
        assert "medical professional" in refused.json()["detail"]

        # Refused means nothing was written: the case is still open.
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["decision"] is None
        assert detail["status"] != "decided"


def test_an_underwriter_can_still_escalate_an_elevated_case(carrier):
    """Escalating is exactly what the underwriter is meant to do with one."""
    _, underwriter, created = an_application(carrier, "elevated", "82.00")

    with TestClient(app) as client:
        sign_in(client, underwriter)
        response = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "escalated_senior_review"},
        )
        assert response.status_code == 201, response.text


def test_a_medical_professional_can_approve_an_elevated_case(carrier):
    medical, _, created = an_application(carrier, "elevated", "82.00")

    with TestClient(app) as client:
        sign_in(client, medical)
        response = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "approved_with_adjustment", "finalPremium": 12000},
        )
        assert response.status_code == 201, response.text


def test_an_underwriter_approves_a_moderate_case_as_before(carrier):
    """The rule is about elevated cases only. Everything else is unchanged."""
    _, underwriter, created = an_application(carrier, "moderate", "48.00")

    with TestClient(app) as client:
        sign_in(client, underwriter)
        response = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "approved_with_adjustment", "finalPremium": 8000},
        )
        assert response.status_code == 201, response.text
