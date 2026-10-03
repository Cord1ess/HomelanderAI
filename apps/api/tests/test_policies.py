"""Policies, prices, declines, claims and the dates that govern them.

The pricing engine and the date helpers are tested on their own first: they
are arithmetic, and a mistake in either shows up as a wrong premium or a
policy ending on a day that does not exist.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import policies as rules
from app import pricing
from app.main import app
from tests.conftest import needs_database
from tests.test_applications import sign_in
from tests.test_roles import an_application, skip_scoring  # noqa: F401  (fixture)

# ── dates ────────────────────────────────────────────────────────────────────


def test_a_month_on_from_the_31st_is_the_last_day_of_a_short_month():
    assert rules.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert rules.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert rules.add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert rules.end_date(date(2026, 10, 3), 10) == date(2036, 10, 3)


def test_the_term_comes_from_what_was_asked_for():
    assert rules.term_years("10") == 10
    assert rules.term_years("20 years") == 20
    assert rules.term_years(None) == rules.DEFAULT_TERM_YEARS


# ── prices ───────────────────────────────────────────────────────────────────


def test_term_life_is_priced_at_bangladeshi_levels():
    """Ten lakh for ten years at thirty costs a few hundred taka a month, not
    the five thousand the placeholder charged."""
    q = pricing.quote("life", 1_000_000, 10, 30, "male")
    assert 2_500 <= q.annual_bdt <= 5_000
    assert q.monthly_bdt * 12 > q.annual_bdt, "paying monthly costs a little more"


def test_older_smokers_and_rated_lives_pay_more_and_women_less():
    base = pricing.quote("life", 1_000_000, 10, 40, "male").annual_bdt
    assert pricing.quote("life", 1_000_000, 10, 50, "male").annual_bdt > base
    assert pricing.quote("life", 1_000_000, 10, 40, "female").annual_bdt < base
    assert pricing.quote("life", 1_000_000, 10, 40, "male", smoker=True).annual_bdt > base
    assert pricing.quote("life", 1_000_000, 10, 40, "male", rating_pct=100).annual_bdt > base


def test_the_premium_covers_expected_claims_with_the_idra_loading():
    """Profitable by construction: the gross premium is the expected cost of
    claims divided by (1 - 22.32%)."""
    q = pricing.quote("life", 2_000_000, 20, 35, "male")
    assert q.expected_claims_bdt < q.annual_bdt
    assert q.annual_bdt == pytest.approx(q.expected_claims_bdt / (1 - 0.2232), abs=10)


def test_hospital_cover_is_one_year_priced_by_age_band():
    young = pricing.quote("health", 200_000, 10, 30)
    assert young.term_years == 1, "hospital cover runs one year, whatever was asked"
    assert young.annual_bdt == 3600
    assert pricing.quote("health", 200_000, 1, 50).annual_bdt == 3600 * 1.9


@pytest.mark.parametrize(
    ("product", "term", "age", "why"),
    [
        ("life", 10, 17, "ages 18 to 60"),
        ("life", 10, 61, "ages 18 to 60"),
        ("life", 20, 55, "age 70"),
        ("health", 1, 66, "between ages 18 and 65"),
        ("life", 10, None, "date of birth"),
    ],
)
def test_outside_the_limits_there_is_no_price(product, term, age, why):
    q = pricing.quote(product, 1_000_000, term, age)
    assert not q.eligible and q.annual_bdt == 0 and why in q.reason


def test_findings_suggest_exclusions_in_plain_words():
    out = pricing.suggested_exclusions(
        {"ecg_12lead": "moderate", "tb_xray": "low", "dr_fundus": "elevated"},
        {"cxr_lung": {"history": {"diabetes": True}}},
    )
    assert "Heart disease and heart rhythm problems" in out
    assert "Eye disease from diabetes (diabetic retinopathy)" in out
    assert "Diabetes and its complications" in out
    assert not any("tuberculosis" in e for e in out), "a low reading suggests nothing"


# ── with a database ──────────────────────────────────────────────────────────


def _decide(carrier, body: dict, coverage: dict | None = None):
    _, underwriter, admin, created = an_application(carrier, "moderate", "48.00", coverage)
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        r = client.post(f"{url}/decision", json=body)
        assert r.status_code == 201, r.text
        detail = client.get(url).json()
    return underwriter, admin, created, detail


HEALTH = {"coverageType": "Health", "coverageAmount": 200000, "policyTerm": "1"}


@needs_database
def test_a_rated_approval_issues_a_life_policy_with_proper_dates(carrier):
    _, _, created, detail = _decide(
        carrier, {"decision": "approved_with_adjustment", "ratingPct": 50}
    )
    policy = detail["policy"]
    today = date.today()
    assert policy["policyNumber"] == f"P-{created['reference']}"
    assert policy["product"] == "life" and policy["ratingPct"] == 50
    assert policy["termYears"] == 10
    assert policy["startDate"] == today.isoformat()
    assert policy["endDate"] == rules.end_date(today, 10).isoformat()
    assert policy["freeLookUntil"] == (today + timedelta(days=15)).isoformat()
    assert policy["inFreeLook"] is True
    assert policy["waitingUntil"] is None, "no waiting period on term life"
    assert policy["nextPremiumDue"] == today.isoformat()
    # The rated premium is the engine's, at +50%.
    assert detail["decision"]["ratingPct"] == 50
    assert float(policy["monthlyPremiumBdt"]) == float(detail["decision"]["finalPremium"])


@needs_database
def test_hospital_cover_is_one_year_with_waiting_periods_and_exclusions(carrier):
    body = {
        "decision": "approved_with_adjustment",
        "ratingPct": 0,
        "exclusions": ["Heart disease and heart rhythm problems"],
    }
    _, _, _, detail = _decide(carrier, body, HEALTH)
    policy = detail["policy"]
    today = date.today()
    assert policy["product"] == "health" and policy["termYears"] == 1
    assert policy["endDate"] == rules.add_months(today, 12).isoformat()
    assert policy["waitingUntil"] == (today + timedelta(days=30)).isoformat()
    assert policy["preexistingUntil"] == rules.add_months(today, 24).isoformat()
    assert policy["exclusions"] == ["Heart disease and heart rhythm problems"]
    assert float(policy["remainingLimitBdt"]) == 200000


@needs_database
def test_exclusions_are_for_hospital_cover_and_an_adjustment_must_adjust(carrier):
    _, underwriter, _, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}/decision"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        r = client.post(url, json={"decision": "approved_with_adjustment", "exclusions": ["x"]})
        assert r.status_code == 422 and "hospital cover" in r.json()["detail"]
        r = client.post(url, json={"decision": "approved_with_adjustment", "ratingPct": 30})
        assert r.status_code == 422, "30% is not one of the ratings"


@needs_database
def test_a_decline_needs_a_reason_and_tells_the_client_in_plain_words(carrier):
    _, underwriter, _, created = an_application(carrier, "moderate", "48.00")
    url = f"/api/applications/{created['id']}"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post(f"{url}/decision", json={"decision": "declined"}).status_code == 422
        r = client.post(
            f"{url}/decision",
            json={
                "decision": "declined",
                "declineReason": "under_treatment",
                "declineNote": "Please apply again once your treatment has finished.",
                "reapplyAfterMonths": 6,
            },
        )
        assert r.status_code == 201, r.text
        assert client.get(url).json()["policy"] is None
        queue = client.get("/api/applications").json()["items"]
        assert queue[0]["declined"] is True
    with TestClient(app) as client:
        me = client.post("/api/portal/login", json=created["portal"]).json()
    assert me["policy"] is None and me["offer"] is None
    assert "treated" in me["declined"]["reason"]
    assert me["declined"]["note"] == "Please apply again once your treatment has finished."
    assert me["declined"]["reapplyAfter"] == rules.add_months(date.today(), 6).isoformat()


@needs_database
def test_an_elevated_case_is_declined_only_after_a_doctor_has_looked(carrier):
    _, underwriter, _, created = an_application(carrier, "elevated", "82.00")
    url = f"/api/applications/{created['id']}/decision"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        r = client.post(url, json={"decision": "declined", "declineReason": "medical_risk"})
        assert r.status_code == 403


@needs_database
def test_the_owner_cancels_and_the_client_sees_it(carrier):
    underwriter, admin, created, detail = _decide(carrier, {"decision": "confirmed_fast_track"})
    url = f"/api/policies/{detail['policy']['id']}/cancel"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post(url, json={"reason": "Client asked."}).status_code == 403
    with TestClient(app) as client:
        sign_in(client, admin)
        r = client.post(url, json={"reason": "The client asked to cancel."})
        assert r.status_code == 200, r.text
        assert r.json()["effectiveStatus"] == "cancelled"
        assert r.json()["nextPremiumDue"] is None
        assert client.post(url, json={"reason": "Twice over."}).status_code == 409
    with TestClient(app) as client:
        me = client.post("/api/portal/login", json=created["portal"]).json()
        assert me["policy"]["effectiveStatus"] == "cancelled"


@needs_database
def test_the_owner_sees_premiums_due_and_payouts_owed(carrier):
    _, admin, _, detail = _decide(carrier, {"decision": "confirmed_fast_track"})
    policy = detail["policy"]
    # What the client actually pays in a year: twelve instalments cost more than one payment.
    paid_yearly = (
        Decimal(policy["annualPremiumBdt"])
        if policy["premiumMode"] == "yearly"
        else Decimal(policy["monthlyPremiumBdt"]) * 12
    )
    with TestClient(app) as client:
        sign_in(client, admin)
        money = client.get("/api/analytics").json()["business"]
    assert money["policiesActive"] == 1 and money["lifePolicies"] == 1
    assert Decimal(money["premiumYearlyBdt"]) == paid_yearly
    assert Decimal(money["sumAssuredInForceBdt"]) == 500000
    assert Decimal(money["expectedMarginYearlyBdt"]) > 0, "priced to make money"
    assert len(money["months"]) == 12


# ── claims ───────────────────────────────────────────────────────────────────


def _claim_on(client, policy_id: str, body: dict, files=None):
    return client.post(
        f"/api/policies/{policy_id}/claims",
        data={"payload": json.dumps(body)},
        files=files or [],
    )


@needs_database
def test_a_hospital_claim_runs_from_filing_to_settled(carrier):
    underwriter, admin, created, detail = _decide(
        carrier, {"decision": "confirmed_fast_track"}, HEALTH
    )
    policy_id = detail["policy"]["id"]

    # The client files it from the portal, with the bill.
    with TestClient(app) as client:
        client.post("/api/portal/login", json=created["portal"])
        me = client.post(
            "/api/portal/claims",
            data={
                "payload": json.dumps(
                    {
                        "eventDate": date.today().isoformat(),
                        "claimedAmountBdt": 45000,
                        "description": "Two nights in hospital with dengue fever",
                        "hospital": "Square Hospital",
                        "accident": False,
                    }
                )
            },
            files={"files": ("bill.pdf", b"%PDF-1.4 bill", "application/pdf")},
        ).json()
        [claim] = me["claims"]
        assert claim["status"] == "submitted" and claim["documents"] == 1

    with TestClient(app) as client:
        sign_in(client, underwriter)
        [staff_view] = client.get("/api/claims").json()
        # Illness in the first thirty days: flagged for the person deciding.
        assert any("30 days" in c for c in staff_view["checks"])
        claim_id = staff_view["id"]
        act = f"/api/claims/{claim_id}/action"
        r = client.post(act, json={"action": "request_documents", "note": "The discharge summary"})
        assert r.json()["status"] == "documents_requested"
        r = client.post(act, json={"action": "documents_complete"})
        assert r.json()["settleBy"] == (date.today() + timedelta(days=90)).isoformat()
        r = client.post(act, json={"action": "approve", "approvedAmountBdt": 300000})
        assert r.status_code == 422, "more than the year's limit"
        r = client.post(act, json={"action": "approve", "approvedAmountBdt": 40000})
        assert r.json()["status"] == "approved"
        assert client.post(act, json={"action": "settle"}).status_code == 403, (
            "the bank's, the owner's"
        )

    with TestClient(app) as client:
        sign_in(client, admin)
        r = client.post(
            f"/api/claims/{claim_id}/action",
            json={"action": "settle", "settlementReference": "BANK-REF-77"},
        )
        assert r.json()["status"] == "settled"
        policy = client.get(f"/api/policies/{policy_id}").json()
        assert float(policy["remainingLimitBdt"]) == 160000
        assert float(policy["claimsPaidBdt"]) == 40000


@needs_database
def test_a_death_claim_is_filed_by_staff_and_pays_the_sum_assured(carrier):
    underwriter, _, created, detail = _decide(carrier, {"decision": "confirmed_fast_track"})
    with TestClient(app) as client:
        sign_in(client, underwriter)
        r = _claim_on(
            client,
            detail["policy"]["id"],
            {
                "eventDate": date.today().isoformat(),
                "claimedAmountBdt": 500000,
                "description": "Death certificate attached",
                "claimantName": "Test Nominee",
            },
        )
        assert r.status_code == 201, r.text
        claim = r.json()
        assert claim["claimType"] == "death"
        assert float(claim["payableLimitBdt"]) == 500000
        reject = client.post(f"/api/claims/{claim['id']}/action", json={"action": "reject"})
        assert reject.status_code == 422, "a rejection needs a reason the client reads"
    with TestClient(app) as client:
        client.post("/api/portal/login", json=created["portal"])
        refused = client.post(
            "/api/portal/claims",
            data={
                "payload": json.dumps(
                    {
                        "eventDate": date.today().isoformat(),
                        "claimedAmountBdt": 1,
                        "description": "hello",
                    }
                )
            },
            files={"files": ("x.pdf", b"%PDF", "application/pdf")},
        )
        assert refused.status_code == 422, "a life claim is made by the nominee at the office"


# ── case assignment ──────────────────────────────────────────────────────────


@needs_database
def test_one_underwriter_takes_a_case_and_another_cannot(carrier):
    from tests.test_roles import add_underwriter

    _, underwriter, admin, created = an_application(carrier, "moderate", "48.00")
    other = add_underwriter(admin["tenant_id"])
    url = f"/api/applications/{created['id']}/assign"
    with TestClient(app) as client:
        sign_in(client, underwriter)
        r = client.post(url)
        assert r.status_code == 200 and r.json()["assignedToName"]
        assert client.get("/api/applications", params={"mine": True}).json()["items"]
    with TestClient(app) as client:
        sign_in(client, other)
        assert client.post(url).status_code == 409
        assert client.get("/api/applications", params={"mine": True}).json()["items"] == []
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post(url, params={"release": True}).json()["assignedToId"] is None
