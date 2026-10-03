"""Company settings: tier boundaries and pricing policy, per company.

Three things have to hold. Only an administrator can change them and every
change is recorded with who and from what. The boundaries cannot be crossed,
however they are sent. And a change reaches the places that use it: a new
score is tiered with the company's boundaries, and every price on every screen
comes from the company's policy, while nothing already scored moves.
"""

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import mailer
from app.core.security import hash_password
from app.main import app
from app.routers import applications
from tests.conftest import needs_database
from tests.test_applications import a_chest_xray, intake_payload, sign_in

pytestmark = needs_database

# apps/api/tests -> repo root
DEMO_NORMAL = Path(__file__).resolve().parents[3] / "data" / "demo" / "01-normal"


@pytest.fixture
def real_scoring():
    """Ask for this to have the X-ray actually scored after submission."""


@pytest.fixture(autouse=True)
def skip_scoring(request, monkeypatch):
    """Scoring takes ~15 s on a CPU; only the test that checks tiering needs it."""
    if "real_scoring" in request.fixturenames:
        return

    async def not_scored(application_id):
        return None

    monkeypatch.setattr(applications, "score_application", not_scored)


@pytest.fixture(autouse=True)
def no_mail(monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")


def add_admin(tenant_id: uuid.UUID) -> dict:
    """An administrator in the throwaway tenant, beside the fixture's user."""

    async def make() -> dict:
        from app.db.session import AsyncSessionLocal
        from app.models import User, UserRole

        email = f"{uuid.uuid4().hex[:12]}@test.local"
        async with AsyncSessionLocal() as db:
            db.add(
                User(
                    tenant_id=tenant_id,
                    full_name="Test Administrator",
                    email=email,
                    password_hash=hash_password("testpassword123"),
                    role=UserRole.ADMIN,
                )
            )
            await db.commit()
        return {"email": email, "password": "testpassword123"}

    return asyncio.run(make())


def submit(client: TestClient, payload: str | None = None) -> dict:
    response = client.post(
        "/api/applications",
        data={
            "payload": payload or json.dumps(json.loads(intake_payload())),
            "file_arms": ["cxr_lung"],
            "file_kinds": ["chest_xray"],
        },
        files={"files": ("xray.png", a_chest_xray(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ── who may change what ──────────────────────────────────────────────────────


def test_defaults_are_the_constants_the_code_used_to_have(carrier):
    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        s = client.get("/api/tenant/settings").json()
    assert (s["tierLowMax"], s["tierModerateMax"]) == (30, 65)
    # The pricing assumptions default to IDRA's limits for non-participating
    # life plans, and the hospital rate to the market's.
    assert s["lifeExpenseLoadingPct"] == 22.32
    assert s["lifeInterestPct"] == 5.0
    assert s["healthRatePerLakhBdt"] == 1800


def test_only_an_administrator_can_change_settings(carrier):
    underwriter = asyncio.run(carrier(role="underwriter"))
    with TestClient(app) as client:
        sign_in(client, underwriter)
        response = client.patch("/api/tenant/settings", json={"tierLowMax": 25})
        assert response.status_code == 403
        assert client.get("/api/tenant/settings").json()["tierLowMax"] == 30


def test_a_change_is_recorded_with_who_and_from_what(carrier):
    medical = asyncio.run(carrier())
    admin = add_admin(medical["tenant_id"])
    with TestClient(app) as client:
        sign_in(client, admin)
        response = client.patch(
            "/api/tenant/settings",
            json={"tierLowMax": 25, "healthRatePerLakhBdt": 2000},
        )
        assert response.status_code == 200, response.text
        assert response.json()["tierLowMax"] == 25
        assert response.json()["healthRatePerLakhBdt"] == 2000
        # Untouched fields are untouched.
        assert response.json()["tierModerateMax"] == 65

        history = client.get("/api/tenant/settings/history").json()
    assert len(history) == 1
    assert history[0]["actorName"] == "Test Administrator"
    assert history[0]["changes"] == {
        "tier_low_max": {"from": 30, "to": 25},
        "health_rate_per_lakh_bdt": {"from": 1800, "to": 2000},
    }


def test_sending_the_same_value_records_nothing(carrier):
    medical = asyncio.run(carrier())
    admin = add_admin(medical["tenant_id"])
    with TestClient(app) as client:
        sign_in(client, admin)
        assert client.patch("/api/tenant/settings", json={"tierLowMax": 30}).status_code == 200
        assert client.get("/api/tenant/settings/history").json() == []


# ── the boundaries cannot be crossed ─────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"tierLowMax": 70},  # above the stored moderate boundary
        {"tierModerateMax": 20},  # below the stored low boundary
        {"tierLowMax": 50, "tierModerateMax": 50},  # equal
        {"tierLowMax": 60, "tierModerateMax": 40},  # reversed
    ],
)
def test_crossed_boundaries_are_refused(carrier, body):
    medical = asyncio.run(carrier())
    admin = add_admin(medical["tenant_id"])
    with TestClient(app) as client:
        sign_in(client, admin)
        response = client.patch("/api/tenant/settings", json=body)
        assert response.status_code == 422, response.text
        assert "below" in response.json()["detail"]
        s = client.get("/api/tenant/settings").json()
        assert (s["tierLowMax"], s["tierModerateMax"]) == (30, 65)


@pytest.mark.parametrize(
    "body",
    [
        {"tierLowMax": 0},
        {"tierModerateMax": 100},
        {"healthRatePerLakhBdt": 0},
        # IDRA caps the expense loading at 22.32% and the interest at 5%.
        {"lifeExpenseLoadingPct": 30},
        {"lifeInterestPct": 8},
        {},
    ],
)
def test_out_of_range_and_empty_changes_are_refused(carrier, body):
    medical = asyncio.run(carrier())
    admin = add_admin(medical["tenant_id"])
    with TestClient(app) as client:
        sign_in(client, admin)
        assert client.patch("/api/tenant/settings", json=body).status_code == 422


# ── the change reaches the places that use it ────────────────────────────────


def test_prices_everywhere_follow_the_policy(carrier):
    """The pricing screen, the quote and the policy an approval issues all read
    the company's assumptions, not the defaults."""
    medical = asyncio.run(carrier())
    admin = add_admin(medical["tenant_id"])

    with TestClient(app) as client:
        sign_in(client, admin)
        before = client.post(
            "/api/quote",
            json={"product": "health", "sumAssuredBdt": 200000, "age": 30},
        ).json()
        client.patch("/api/tenant/settings", json={"healthRatePerLakhBdt": 2400})
        after = client.post(
            "/api/quote",
            json={"product": "health", "sumAssuredBdt": 200000, "age": 30},
        ).json()
        assert before["annualBdt"] == 3600
        assert after["annualBdt"] == 4800
        examples = client.get("/api/pricing").json()["examples"]
        assert any(e["product"] == "health" and e["annualBdt"] == 4800 for e in examples)

        from tests.test_applications import eligible_payload

        created = submit(client, eligible_payload(coverage={
            "coverageType": "Health", "coverageAmount": 200000, "policyTerm": "1"
        }))
        client.post(
            f"/api/applications/{created['id']}/decision", json={"decision": "confirmed_fast_track"}
        )
        policy = client.get(f"/api/applications/{created['id']}").json()["policy"]
    # Forty-six is in the 46-55 band (1.9 times the base rate), and the test
    # client declared smoking (50% more).
    assert float(policy["annualPremiumBdt"]) == 2400 * 2 * 1.9 * 1.5

def test_a_new_score_is_tiered_with_the_companys_boundaries(carrier, real_scoring):
    """Score once with the defaults, then set the boundaries either side of that
    score so the same image lands in the moderate tier. The score records the
    boundaries it was tiered with, so changing them afterwards moves nothing."""
    # The synthetic test image scores a flat 100, which no boundary below 100
    # can bracket, so this one test uses a real radiograph from the local demo
    # set (gitignored; see docs/DEMO_SETUP.md) and skips without it.
    demo = sorted(DEMO_NORMAL.glob("*.png")) if DEMO_NORMAL.is_dir() else []
    if not demo:
        pytest.skip("no demo X-ray in data/demo/01-normal; run the demo setup to enable this test")
    image = demo[0].read_bytes()

    medical = asyncio.run(carrier())
    admin = add_admin(medical["tenant_id"])
    no_history = json.loads(intake_payload(declaredHistory={}))

    def submit_plain(client: TestClient) -> dict:
        response = client.post(
            "/api/applications",
            data={
                "payload": json.dumps(no_history),
                "file_arms": ["cxr_lung"],
                "file_kinds": ["chest_xray"],
            },
            files={"files": ("xray.png", image, "image/png")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    with TestClient(app) as client:
        sign_in(client, admin)
        first = client.get(f"/api/applications/{submit_plain(client)['id']}").json()
        assert first["status"] == "scored", first
        crs = first["score"]["crs"]
        assert first["score"]["thresholds"] == {"low_max": 30.0, "moderate_max": 65.0}
        if not 1 < crs < 99:
            pytest.skip(f"the demo image scores {crs}; no boundaries can bracket it")

        low, moderate = round(crs - 0.5, 2), round(crs + 0.5, 2)
        changed = client.patch(
            "/api/tenant/settings", json={"tierLowMax": low, "tierModerateMax": moderate}
        )
        assert changed.status_code == 200, changed.text

        second = client.get(f"/api/applications/{submit_plain(client)['id']}").json()
        assert second["score"]["tier"] == "moderate", second["score"]
        assert second["score"]["thresholds"] == {"low_max": low, "moderate_max": moderate}
        # The first score kept the boundaries it was tiered with.
        again = client.get(f"/api/applications/{first['id']}").json()
        assert again["score"]["thresholds"] == {"low_max": 30.0, "moderate_max": 65.0}

        # And changing the boundaries back does not touch the second score.
        client.patch("/api/tenant/settings", json={"tierLowMax": 30, "tierModerateMax": 65})
        later = client.get(f"/api/applications/{second['id']}").json()
        assert later["score"]["tier"] == "moderate"
        assert later["score"]["thresholds"] == {"low_max": low, "moderate_max": moderate}
