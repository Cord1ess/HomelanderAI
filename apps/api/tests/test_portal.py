"""The client portal.

Two properties matter more than the rest. An applicant must never be shown a
risk score or a model finding. And the portal sign-in must be a different thing
from a staff session in both directions, so neither can be used as the other.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import mailer
from app.main import app
from app.routers import applications, portal
from tests.conftest import needs_database
from tests.test_applications import a_chest_xray, intake_payload, sign_in

pytestmark = needs_database

# Nothing clinical may appear anywhere in what the applicant receives.
FORBIDDEN_KEYS = {
    "crs", "score", "tier", "findings", "probability", "contribution",
    "adjustments", "visionScore", "thresholds", "modelInfo",
}


def submit_with_email(client: TestClient, email: str | None = "client@example.com") -> dict:
    body = json.loads(intake_payload())
    if email:
        body["applicant"]["email"] = email
    response = client.post(
        "/api/applications",
        data={"payload": json.dumps(body), "file_arms": ["cxr_lung"], "file_kinds": ["chest_xray"]},
        files={"files": ("xray.png", a_chest_xray(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def keys_in(value) -> set[str]:
    """Every key at every depth of a JSON value."""
    if isinstance(value, dict):
        found = set(value)
        for inner in value.values():
            found |= keys_in(inner)
        return found
    if isinstance(value, list):
        return set().union(*(keys_in(v) for v in value)) if value else set()
    return set()


@pytest.fixture
def real_scoring():
    """Ask for this to have the X-ray actually scored after submission."""


@pytest.fixture(autouse=True)
def skip_scoring(request, monkeypatch):
    """Do not score the X-ray unless a test asks for `real_scoring`.

    Scoring takes about 15 seconds on a CPU and runs inside the request under
    TestClient. Almost nothing here depends on its result: the portal shows
    status, dates, documents and the recorded decision, none of which need a
    score to exist. The one test that checks the plan lookup opts back in.
    """
    if "real_scoring" in request.fixturenames:
        return

    async def not_scored(application_id):
        return None

    monkeypatch.setattr(applications, "score_application", not_scored)


@pytest.fixture
def sent(monkeypatch):
    """Capture mail instead of sending it, and report it as delivered."""
    outbox: list[dict] = []

    def fake_send(to, subject, body, *, redact=None):
        outbox.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(mailer, "send", fake_send)
    return outbox


# ── credentials at intake ────────────────────────────────────────────────────


def test_without_mail_the_operator_is_handed_the_credentials(carrier, monkeypatch):
    """No mail server: the client is in the room, so the operator gets the
    sign-in to hand over. It is the one time the password exists in a response."""
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit_with_email(client)

    portal = created["portal"]
    assert portal["portalId"].startswith("HC-")
    assert portal["emailed"] is False
    assert portal["password"], "the operator must be given the password to hand over"


def test_with_mail_the_password_never_appears_on_screen(carrier, sent):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit_with_email(client, "client@example.com")

    portal = created["portal"]
    assert portal["emailed"] is True
    assert portal["password"] is None

    message = next(m for m in sent if m["to"] == "client@example.com")
    assert portal["portalId"] in message["body"]
    assert created["reference"] in message["subject"]


def test_the_password_is_never_written_to_the_log(carrier, monkeypatch, caplog):
    """With mail unconfigured the message is logged, but a generated password in
    a log file is a credential leak whether or not anything was sent."""
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    account = asyncio.run(carrier())

    with caplog.at_level("INFO"), TestClient(app) as client:
        sign_in(client, account)
        created = submit_with_email(client)

    password = created["portal"]["password"]
    assert password
    # The message was logged, so this is not passing because nothing was written.
    assert created["portal"]["portalId"] in caplog.text
    assert password not in caplog.text


def test_portal_ids_do_not_follow_the_reference_sequence(carrier, monkeypatch):
    """The HL- reference is a sequence and known to staff, which is exactly why
    it is not the login name."""
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        first = submit_with_email(client)["portal"]["portalId"]
        second = submit_with_email(client)["portal"]["portalId"]

    assert first != second
    assert not first.startswith("HL-")


# ── sign-in ──────────────────────────────────────────────────────────────────


def make_applicant(carrier, monkeypatch) -> tuple[dict, dict]:
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit_with_email(client)
    return account, created


def test_an_applicant_can_sign_in_and_see_their_application(carrier, monkeypatch):
    _, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    with TestClient(app) as client:
        login = client.post(
            "/api/portal/login",
            json={"portalId": creds["portalId"], "password": creds["password"]},
        )
        assert login.status_code == 200, login.text
        assert login.json()["reference"] == created["reference"]

        me = client.get("/api/portal/me")
        assert me.status_code == 200
        body = me.json()
        assert body["reference"] == created["reference"]
        assert body["stageLabel"]
        assert body["expectedBy"] is not None


def test_wrong_credentials_are_refused_without_saying_which_part(carrier, monkeypatch):
    _, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    with TestClient(app) as client:
        wrong_password = client.post(
            "/api/portal/login", json={"portalId": creds["portalId"], "password": "nope"}
        )
        unknown_id = client.post(
            "/api/portal/login", json={"portalId": "HC-ZZZZZZZZ", "password": creds["password"]}
        )

    assert wrong_password.status_code == unknown_id.status_code == 401
    # The same words, so the response does not confirm which ids exist.
    assert wrong_password.json()["detail"] == unknown_id.json()["detail"]


def test_the_portal_needs_a_session():
    with TestClient(app) as client:
        assert client.get("/api/portal/me").status_code == 401


# ── the narrow response ──────────────────────────────────────────────────────


def test_the_applicant_never_sees_a_score_or_a_finding(carrier, monkeypatch, real_scoring):
    """The point of the narrow schema. The models are not diagnostic, and a
    clinical impression delivered by an insurance portal with no clinician
    present is not something to hand anyone."""
    account, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    # Decide it, so the offer path (which reads the tier internally) is exercised.
    with TestClient(app) as client:
        sign_in(client, account)
        client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "approved_with_adjustment", "finalPremium": 9000},
        )

    with TestClient(app) as client:
        body = client.post(
            "/api/portal/login",
            json={"portalId": creds["portalId"], "password": creds["password"]},
        ).json()

    leaked = keys_in(body) & FORBIDDEN_KEYS
    assert not leaked, f"clinical detail reached the applicant: {sorted(leaked)}"
    assert body["offer"]["outcome"] == "Approved with an adjusted premium"
    assert body["offer"]["planName"] == "Standard with adjustment"
    assert float(body["offer"]["monthlyPremiumBdt"]) == 9000


def test_the_offer_follows_the_decision_not_the_models_tier(carrier, monkeypatch):
    """Plans map one-to-one to tiers, so a plan looked up from the tier is the
    risk score under another name. The offer has to come from what the
    underwriter decided: a fast-track is the standard plan at the standard rate
    for the cover asked for, whatever the model thought."""
    account, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    with TestClient(app) as client:
        sign_in(client, account)
        client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "confirmed_fast_track"},
        )

    with TestClient(app) as client:
        offer = client.post(
            "/api/portal/login",
            json={"portalId": creds["portalId"], "password": creds["password"]},
        ).json()["offer"]

    assert offer["outcome"] == "Approved at the standard rate"
    assert offer["planName"] == "Standard"
    # The standard rate is 5,000 a month per 1,000,000 of cover; this asks for 500,000.
    assert float(offer["monthlyPremiumBdt"]) == 2500


def test_the_portal_does_not_read_the_scores_table():
    """The guarantee behind the two tests above. If this module never touches
    scores or findings, no later edit to the response can leak one."""
    for name in ("CompositeScore", "SubScore", "ModelRun", "ExplanationArtifact", "RiskTier"):
        assert not hasattr(portal, name), f"the portal router now imports {name}"


def test_requested_documents_reach_the_applicant_in_the_underwriters_words(carrier, monkeypatch):
    account, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    with TestClient(app) as client:
        sign_in(client, account)
        client.post(
            f"/api/applications/{created['id']}/evidence-request",
            json={"items": ["A chest X-ray taken within the last 6 months"]},
        )

    with TestClient(app) as client:
        body = client.post(
            "/api/portal/login",
            json={"portalId": creds["portalId"], "password": creds["password"]},
        ).json()

    assert body["stage"] == "waiting_on_you"
    assert body["documents"][0]["description"] == "A chest X-ray taken within the last 6 months"
    assert body["documents"][0]["received"] is False
    # Waiting on the applicant is never reported to them as the carrier being late.
    assert body["overdue"] is False


def test_an_escalation_is_not_presented_as_a_refusal(carrier, monkeypatch):
    account, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    with TestClient(app) as client:
        sign_in(client, account)
        client.post(f"/api/applications/{created['id']}/escalate", json={})

    with TestClient(app) as client:
        body = client.post(
            "/api/portal/login",
            json={"portalId": creds["portalId"], "password": creds["password"]},
        ).json()

    assert body["stage"] == "senior_review"
    assert body["offer"] is None
    assert "not a refusal" in body["stageDetail"]


# ── the two sign-ins are not interchangeable ─────────────────────────────────


def test_a_portal_token_cannot_be_used_as_a_staff_session(carrier, monkeypatch):
    """Different cookies, but the claim is the real boundary: a portal token
    pasted into the staff cookie must still be refused."""
    _, created = make_applicant(carrier, monkeypatch)
    creds = created["portal"]

    with TestClient(app) as client:
        client.post(
            "/api/portal/login",
            json={"portalId": creds["portalId"], "password": creds["password"]},
        )
        portal_token = client.cookies.get("portal_token")
        assert portal_token

        # Its own cookie does not open the console.
        assert client.get("/api/applications").status_code == 401

        # Nor does pasting it where a staff token goes.
        client.cookies.set("session_token", portal_token)
        assert client.get("/api/applications").status_code == 401
        assert client.get(f"/api/applications/{created['id']}").status_code == 401


def test_a_staff_token_cannot_be_used_as_a_portal_session(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        staff_token = client.cookies.get("session_token")
        assert client.get("/api/portal/me").status_code == 401

        client.cookies.set("portal_token", staff_token)
        assert client.get("/api/portal/me").status_code == 401


def test_each_applicant_sees_only_their_own_application(carrier, monkeypatch):
    """There is no application id in any portal URL, so there is nothing to
    tamper with; this proves the pinning holds."""
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        first = submit_with_email(client, "one@example.com")
        second = submit_with_email(client, "two@example.com")

    for mine, other in ((first, second), (second, first)):
        with TestClient(app) as client:
            body = client.post(
                "/api/portal/login",
                json={
                    "portalId": mine["portal"]["portalId"],
                    "password": mine["portal"]["password"],
                },
            ).json()
            assert body["reference"] == mine["reference"]
            assert other["reference"] not in json.dumps(body)

        # And one applicant's password does not open the other's portal.
        with TestClient(app) as client:
            crossed = client.post(
                "/api/portal/login",
                json={
                    "portalId": other["portal"]["portalId"],
                    "password": mine["portal"]["password"],
                },
            )
            assert crossed.status_code == 401


# ── the decision notice ──────────────────────────────────────────────────────


def test_a_decision_emails_a_notice_that_carries_no_outcome(carrier, sent):
    """Email is not a confidential channel, so the message says only that there
    is something to see."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit_with_email(client, "client@example.com")
        sent.clear()
        client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "approved_with_adjustment", "finalPremium": 9000},
        )

    notice = next(m for m in sent if "update" in m["subject"].lower())
    assert notice["to"] == "client@example.com"
    for word in ("approved", "premium", "9000", "9,000", "declin", "elevated"):
        assert word not in notice["body"].lower()
