"""What each staff role may do.

The underwriter decides the policy. An elevated case goes to a doctor first;
the doctor checks the readers' results, returns them as accurate or
inaccurate, and may write to the client directly — but never decides the
policy. A doctor sees only what was sent to a doctor. Every rule here is the
API's, not just the screen's: a request sent directly must be refused too.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.main import app
from app.routers import applications
from tests.conftest import needs_database
from tests.test_applications import a_chest_xray, eligible_payload, sign_in

pytestmark = needs_database


@pytest.fixture(autouse=True)
def skip_scoring(monkeypatch):
    """The tier is set by hand below, so the 15-second X-ray scoring is not needed."""

    async def not_scored(application_id):
        return None

    monkeypatch.setattr(applications, "score_application", not_scored)


def add_user(tenant_id: uuid.UUID, role: str) -> dict:
    """Another account in the carrier's tenant, with the given role."""

    async def make() -> dict:
        from app.db.session import AsyncSessionLocal
        from app.models import User, UserRole

        email = f"{uuid.uuid4().hex[:12]}@test.local"
        async with AsyncSessionLocal() as db:
            db.add(
                User(
                    tenant_id=tenant_id,
                    full_name=f"Test {role}",
                    email=email,
                    password_hash=hash_password("testpassword123"),
                    role=UserRole(role),
                )
            )
            await db.commit()
        return {"email": email, "password": "testpassword123"}

    return asyncio.run(make())


def add_underwriter(tenant_id: uuid.UUID) -> dict:
    return add_user(tenant_id, "underwriter")


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


def submit(client: TestClient, coverage: dict | None = None) -> dict:
    response = client.post(
        "/api/applications",
        data={
            "payload": eligible_payload(**({"coverage": coverage} if coverage else {})),
            "file_arms": ["cxr_lung"],
            "file_kinds": ["chest_xray"],
        },
        files={"files": ("xray.png", a_chest_xray(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def an_application(
    carrier, tier: str, crs: str, coverage: dict | None = None
) -> tuple[dict, dict, dict, dict]:
    """(doctor, underwriter, admin, application) in one throwaway tenant."""
    admin = asyncio.run(carrier())
    underwriter = add_underwriter(admin["tenant_id"])
    doctor = add_user(admin["tenant_id"], "medical_professional")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        created = submit(client, coverage)
    set_tier(admin["tenant_id"], created["id"], tier, crs)
    return doctor, underwriter, admin, created


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "confirmed_fast_track"},
        {"decision": "approved_with_adjustment", "ratingPct": 50},
    ],
)
def test_an_underwriter_cannot_approve_an_elevated_case_a_doctor_has_not_seen(carrier, body):
    _, underwriter, _, created = an_application(carrier, "elevated", "82.00")

    with TestClient(app) as client:
        sign_in(client, underwriter)
        refused = client.post(f"/api/applications/{created['id']}/decision", json=body)
        assert refused.status_code == 403, refused.text
        assert "doctor" in refused.json()["detail"]

        # Refused means nothing was written: the case is still open.
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["decision"] is None
        assert detail["status"] != "decided"


def test_the_doctor_checks_the_results_and_the_underwriter_decides(carrier):
    """The whole hand-over: sent to a doctor, checked, returned with a verdict,
    then decided by the underwriter — who could not approve it before."""
    doctor, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"

    with TestClient(app) as client:
        sign_in(client, underwriter)
        # Sending through the decision endpoint is refused: it is not a decision.
        assert (
            client.post(f"{url}/decision", json={"decision": "escalated_senior_review"}).status_code
            == 422
        )

        sent = client.post(f"{url}/escalate", json={"note": "Please look at the apex."})
        assert sent.status_code == 200, sent.text
        assert sent.json()["status"] == "escalated"
        assert sent.json()["sentToDoctorAt"] is not None
        assert client.post(f"{url}/escalate", json={}).status_code == 409

        # While a doctor has it, nobody decides.
        waiting = client.post(f"{url}/decision", json={"decision": "confirmed_fast_track"})
        assert waiting.status_code == 409
        assert "doctor" in waiting.json()["detail"]

    with TestClient(app) as client:
        sign_in(client, doctor)
        notes = client.get("/api/notifications").json()
        assert any(
            n["notificationType"] == "tier_escalation"
            and "apex" in n["message"]
            and "check the results" in n["message"]
            for n in notes
        ), notes

        # The doctor does not decide the policy, whatever the tier.
        no = client.post(
            f"{url}/decision", json={"decision": "approved_with_adjustment", "ratingPct": 50}
        )
        assert no.status_code == 403
        assert "underwriter" in no.json()["detail"]

        returned = client.post(
            f"{url}/doctor-review", json={"verdict": "accurate", "note": "Consistent with TB."}
        )
        assert returned.status_code == 200, returned.text
        body = returned.json()
        assert body["status"] == "scored"
        assert body["doctorReviews"][0]["verdict"] == "accurate"
        assert body["doctorReviews"][0]["note"] == "Consistent with TB."
        # Returned once; a second verdict needs it sent again.
        assert client.post(f"{url}/doctor-review", json={"verdict": "accurate"}).status_code == 409

    with TestClient(app) as client:
        sign_in(client, underwriter)
        told = client.get("/api/notifications").json()
        assert any(
            n["notificationType"] == "doctor_reviewed" and "accurate" in n["message"] for n in told
        ), told

        queue = client.get("/api/applications").json()["items"]
        assert next(i for i in queue if i["id"] == created["id"])["doctorVerdict"] == "accurate"

        decided = client.post(
            f"{url}/decision", json={"decision": "approved_with_adjustment", "ratingPct": 50}
        )
        assert decided.status_code == 201, decided.text
        assert client.get(url).json()["status"] == "decided"


def test_an_inaccurate_verdict_is_tagged_as_such(carrier):
    doctor, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/escalate", json={})
    with TestClient(app) as client:
        sign_in(client, doctor)
        r = client.post(
            f"{url}/doctor-review",
            json={"verdict": "inaccurate", "note": "Old scarring, not active."},
        )
        assert r.status_code == 200, r.text
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.get(url).json()["doctorReviews"][0]["verdict"] == "inaccurate"


def test_a_verdict_must_be_one_of_the_two(carrier):
    doctor, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/escalate", json={})
    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.post(f"{url}/doctor-review", json={"verdict": "maybe"}).status_code == 422


def test_only_a_doctor_returns_a_verdict_or_writes_to_the_client(carrier):
    _, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/escalate", json={})
        assert client.post(f"{url}/doctor-review", json={"verdict": "accurate"}).status_code == 403
        assert (
            client.post(
                f"{url}/client-message", json={"urgency": "urgent", "message": "See a doctor."}
            ).status_code
            == 403
        )


def test_a_doctor_sees_only_what_was_sent_to_a_doctor(carrier):
    doctor, underwriter, _, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}"

    with TestClient(app) as client:
        sign_in(client, doctor)
        # Not sent: as if it did not exist.
        assert client.get(url).status_code == 404
        assert client.get("/api/applications").json()["items"] == []
        assert client.get("/api/clients").json() == []

    with TestClient(app) as client:
        sign_in(client, underwriter)
        files = client.get(url).json()["files"]
        client.post(f"{url}/escalate", json={})

    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.get(url).status_code == 200
        assert [i["id"] for i in client.get("/api/applications").json()["items"]] == [created["id"]]
        clients = client.get("/api/clients").json()
        assert len(clients) == 1
        # The profile needs an administrator's yes first (test_access.py).
        assert client.get(f"/api/clients/{clients[0]['id']}").status_code == 403
        assert client.get(f"/api/files/{files[0]['id']}").status_code == 200


def test_a_doctor_hears_only_about_what_was_sent_to_a_doctor(carrier):
    doctor, underwriter, _, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}"

    with TestClient(app) as client:
        sign_in(client, underwriter)
        asked = client.post(f"{url}/evidence-request", json={"items": ["A recent chest film"]})
        assert asked.status_code in (200, 201), asked.text
        assert client.get("/api/notifications").json(), "the underwriters are told"

    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.get("/api/notifications").json() == []

    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post(f"{url}/escalate", json={}).status_code == 200

    with TestClient(app) as client:
        sign_in(client, doctor)
        told = client.get("/api/notifications").json()
        assert [n["notificationType"] for n in told] == ["tier_escalation"], told


def test_a_doctor_cannot_see_an_unsent_file_or_client(carrier):
    doctor, underwriter, _, created = an_application(carrier, "low", "12.00")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        files = client.get(f"/api/applications/{created['id']}").json()["files"]
        client_id = client.get("/api/clients").json()[0]["id"]
    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.get(f"/api/files/{files[0]['id']}").status_code == 404
        assert client.get(f"/api/clients/{client_id}").status_code == 404


def test_a_doctor_does_not_take_applications_or_see_analytics(carrier):
    doctor, *_ = an_application(carrier, "low", "12.00")
    with TestClient(app) as client:
        sign_in(client, doctor)
        taken = client.post(
            "/api/applications",
            data={
                "payload": eligible_payload(),
                "file_kinds": ["chest_xray"],
            },
            files={"files": ("xray.png", a_chest_xray(), "image/png")},
        )
        assert taken.status_code == 403
        assert client.get("/api/analytics").status_code == 403


def test_a_doctor_writes_to_the_client_and_the_portal_shows_it(carrier):
    """For what cannot wait for the policy. The client reads the doctor's words
    and nothing else — never a score."""
    doctor, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/escalate", json={})
    with TestClient(app) as client:
        sign_in(client, doctor)
        sent = client.post(
            f"{url}/client-message",
            json={"urgency": "urgent", "message": "Please see a chest physician this week."},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["clientMessages"][0]["urgency"] == "urgent"
        # Writing to the client does not return the case: the verdict still does that.
        assert sent.json()["status"] == "escalated"

    with TestClient(app) as portal:
        login = portal.post(
            "/api/portal/login",
            json={
                "portalId": created["portal"]["portalId"],
                "password": created["portal"]["password"],
            },
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["messages"][0]["message"] == "Please see a chest physician this week."
        assert body["messages"][0]["urgency"] == "urgent"
        assert not any(k in body for k in ("crs", "tier", "score", "arms", "findings"))


def test_an_underwriter_approves_a_moderate_case_as_before(carrier):
    """The rule is about elevated cases only. Everything else is unchanged."""
    _, underwriter, _, created = an_application(carrier, "moderate", "48.00")

    with TestClient(app) as client:
        sign_in(client, underwriter)
        response = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "approved_with_adjustment", "ratingPct": 50},
        )
        assert response.status_code == 201, response.text
