"""A client's portal sign-in can be made again after intake, and every email is logged."""

from fastapi.testclient import TestClient

from app import mailer
from app.main import app
from tests.conftest import needs_database
from tests.test_applications import sign_in
from tests.test_roles import an_application, skip_scoring  # noqa: F401  (fixture)

pytestmark = needs_database


def test_a_new_password_replaces_the_old_one(carrier, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    doctor, underwriter, admin, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}/client-sign-in"
    old = created["portal"]

    with TestClient(app) as client:
        sign_in(client, admin)
        page = client.get(url).json()
        assert page["portalId"] == old["portalId"]
        assert page["mailConfigured"] is False
        made = client.post(url, json={"sendEmail": True})
        assert made.status_code == 200, made.text
        fresh = made.json()
        # No address and no mail server: shown once, to hand over.
        assert fresh["emailed"] is False and fresh["password"]

    with TestClient(app) as client:
        assert client.post("/api/portal/login", json=old).status_code == 401
        new = {"portalId": old["portalId"], "password": fresh["password"]}
        assert client.post("/api/portal/login", json=new).status_code == 200


def test_a_corrected_address_is_tried_and_logged(carrier, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    _, _, admin, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}/client-sign-in"
    with TestClient(app) as client:
        sign_in(client, admin)
        bad = client.post(url, json={"email": "not-an-address"})
        assert bad.status_code == 422
        r = client.post(url, json={"email": "Client@Example.com", "sendEmail": True}).json()
        assert r["email"] == "client@example.com"
        # Mail is not set up, so it was not sent; the log says so and the
        # password is shown instead.
        assert r["emails"][0]["status"] == "not_configured"
        assert r["password"]


def test_a_sent_email_hides_the_password(carrier, monkeypatch):
    monkeypatch.setattr(mailer, "send", lambda *a, **k: True)
    _, _, admin, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}/client-sign-in"
    with TestClient(app) as client:
        sign_in(client, admin)
        r = client.post(url, json={"email": "client@example.com"}).json()
        assert r["emailed"] is True and r["password"] is None
        assert r["emails"][0]["status"] == "sent"


def test_an_underwriter_sees_the_details_masked_and_a_doctor_not_at_all(carrier, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    doctor, underwriter, admin, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}/client-sign-in"
    with TestClient(app) as client:
        sign_in(client, admin)
        client.post(url, json={"email": "client@example.com", "sendEmail": False})
    with TestClient(app) as client:
        sign_in(client, underwriter)
        page = client.get(url).json()
        assert page["detailsVisible"] is False
        assert page["email"] != "client@example.com" and page["email"].endswith("@example.com")
        assert "•" in page["portalId"]
        # They can still make a new one to hand over, whole.
        made = client.post(url, json={"sendEmail": False}).json()
        assert made["portalId"] == created["portal"]["portalId"] and made["password"]
    with TestClient(app) as client:
        sign_in(client, doctor)
        assert client.get(url).status_code == 403
