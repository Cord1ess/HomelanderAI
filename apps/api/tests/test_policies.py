"""An approval issues a policy; payments are recorded against it; only the owner cancels.

The schedule rules are tested on their own first: they are plain date
arithmetic, and a month-end mistake would show up as a premium due on a day
that does not exist.
"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app import policies as rules
from app.main import app
from tests.conftest import needs_database
from tests.test_applications import sign_in
from tests.test_roles import an_application, skip_scoring  # noqa: F401  (fixture)

# ── the schedule ─────────────────────────────────────────────────────────────


def test_a_month_on_from_the_31st_is_the_last_day_of_a_short_month():
    assert rules.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert rules.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert rules.add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert rules.end_date(date(2026, 10, 3), 10) == date(2036, 10, 3)


def test_the_term_comes_from_what_was_asked_for():
    assert rules.term_years("10") == 10
    assert rules.term_years("20 years") == 20
    assert rules.term_years(None) == rules.DEFAULT_TERM_YEARS
    assert rules.term_years("99") == 40


def test_unpaid_months_become_overdue_after_the_grace_period():
    start = date(2026, 1, 10)
    today = date(2026, 4, 1)
    due = rules.schedule(start, date(2036, 1, 10), Decimal(1000), {}, today)
    assert [i.status for i in due] == ["overdue", "overdue", "due", "upcoming"]
    assert due[-1].due_date == date(2026, 4, 10)


def test_a_paid_month_is_paid_and_the_next_one_is_due():
    start = date(2026, 1, 10)
    paid = {date(2026, 1, 10): (date(2026, 1, 10), "bkash")}
    due = rules.schedule(start, date(2027, 1, 10), Decimal(1000), paid, date(2026, 1, 20))
    assert [i.status for i in due] == ["paid", "upcoming"]
    summary = rules.summarise(due, 1)
    assert summary.paid_count == 1 and summary.next_due == date(2026, 2, 10)


def test_a_cancelled_policy_stops_falling_due():
    start = date(2026, 1, 10)
    due = rules.schedule(
        start,
        date(2036, 1, 10),
        Decimal(1000),
        {},
        date(2026, 6, 1),
        cancelled_on=date(2026, 3, 1),
    )
    assert [i.due_date for i in due] == [date(2026, 1, 10), date(2026, 2, 10)]


# ── with a database ──────────────────────────────────────────────────────────


def _approve(carrier):
    _, underwriter, admin, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        body = {"decision": "approved_with_adjustment", "finalPremium": 4200}
        assert client.post(f"{url}/decision", json=body).status_code == 201
        policy = client.get(url).json()["policy"]
    return underwriter, admin, created, policy


@needs_database
def test_an_approval_issues_a_policy_on_the_terms_asked_for(carrier):
    _, _, created, policy = _approve(carrier)
    assert policy["policyNumber"] == f"P-{created['reference']}"
    assert policy["status"] == "active"
    assert Decimal(policy["monthlyPremiumBdt"]) == 4200
    assert Decimal(policy["yearlyPremiumBdt"]) == 4200 * 12
    assert Decimal(policy["sumAssuredBdt"]) == 500000
    assert policy["termYears"] == 10
    assert policy["startDate"] == date.today().isoformat()
    # The first month falls due the day it starts.
    assert policy["installments"][0]["status"] == "due"
    assert policy["nextDue"] == date.today().isoformat()


@needs_database
def test_the_client_sees_their_policy_and_what_is_due(carrier):
    _, _, created, _ = _approve(carrier)
    with TestClient(app) as client:
        me = client.post("/api/portal/login", json=created["portal"]).json()
        assert me["policy"]["status"] == "active"
        assert Decimal(me["policy"]["monthlyPremiumBdt"]) == 4200
        assert me["policy"]["nextDue"] == date.today().isoformat()


@needs_database
def test_the_owner_records_a_payment_and_the_next_month_is_due(carrier):
    underwriter, admin, created, policy = _approve(carrier)
    url = f"/api/policies/{policy['id']}/payments"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post(url, json={"method": "bkash"}).status_code == 403
    with TestClient(app) as client:
        sign_in(client, admin)
        r = client.post(url, json={"method": "bkash", "reference": "TX123"})
        assert r.status_code == 201, r.text
        paid = r.json()
        assert paid["paidCount"] == 1
        assert paid["installments"][0]["status"] == "paid"
        assert paid["installments"][0]["method"] == "bkash"
        assert paid["nextDue"] == rules.add_months(date.today(), 1).isoformat()
        again = client.post(url, json={"dueDate": date.today().isoformat()})
        assert again.status_code == 409


@needs_database
def test_only_the_owner_cancels_and_the_client_sees_it(carrier):
    underwriter, admin, created, policy = _approve(carrier)
    url = f"/api/policies/{policy['id']}/cancel"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post(url, json={"reason": "Client asked."}).status_code == 403
    with TestClient(app) as client:
        sign_in(client, admin)
        assert client.post(url, json={"reason": "no"}).status_code == 422
        r = client.post(url, json={"reason": "The client asked to cancel."})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"
        assert r.json()["cancelReason"] == "The client asked to cancel."
        assert client.post(url, json={"reason": "Twice over."}).status_code == 409
        pay = client.post(f"/api/policies/{policy['id']}/payments", json={})
        assert pay.status_code == 409
        # It is on the client's profile, as cancelled.
        profile = client.get(f"/api/clients/{policy['clientId']}").json()
        assert profile["policies"][0]["status"] == "cancelled"
    with TestClient(app) as client:
        me = client.post("/api/portal/login", json=created["portal"]).json()
        assert me["policy"]["status"] == "cancelled"
        assert me["policy"]["nextDue"] is None


@needs_database
def test_the_owner_sees_premiums_in_and_payouts_owed(carrier):
    _, admin, _, _ = _approve(carrier)
    with TestClient(app) as client:
        sign_in(client, admin)
        money = client.get("/api/analytics").json()["business"]
        assert money["clients"] == 1
        assert money["policiesActive"] == 1
        assert Decimal(money["premiumMonthlyBdt"]) == 4200
        assert Decimal(money["premiumYearlyBdt"]) == 50400
        assert Decimal(money["sumAssuredInForceBdt"]) == 500000
        assert len(money["months"]) == 12
        assert Decimal(money["months"][-1]["expectedBdt"]) == 4200


@needs_database
def test_a_fast_track_is_issued_at_the_standard_rate(carrier):
    _, underwriter, _, created = an_application(carrier, "low", "12.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        client.post(f"{url}/decision", json={"decision": "confirmed_fast_track"})
        policy = client.get(url).json()["policy"]
    # 500,000 of cover at the default 5,000 a month per 1,000,000.
    assert Decimal(policy["monthlyPremiumBdt"]) == 2500
    assert policy["planName"] == "Standard"


def test_grace_is_thirty_days():
    assert rules.GRACE_DAYS == 30
    start = date.today() - timedelta(days=31)
    due = rules.schedule(start, rules.end_date(start, 1), Decimal(1), {}, date.today())
    assert due[0].status == "overdue"
