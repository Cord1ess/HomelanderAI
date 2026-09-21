"""When an applicant is told to expect an answer.

The pure arithmetic is tested on its own; the endpoints against a database.
"""

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import turnaround
from app.main import app
from tests.conftest import needs_database
from tests.test_applications import sign_in, submit

# ── business-day arithmetic, no database ─────────────────────────────────────

MON = date(2026, 9, 21)
FRI = date(2026, 9, 25)
SAT = date(2026, 9, 26)
SUN = date(2026, 9, 27)


def test_weekdays_count_straight_through():
    assert turnaround.add_business_days(MON, 2) == date(2026, 9, 23)


def test_a_friday_submission_skips_the_weekend():
    """Two working days from Friday is Tuesday, not Sunday. This is the whole
    reason the unit is business days."""
    assert turnaround.add_business_days(FRI, 2) == date(2026, 9, 29)


def test_a_weekend_submission_counts_from_monday():
    assert turnaround.add_business_days(SAT, 1) == date(2026, 9, 29)
    assert turnaround.add_business_days(SUN, 1) == date(2026, 9, 29)


def test_zero_days_is_the_same_working_day():
    assert turnaround.add_business_days(MON, 0) == MON
    # Except that a weekend has no working day of its own.
    assert turnaround.add_business_days(SAT, 0) == date(2026, 9, 28)


def test_negative_days_are_refused():
    with pytest.raises(ValueError):
        turnaround.add_business_days(MON, -1)


def test_overdue_only_while_the_carrier_holds_the_case():
    past = date(2026, 9, 20)
    today = date(2026, 9, 22)

    assert turnaround.is_overdue(past, "scored", today) is True
    assert turnaround.is_overdue(past, "processing", today) is True
    # Finished: nothing to be late for.
    assert turnaround.is_overdue(past, "decided", today) is False
    # Waiting on the applicant: their delay, not the carrier's.
    assert turnaround.is_overdue(past, "awaiting_evidence", today) is False
    # No estimate was ever given.
    assert turnaround.is_overdue(None, "scored", today) is False
    # Due today is not yet overdue.
    assert turnaround.is_overdue(today, "scored", today) is False


# ── the endpoints ────────────────────────────────────────────────────────────


@needs_database
def test_submit_sets_the_expected_date_from_the_carrier_default(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        detail = client.get(f"/api/applications/{created['id']}").json()

    assert detail["expectedBy"] is not None
    expected = turnaround.add_business_days(date.today(), turnaround.DEFAULT_BUSINESS_DAYS)
    assert detail["expectedBy"] == expected.isoformat()
    assert detail["overdue"] is False
    assert detail["expectedByNote"] is None


@needs_database
def test_an_underwriter_can_revise_the_date_with_a_reason(carrier):
    account = asyncio.run(carrier())
    later = (date.today() + timedelta(days=10)).isoformat()

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        response = client.patch(
            f"/api/applications/{created['id']}/turnaround",
            json={"expectedBy": later, "reason": "Waiting on the radiology report."},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["expectedBy"] == later
        assert body["expectedByNote"] == "Waiting on the radiology report."

        # The queue carries the same date, so late cases can be spotted there.
        items = client.get("/api/applications").json()["items"]
        row = next(i for i in items if i["id"] == created["id"])
        assert row["expectedBy"] == later

        trail = client.get(f"/api/applications/{created['id']}/audit").json()
        revised = next(e for e in trail["entries"] if e["eventType"] == "turnaround_revised")
        assert revised["payload"]["to"] == later
        assert revised["payload"]["reason"] == "Waiting on the radiology report."
        assert revised["actorName"] == "Test Underwriter"


@needs_database
def test_a_revision_needs_a_reason_and_a_future_date(carrier):
    """A date that moves with no explanation is the silent slip this exists
    to replace."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        url = f"/api/applications/{created['id']}/turnaround"

        soon = (date.today() + timedelta(days=3)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # No reason at all.
        assert client.patch(url, json={"expectedBy": soon}).status_code == 422
        # A reason too short to mean anything.
        assert client.patch(url, json={"expectedBy": soon, "reason": "x"}).status_code == 422
        # A date already gone.
        assert (
            client.patch(url, json={"expectedBy": yesterday, "reason": "Backdated."}).status_code
            == 422
        )


@needs_database
def test_the_carrier_default_is_admin_only_and_does_not_move_existing_promises(carrier):
    """Changing the company default applies to future applicants. One already
    told 'by Wednesday' keeps Wednesday."""
    underwriter = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, underwriter)
        created = submit(client)
        before = client.get(f"/api/applications/{created['id']}").json()["expectedBy"]

        # A senior underwriter is not an admin.
        forbidden = client.patch("/api/tenant/settings", json={"turnaroundBusinessDays": 5})
        assert forbidden.status_code == 403
        assert client.get("/api/tenant/settings").json()["turnaroundBusinessDays"] == 2

    # The seeded admin@dev.local is an admin of Tenant A. Use the built-in
    # admin instead, whose tenant is also seeded, so this does not depend on
    # Tenant A's state.
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": "admin", "password": "admin123"})
        assert login.status_code == 200
        response = client.patch("/api/tenant/settings", json={"turnaroundBusinessDays": 5})
        assert response.status_code == 200, response.text
        assert response.json()["turnaroundBusinessDays"] == 5
        # Bounds are enforced.
        for out_of_range in (0, 31):
            body = {"turnaroundBusinessDays": out_of_range}
            assert client.patch("/api/tenant/settings", json=body).status_code == 422
        # Put it back so the demo tenant is left as it was found.
        client.patch("/api/tenant/settings", json={"turnaroundBusinessDays": 2})

    with TestClient(app) as client:
        sign_in(client, underwriter)
        after = client.get(f"/api/applications/{created['id']}").json()["expectedBy"]
    assert after == before
