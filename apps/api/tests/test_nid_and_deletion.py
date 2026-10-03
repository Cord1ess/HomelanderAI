"""Reading NID cards, what intake now requires, and deleting a client's data."""

import asyncio
import importlib.util
import io
import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import mailer, nid
from app.main import app
from tests.conftest import needs_database
from tests.test_applications import a_chest_xray, eligible_payload, intake_payload, sign_in
from tests.test_roles import an_application, skip_scoring  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[3]


def _specimen_png(name: str, born: date, number: str) -> bytes:
    """A SPECIMEN card drawn by scripts/make_nid_specimens.py."""
    spec = importlib.util.spec_from_file_location(
        "make_nid_specimens", ROOT / "scripts" / "make_nid_specimens.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buffer = io.BytesIO()
    module.specimen(name, born, number).save(buffer, format="PNG")
    return buffer.getvalue()


# ── reading the card ─────────────────────────────────────────────────────────


def test_the_three_fields_are_found_in_the_cards_lines():
    reading = nid.parse(
        [
            "Government of the People's Republic of Bangladesh",
            "National ID Card",
            "Name",
            "MD. KARIM HOSSAIN",
            "Date of Birth 23 Nov 1965",
            "ID NO 616 411 7598",
        ]
    )
    assert reading.number == "6164117598"
    assert reading.name == "Md. Karim Hossain"
    assert reading.date_of_birth == date(1965, 11, 23)
    assert reading.missing == []


def test_an_old_seventeen_digit_card_and_a_misread_zero():
    reading = nid.parse(
        ["Name: Abdul Malek", "Date of Birth: 30-01-1956", "NID NO 1956269O512345678"]
    )
    assert reading.number == "19562690512345678"
    assert reading.date_of_birth == date(1956, 1, 30)
    assert reading.name == "Abdul Malek"


def test_what_is_not_found_is_said():
    reading = nid.parse(["something", "unreadable"])
    assert set(reading.missing) == {"ID number", "date of birth", "name"}


def test_names_are_compared_loosely():
    assert nid.name_matches("FATEMA BEGUM", "Fatema Begum")
    assert nid.name_matches("Md. Karim Hossain", "Karim Hossain")
    assert not nid.name_matches("Fatema Begum", "Rahim Uddin")


@pytest.mark.skipif(not nid.available(), reason="OCR not installed")
def test_a_specimen_card_is_read_by_the_ocr():
    raw = _specimen_png("Fatema Begum", date(1974, 7, 2), "5271866900")
    reading = nid.read(raw)
    assert reading.number == "5271866900"
    assert reading.name == "Fatema Begum"
    assert reading.date_of_birth == date(1974, 7, 2)


# ── intake ───────────────────────────────────────────────────────────────────


def _post(client, payload: str, **files):
    return client.post(
        "/api/applications",
        data={"payload": payload, "file_arms": ["cxr_lung"], "file_kinds": ["chest_xray"]},
        files={"files": ("xray.png", a_chest_xray(), "image/png"), **files},
    )


@needs_database
def test_intake_needs_consent_and_a_nominee_for_life(carrier):
    account = asyncio.run(carrier())
    body = json.loads(eligible_payload())
    with TestClient(app) as client:
        sign_in(client, account)
        no_consent = {**body, "applicant": {**body["applicant"], "consent": False}}
        r = _post(client, json.dumps(no_consent))
        assert r.status_code == 422 and "agree" in r.json()["detail"]
        no_nominee = {**body, "applicant": {**body["applicant"], "nomineeName": ""}}
        r = _post(client, json.dumps(no_nominee))
        assert r.status_code == 422 and "nominee" in r.json()["detail"]


@needs_database
@pytest.mark.skipif(not nid.available(), reason="OCR not installed")
def test_the_card_is_read_stored_and_an_nid_is_taken_once(carrier):
    account = asyncio.run(carrier())
    number = str(uuid.uuid4().int)[:10]
    card = _specimen_png("Test Applicant", date(1980, 1, 15), number)
    with TestClient(app) as client:
        sign_in(client, account)
        read = client.post("/api/nid/read", files={"image": ("card.png", card, "image/png")})
        assert read.status_code == 200, read.text
        assert read.json()["number"] == number

        body = json.loads(eligible_payload())
        body["applicant"].update(
            {"nidNumber": number, "nidName": "Test Applicant", "nidDateOfBirth": "1980-01-15"}
        )
        r = _post(client, json.dumps(body), nid_image=("card.png", card, "image/png"))
        assert r.status_code == 201, r.text
        detail = client.get(f"/api/applications/{r.json()['id']}").json()
        assert detail["applicant"]["nidNumber"] == number
        # The same person cannot be taken twice.
        again = _post(client, json.dumps(body))
        assert again.status_code == 409 and r.json()["reference"] in again.json()["detail"]


# ── deleting a client's data ─────────────────────────────────────────────────


def _portal(created) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/portal/login", json=created["portal"]).status_code == 200
    return client


@needs_database
def test_a_client_asks_the_owner_approves_and_the_data_is_gone(carrier, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    _, underwriter, admin, created = an_application(carrier, "moderate", "48.00")

    with _portal(created) as client:
        me = client.post(
            "/api/portal/deletion-request", json={"reason": "I applied elsewhere."}
        ).json()
        assert me["deletion"]["status"] == "pending"
        assert me["deletion"]["deleteOn"] == str(date.fromordinal(date.today().toordinal() + 30))
        assert client.post("/api/portal/deletion-request", json={}).status_code == 409

    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.get("/api/deletion-requests").status_code == 403
    with TestClient(app) as client:
        sign_in(client, admin)
        told = [
            n
            for n in client.get("/api/notifications").json()
            if n["notificationType"] == "deletion_requested"
        ]
        assert told
        [request] = client.get("/api/deletion-requests").json()
        assert request["reason"] == "I applied elsewhere."
        decide = f"/api/deletion-requests/{request['id']}/decision"
        r = client.post(decide, json={"approve": True, "now": True})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["applicant"]["name"] == "Deleted client"
        assert detail["applicant"]["phone"] == "—"
        assert detail["declaredHistory"] == {}

    # They can no longer sign in: the sign-in itself was erased.
    with TestClient(app) as client:
        assert client.post("/api/portal/login", json=created["portal"]).status_code == 401


@needs_database
def test_a_policy_in_force_stops_the_deletion_and_a_decline_needs_a_reason(carrier, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    _, underwriter, admin, created = an_application(carrier, "low", "12.00")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(
            f"/api/applications/{created['id']}/decision", json={"decision": "confirmed_fast_track"}
        )
    with _portal(created) as client:
        client.post("/api/portal/deletion-request", json={})
    with TestClient(app) as client:
        sign_in(client, admin)
        [request] = client.get("/api/deletion-requests").json()
        assert any("in force" in b for b in request["blockers"])
        decide = f"/api/deletion-requests/{request['id']}/decision"
        assert client.post(decide, json={"approve": True}).status_code == 409
        assert client.post(decide, json={"approve": False}).status_code == 422
        r = client.post(decide, json={"approve": False, "reason": "Your policy is still running."})
        assert r.json()["status"] == "declined"
    with _portal(created) as client:
        me = client.get("/api/portal/me").json()
        assert me["deletion"]["status"] == "declined"
        assert me["deletion"]["declineReason"] == "Your policy is still running."


@needs_database
def test_a_client_can_change_their_mind(carrier, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    _, _, _, created = an_application(carrier, "moderate", "48.00")
    with _portal(created) as client:
        client.post("/api/portal/deletion-request", json={})
        assert (
            client.delete("/api/portal/deletion-request").json()["deletion"]["status"]
            == "withdrawn"
        )
        assert client.delete("/api/portal/deletion-request").status_code == 409


def test_the_default_applicant_is_still_the_scoring_tests_one():
    """The scoring tests rely on a 68-year-old; intake_payload must not drift."""
    assert json.loads(intake_payload())["applicant"]["dateOfBirth"] == "1958-04-11"
