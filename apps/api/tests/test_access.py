"""Who sees a client's details, who sees the company's book, and what the owner may do.

The administrator owns the company: every client, analytics, plans and pricing,
and a doctor's work as well as an underwriter's. An underwriter or a doctor
sees a client's name and reference and asks for the rest, with a reason.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import needs_database
from tests.test_applications import sign_in
from tests.test_roles import an_application, skip_scoring  # noqa: F401  (fixture)

pytestmark = needs_database


def notices(client: TestClient, kind: str) -> list[dict]:
    return [n for n in client.get("/api/notifications").json() if n["notificationType"] == kind]


def test_an_underwriter_sees_a_name_not_the_details(carrier):
    _, underwriter, _, _ = an_application(carrier, "moderate", "48.00")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        [row] = client.get("/api/clients").json()
        assert row["name"] and row["reference"].startswith("HL-")
        assert row["access"] == "none"
        assert row["phone"] is None and row["email"] is None and row["portalId"] is None
        assert client.get(f"/api/clients/{row['id']}").status_code == 403
        # Searching by phone would confirm a detail they were not given.
        assert client.get("/api/clients", params={"q": "01700000000"}).json() == []


def test_asking_with_a_reason_and_the_owner_approving(carrier):
    _, underwriter, admin, _ = an_application(carrier, "moderate", "48.00")

    with TestClient(app) as client:
        sign_in(client, underwriter)
        [row] = client.get("/api/clients").json()
        url = f"/api/clients/{row['id']}/access-requests"
        assert client.post(url, json={"reason": ""}).status_code == 422
        asked = client.post(url, json={"reason": "Need their phone to arrange the medical."})
        assert asked.status_code == 201, asked.text
        assert asked.json()["status"] == "pending"
        # Once is enough.
        assert client.post(url, json={"reason": "Asking again."}).status_code == 409
        assert client.get("/api/clients").json()[0]["access"] == "pending"
        # Only the owner answers.
        decide = f"/api/access-requests/{asked.json()['id']}/decision"
        assert client.post(decide, json={"approve": True}).status_code == 403

    with TestClient(app) as client:
        sign_in(client, admin)
        [told] = notices(client, "access_requested")
        assert "arrange the medical" in told["message"]
        [pending] = client.get("/api/access-requests").json()
        assert pending["reason"] == "Need their phone to arrange the medical."
        assert pending["requesterRole"] == "Underwriter"
        approved = client.post(decide, json={"approve": True})
        assert approved.status_code == 200, approved.text
        assert approved.json()["expiresAt"]
        assert client.post(decide, json={"approve": False}).status_code == 409

    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert notices(client, "access_decided")
        [row] = client.get("/api/clients").json()
        assert row["access"] == "granted" and row["accessUntil"]
        assert row["phone"] == "01700000000"
        assert client.get(f"/api/clients/{row['id']}").status_code == 200


def test_a_declined_request_keeps_the_details_hidden(carrier):
    _, underwriter, admin, _ = an_application(carrier, "moderate", "48.00")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        [row] = client.get("/api/clients").json()
        url = f"/api/clients/{row['id']}/access-requests"
        asked = client.post(url, json={"reason": "Curious."}).json()
    with TestClient(app) as client:
        sign_in(client, admin)
        client.post(f"/api/access-requests/{asked['id']}/decision", json={"approve": False})
    with TestClient(app) as client:
        sign_in(client, underwriter)
        [row] = client.get("/api/clients").json()
        assert row["access"] == "declined" and row["phone"] is None
        assert client.get(f"/api/clients/{row['id']}").status_code == 403
        # They may ask again, with a better reason.
        assert client.post(url, json={"reason": "To book the follow-up."}).status_code == 201


def test_a_doctor_asks_too_and_only_about_their_own_patients(carrier):
    doctor, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        [row] = client.get("/api/clients").json()
    url = f"/api/clients/{row['id']}/access-requests"
    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.post(url, json={"reason": "To call them."}).status_code == 404
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"/api/applications/{created['id']}/escalate", json={})
    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.post(url, json={"reason": "To call them."}).status_code == 201


def test_the_owner_sees_every_client_without_asking(carrier):
    _, _, admin, _ = an_application(carrier, "moderate", "48.00")
    with TestClient(app) as client:
        sign_in(client, admin)
        [row] = client.get("/api/clients").json()
        assert row["access"] == "full" and row["phone"] == "01700000000"
        assert client.get(f"/api/clients/{row['id']}").status_code == 200
        assert (
            client.post(
                f"/api/clients/{row['id']}/access-requests", json={"reason": "Just because."}
            ).status_code
            == 409
        )


@pytest.mark.parametrize("path", ["/api/analytics", "/api/pricing"])
def test_analytics_and_pricing_are_the_owners(carrier, path):
    doctor, underwriter, admin, _ = an_application(carrier, "moderate", "48.00")
    for account, expected in ((underwriter, 403), (doctor, 403), (admin, 200)):
        with TestClient(app) as client:
            sign_in(client, account)
            assert client.get(path).status_code == expected, (account, path)


def test_the_owner_may_do_a_doctors_work(carrier):
    _, underwriter, admin, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/escalate", json={})
    with TestClient(app) as client:
        sign_in(client, admin)
        r = client.post(f"{url}/doctor-review", json={"verdict": "accurate"})
        assert r.status_code == 200, r.text
        r = client.post(
            f"{url}/client-message", json={"urgency": "routine", "message": "All clear."}
        )
        assert r.status_code == 200, r.text


def test_the_owner_may_decide_while_a_doctor_has_it(carrier):
    _, underwriter, admin, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/escalate", json={})
        body = {"decision": "approved_with_adjustment", "finalPremium": 12000}
        assert client.post(f"{url}/decision", json=body).status_code == 409
    with TestClient(app) as client:
        sign_in(client, admin)
        assert client.post(f"{url}/decision", json=body).status_code == 201


def test_access_is_per_company(carrier):
    _, underwriter, _, _ = an_application(carrier, "moderate", "48.00")
    other_admin = asyncio.run(carrier("Another Carrier"))
    with TestClient(app) as client:
        sign_in(client, underwriter)
        [row] = client.get("/api/clients").json()
        client.post(f"/api/clients/{row['id']}/access-requests", json={"reason": "For the file."})
    with TestClient(app) as client:
        sign_in(client, other_admin)
        assert client.get("/api/access-requests").json() == []
