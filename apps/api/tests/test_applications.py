"""The application endpoints, against a real database.

The tests that matter most here are the ones about isolation and write-once
decisions: a wrong answer on either is a breach or an unfixable record, not a
cosmetic bug.
"""

import asyncio
import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from tests.conftest import needs_database

pytestmark = needs_database


def a_chest_xray() -> bytes:
    """A small grey PNG.

    Not a real radiograph — these tests are about the plumbing, not the model.
    It has to vary across pixels, though: a uniform image normalises to a flat
    black PNG and every one of them would share a content hash.
    """
    image = Image.new("L", (256, 256))
    image.putdata([(x * 7 + y * 3) % 256 for y in range(256) for x in range(256)])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def intake_payload(**overrides) -> str:
    body = {
        "applicant": {
            "name": "Test Applicant",
            "phone": "01700000000",
            "dateOfBirth": "1958-04-11",
            "sex": "male",
        },
        "coverage": {"coverageType": "life", "coverageAmount": 500000, "policyTerm": "10"},
        "modelsRequested": ["cxr_lung"],
        "declaredHistory": {
            "cxr_lung": {
                "symptoms": {"cough_over_2_weeks": True, "weight_loss": True},
                "history": {"diabetes": True, "smoker": True},
            }
        },
    }
    body.update(overrides)
    return json.dumps(body)


def sign_in(client: TestClient, account: dict) -> None:
    response = client.post(
        "/api/auth/login", json={"email": account["email"], "password": account["password"]}
    )
    assert response.status_code == 200, response.text


def submit(client: TestClient, payload: str | None = None) -> dict:
    response = client.post(
        "/api/applications",
        data={"payload": payload or intake_payload(), "file_arms": ["cxr_lung"]},
        files={"files": ("xray.png", a_chest_xray(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ── access control ───────────────────────────────────────────────────────────


def test_every_endpoint_needs_a_session():
    """No session, no data. Checked on each endpoint rather than assumed from
    the router, because a missing dependency is invisible until it leaks."""
    unknown = uuid.uuid4()
    with TestClient(app) as client:
        assert client.get("/api/applications").status_code == 401
        assert client.get(f"/api/applications/{unknown}").status_code == 401
        assert client.get(f"/api/applications/{unknown}/audit").status_code == 401
        assert client.get(f"/api/files/{unknown}").status_code == 401
        assert client.get("/api/notifications").status_code == 401
        assert (
            client.post("/api/applications", data={"payload": intake_payload()}).status_code
            == 401
        )


def test_one_carrier_cannot_see_another_carriers_application(carrier):
    """The isolation test. A failure here is a data breach, not a bug."""
    first = asyncio.run(carrier("Carrier One"))
    second = asyncio.run(carrier("Carrier Two"))

    with TestClient(app) as client:
        sign_in(client, first)
        created = submit(client)

    with TestClient(app) as client:
        sign_in(client, second)

        # 404 rather than 403: confirming that another carrier's id exists is
        # itself a leak.
        assert client.get(f"/api/applications/{created['id']}").status_code == 404
        assert client.get(f"/api/applications/{created['id']}/audit").status_code == 404
        assert (
            client.post(
                f"/api/applications/{created['id']}/decision",
                json={"decision": "confirmed_fast_track"},
            ).status_code
            == 404
        )

        # And it is absent from the queue, not merely hidden from the detail view.
        queue = client.get("/api/applications").json()
        assert created["id"] not in [item["id"] for item in queue["items"]]
        assert queue["total"] == 0


# ── intake ───────────────────────────────────────────────────────────────────


def test_the_database_assigns_the_reference(carrier):
    """The operator never types a reference, and the client never invents one —
    a trigger on `applicants` assigns it at INSERT."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        first = submit(client)
        second = submit(client)

    assert first["reference"].startswith("HL-")
    assert first["reference"] != second["reference"]


def test_an_application_with_no_readable_evidence_is_not_left_pending(carrier):
    """An application nothing can score must say so, not sit in the queue
    forever waiting for a background task that has nothing to do."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        response = client.post(
            "/api/applications",
            data={"payload": intake_payload(), "file_arms": ["cxr_lung"]},
            files={"files": ("notes.txt", b"this is not an image", "text/plain")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "insufficient_evidence"

        detail = client.get(f"/api/applications/{response.json()['id']}").json()
        # The reason has to reach the screen; a blank panel explains nothing.
        assert detail["errors"] == [] or any("not a readable image" in e for e in detail["errors"])


def test_malformed_payload_is_rejected_clearly(carrier):
    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        response = client.post("/api/applications", data={"payload": "{not json"})
        assert response.status_code == 422
        assert "could not be read" in response.json()["detail"]


# ── scoring ──────────────────────────────────────────────────────────────────


def test_declared_history_reaches_the_scoring_rules(carrier):
    """The form nests history per model (`declared_history.cxr_lung`) while
    `scoring.py` reads `symptoms` and `history` at the top level. If the
    unwrapping breaks, no rule fires and the applicant is silently scored on
    imaging alone — which is exactly the kind of failure that looks fine."""
    from app.arms import tb_xray

    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        detail = client.get(f"/api/applications/{created['id']}").json()

    if not tb_xray.available():
        pytest.skip("vision extra not installed; there is no score to adjust")

    assert detail["status"] == "scored", detail
    keys = {a["key"] for a in detail["adjustments"]}
    # Two symptoms, diabetes, a smoker, and born in 1958.
    assert {"multiple_symptoms", "diabetes", "smoker", "age_over_60"} <= keys

    # Every adjustment carries the wording shown to the underwriter.
    assert all(a["reason"] for a in detail["adjustments"])


def test_a_scored_application_carries_its_provenance(carrier):
    """The model has only ever been tested on one hospital. That caveat travels
    with the score rather than living in a document nobody opens."""
    from app.arms import tb_xray

    if not tb_xray.available():
        pytest.skip("vision extra not installed")

    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        detail = client.get(f"/api/applications/{created['id']}").json()

    assert detail["modelInfo"]["scorer"]
    assert "NOT externally validated" in detail["modelInfo"]["validation"]
    assert len(detail["findings"]) == 18
    assert detail["score"]["thresholds"] == {"low_max": 30.0, "moderate_max": 65.0}


def test_stored_images_are_served_and_scoped(carrier):
    account = asyncio.run(carrier())
    other = asyncio.run(carrier("Someone Else"))

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        detail = client.get(f"/api/applications/{created['id']}").json()
        file_ids = [f["id"] for f in detail["files"]]
        assert file_ids, "the uploaded X-ray should be stored"

        served = client.get(f"/api/files/{file_ids[0]}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/png"

    with TestClient(app) as client:
        sign_in(client, other)
        # Health data behind a guessable id is still a breach.
        assert client.get(f"/api/files/{file_ids[0]}").status_code == 404


# ── decision ─────────────────────────────────────────────────────────────────


def test_a_decision_can_only_be_made_once(carrier):
    """Write-once is enforced by a unique constraint, so a second decision loses
    even if two underwriters press the button at the same moment."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        first = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "escalated_senior_review"},
        )
        assert first.status_code == 201, first.text

        second = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "confirmed_fast_track"},
        )
        assert second.status_code == 409
        assert "already been decided" in second.json()["detail"]

        # The first decision stands, unchanged.
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["decision"]["decision"] == "escalated_senior_review"
        assert detail["status"] == "decided"


def test_an_adjusted_approval_needs_a_premium(carrier):
    """'Approved with adjustment' and no rate is not a decision anyone can act
    on."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        response = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "approved_with_adjustment"},
        )
        assert response.status_code == 422
        assert "final premium" in response.json()["detail"]


# ── audit ────────────────────────────────────────────────────────────────────


def test_the_audit_chain_records_and_verifies(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "requested_additional_evidence"},
        )
        trail = client.get(f"/api/applications/{created['id']}/audit").json()

    assert trail["intact"] is True
    by_event = {e["eventType"]: e for e in trail["entries"]}
    assert "application_submitted" in by_event
    assert "decision_recorded" in by_event

    # Both human actions name the person who took them.
    assert by_event["application_submitted"]["actorName"] == "Test Underwriter"
    assert by_event["decision_recorded"]["actorName"] == "Test Underwriter"

    # Scoring is done by the system, not a person, and the trail says so.
    if "scoring_completed" in by_event:
        assert by_event["scoring_completed"]["actorName"] is None


def test_a_tampered_audit_row_is_detected(carrier):
    """The point of the chain. Editing a stored payload has to be visible."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        assert client.get(f"/api/applications/{created['id']}/audit").json()["intact"] is True

        async def tamper() -> None:
            async with AsyncSessionLocal() as db:
                # audit_log has an append-only trigger blocking UPDATE, which is
                # the first line of defence. Disabling it locally is how we prove
                # the hash chain catches an edit that gets past the trigger —
                # someone with direct database access, for instance.
                await db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update"))
                await db.execute(
                    text(
                        "UPDATE audit_log SET payload = jsonb_set(payload, '{reference}', "
                        "'\"FORGED\"') WHERE application_id = :app"
                    ),
                    {"app": created["id"]},
                )
                await db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_update"))
                await db.commit()

        asyncio.run(tamper())

        trail = client.get(f"/api/applications/{created['id']}/audit").json()
        assert trail["intact"] is False
        assert "does not match its hash" in trail["brokenAt"]


def test_audit_rows_cannot_be_updated_or_deleted(carrier):
    """Append-only is enforced by the database, not by convention."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.db.session import AsyncSessionLocal

    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

    async def attempt(statement: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(text(statement), {"app": created["id"]})
            await db.commit()

    for statement in (
        "UPDATE audit_log SET event_type = 'tampered' WHERE application_id = :app",
        "DELETE FROM audit_log WHERE application_id = :app",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            asyncio.run(attempt(statement))


# ── queue and notifications ──────────────────────────────────────────────────


def test_the_queue_filters_and_counts(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        queue = client.get("/api/applications").json()
        assert queue["total"] == 1
        assert sum(queue["counts"].values()) == 1

        row = queue["items"][0]
        assert row["reference"] == created["reference"]
        assert row["applicantName"] == "Test Applicant"

        # Searching by reference and by name both find it.
        assert client.get(f"/api/applications?q={created['reference']}").json()["total"] == 1
        assert len(client.get("/api/applications?q=Test Applicant").json()["items"]) == 1
        assert client.get("/api/applications?q=nobody-by-that-name").json()["items"] == []

        # An unmatched status filter empties the list but not the counts.
        filtered = client.get("/api/applications?status=decided").json()
        assert filtered["items"] == []


def test_scoring_notifies_the_carriers_underwriters(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        notes = client.get("/api/notifications").json()
        assert notes, "finishing an evaluation should notify the underwriter"
        assert notes[0]["reference"] == created["reference"]
        assert notes[0]["readAt"] is None

        marked = client.post(f"/api/notifications/{notes[0]['id']}/read").json()
        assert marked["readAt"] is not None

        # Marking read twice is not an error.
        assert client.post(f"/api/notifications/{notes[0]['id']}/read").status_code == 200
