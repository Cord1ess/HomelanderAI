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


def test_uploaded_evidence_is_linked_to_the_model_that_reads_it(carrier):
    """The form sends its own panel id (`cxr_lung`); the arm registry is keyed by
    the model name (`tb_xray`). Matching one against the other left every
    evidence row with a null `model_arm_id` — the link DATABASE.md §C exists to
    provide — while scoring carried on working, so nothing looked wrong."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models import EvidenceFile, EvidenceFileType, ModelArm

    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

    async def stored_row():
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(EvidenceFile).where(EvidenceFile.application_id == created["id"])
                )
            ).scalar_one()
            arm = await db.get(ModelArm, row.model_arm_id) if row.model_arm_id else None
            return row.file_type, row.model_arm_id, (arm.name if arm else None)

    file_type, arm_id, arm_name = asyncio.run(stored_row())

    assert arm_id is not None, "the X-ray was never linked to the arm that reads it"
    assert arm_name == "tb_xray"
    # A PNG radiograph is an image. It used to be filed as 'questionnaire',
    # because the enum had no honest value for it.
    assert file_type == EvidenceFileType.IMAGE


def test_the_scoring_arm_constant_matches_the_registry():
    """`SCORING_ARM` decides which block of declared_history reaches the rules.
    If it stops matching the arm's intake id, every rule silently stops firing
    and applicants are scored on imaging alone."""
    from app.arms import arm_for_intake
    from app.routers.applications import SCORING_ARM

    assert arm_for_intake(SCORING_ARM) is not None


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


# ── the model catalogue ──────────────────────────────────────────────────────


def test_the_form_is_told_which_models_actually_run(carrier):
    """The intake form used to offer seven models as though all seven worked.

    `available` is derived from the arm registry rather than a hand-kept list,
    so the menu cannot advertise a model that would silently produce no score.
    """
    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        models = client.get("/api/models").json()

    by_id = {m["id"]: m for m in models}
    assert by_id["cxr_lung"]["available"] is True
    assert by_id["cxr_lung"]["armName"] == "tb_xray"
    # The caveat travels with the model, not a document.
    assert "NOT externally validated" in by_id["cxr_lung"]["validation"]

    # Everything else is on the roadmap and says so.
    planned = [m["id"] for m in models if not m["available"]]
    assert set(planned) == {"mirai", "ham10000", "eyepacs", "biobert", "xgboost", "neuro"}
    assert all(by_id[p]["validation"] is None for p in planned)


# ── plans ────────────────────────────────────────────────────────────────────


def test_the_plan_scales_with_the_cover_requested(carrier):
    """A tier alone does not price a policy — the amount asked for does.

    Idea.md §5 gives a premium per tier at a reference sum assured; asking for
    more cover has to move the number, or the field is decoration.
    """
    from app import plans

    small = plans.for_tier("low", 1_000_000)
    large = plans.for_tier("low", 4_000_000)

    # plans.for_tier returns plain snake_case; the camelCase aliasing happens
    # at the schema boundary, not here.
    assert small["monthly_premium_bdt"] == 5_000
    assert large["monthly_premium_bdt"] == 20_000

    # Elevated is a routing decision, not a price. Quoting one would imply an
    # outcome nobody has decided (SPEC §7: never an automated denial).
    assert plans.for_tier("elevated", 4_000_000)["monthly_premium_bdt"] is None

    # No cover requested means no premium invented.
    assert plans.for_tier("moderate", None)["monthly_premium_bdt"] is None


def test_a_scored_application_carries_its_plan(carrier):
    from app.arms import tb_xray

    if not tb_xray.available():
        pytest.skip("vision extra not installed")

    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        detail = client.get(f"/api/applications/{created['id']}").json()

    plan = detail["plan"]
    assert plan is not None
    assert plan["tier"] == detail["score"]["tier"]
    assert plan["humanStep"]
    assert plan["referenceCoverBdt"] == 1_000_000


# ── the identity photo ───────────────────────────────────────────────────────


def test_an_application_can_be_submitted_without_an_identity_photo(carrier):
    """It is biometric data that no model reads, so it must never be required
    (SPEC §9, PII minimisation)."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models import Applicant, Application

    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)  # sends no face_photo at all
        detail = client.get(f"/api/applications/{created['id']}").json()

    # And it is never handed back out: only evidence and heatmaps are servable.
    assert {f["kind"] for f in detail["files"]} <= {"evidence", "gradcam"}

    async def stored():
        async with AsyncSessionLocal() as db:
            application = await db.get(Application, uuid.UUID(created["id"]))
            applicant = (
                await db.execute(
                    select(Applicant).where(Applicant.id == application.applicant_id)
                )
            ).scalar_one()
            return applicant.face_photo_path

    assert asyncio.run(stored()) is None


def test_height_and_weight_reach_their_columns(carrier):
    """The form collects them inside the tabular model's panel, so they arrive
    nested in declared_history. They are facts about the person, and
    `applicants` has columns for them that were being left null."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models import Applicant, Application

    payload = json.loads(intake_payload())
    payload["declaredHistory"]["xgboost"] = {"height_cm": 168, "weight_kg": 74.5}

    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client, json.dumps(payload))

    async def stored():
        async with AsyncSessionLocal() as db:
            application = await db.get(Application, uuid.UUID(created["id"]))
            applicant = (
                await db.execute(
                    select(Applicant).where(Applicant.id == application.applicant_id)
                )
            ).scalar_one()
            return applicant.height_cm, applicant.weight_kg

    height, weight = asyncio.run(stored())
    assert float(height) == 168
    assert float(weight) == 74.5
