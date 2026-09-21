"""Asking the applicant for specific documents.

The property that matters: requesting evidence must never spend the write-once
decision. If it did, the application would be decided forever the moment a
document was asked for, and nothing could be decided once it arrived.
"""

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import needs_database
from tests.test_applications import sign_in, submit

pytestmark = needs_database


def test_requesting_evidence_pauses_rather_than_decides(carrier):
    """The whole point. After a request the application is waiting, the
    decision is still open, and it can be decided once the documents arrive."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        response = client.post(
            f"/api/applications/{created['id']}/evidence-request",
            json={"items": ["A chest X-ray taken within the last 6 months", "HbA1c result"]},
        )
        assert response.status_code == 201, response.text
        items = response.json()
        assert [i["description"] for i in items] == [
            "A chest X-ray taken within the last 6 months",
            "HbA1c result",
        ]
        assert all(i["fulfilledAt"] is None for i in items)
        assert items[0]["requestedByName"] == "Test Underwriter"

        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["status"] == "awaiting_evidence"
        assert detail["decision"] is None, "requesting evidence must not decide"
        assert len(detail["requestedDocuments"]) == 2

        # The decision is still available once the documents come in.
        for item in items:
            assert (
                client.post(
                    f"/api/applications/{created['id']}/evidence-request/{item['id']}/fulfil"
                ).status_code
                == 200
            )
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["status"] in ("scored", "insufficient_evidence")

        decided = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "confirmed_fast_track"},
        )
        assert decided.status_code == 201, decided.text


def test_the_decision_endpoint_refuses_to_spend_the_decision_on_a_request(carrier):
    """'Request more evidence' through the decision endpoint would consume the
    one decision. It is redirected to the endpoint that pauses instead."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        response = client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "requested_additional_evidence"},
        )
        assert response.status_code == 422
        assert "evidence-request" in response.json()["detail"]

        # Nothing was recorded.
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["decision"] is None
        assert detail["status"] != "decided"


def test_a_request_for_nothing_is_rejected(carrier):
    """'More evidence needed' with nothing named is exactly what this
    replaces."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)

        assert (
            client.post(
                f"/api/applications/{created['id']}/evidence-request", json={"items": []}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/applications/{created['id']}/evidence-request",
                json={"items": ["   ", ""]},
            ).status_code
            == 422
        )


def test_partial_fulfilment_keeps_waiting(carrier):
    """Two items asked for, one received: still waiting on the applicant."""
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        items = client.post(
            f"/api/applications/{created['id']}/evidence-request",
            json={"items": ["First", "Second"]},
        ).json()

        client.post(f"/api/applications/{created['id']}/evidence-request/{items[0]['id']}/fulfil")
        detail = client.get(f"/api/applications/{created['id']}").json()
        assert detail["status"] == "awaiting_evidence"
        outstanding = [d for d in detail["requestedDocuments"] if d["fulfilledAt"] is None]
        assert [d["description"] for d in outstanding] == ["Second"]


def test_fulfilling_twice_is_not_an_error(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        item = client.post(
            f"/api/applications/{created['id']}/evidence-request", json={"items": ["X"]}
        ).json()[0]
        url = f"/api/applications/{created['id']}/evidence-request/{item['id']}/fulfil"

        first = client.post(url).json()
        second = client.post(url).json()
        assert first["fulfilledAt"] == second["fulfilledAt"]


def test_cannot_request_evidence_on_a_decided_application(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        client.post(
            f"/api/applications/{created['id']}/decision",
            json={"decision": "confirmed_fast_track"},
        )
        response = client.post(
            f"/api/applications/{created['id']}/evidence-request", json={"items": ["X"]}
        )
        assert response.status_code == 409


def test_requests_are_tenant_scoped(carrier):
    """Another carrier can neither see nor fulfil this carrier's requests."""
    first = asyncio.run(carrier("Carrier One"))
    second = asyncio.run(carrier("Carrier Two"))

    with TestClient(app) as client:
        sign_in(client, first)
        created = submit(client)
        item = client.post(
            f"/api/applications/{created['id']}/evidence-request", json={"items": ["X"]}
        ).json()[0]

    with TestClient(app) as client:
        sign_in(client, second)
        assert (
            client.post(
                f"/api/applications/{created['id']}/evidence-request", json={"items": ["Y"]}
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/applications/{created['id']}/evidence-request/{item['id']}/fulfil"
            ).status_code
            == 404
        )


def test_the_request_is_in_the_audit_trail(carrier):
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        created = submit(client)
        item = client.post(
            f"/api/applications/{created['id']}/evidence-request",
            json={"items": ["Recent chest X-ray"], "note": "The film supplied was from 2019."},
        ).json()[0]
        client.post(f"/api/applications/{created['id']}/evidence-request/{item['id']}/fulfil")

        trail = client.get(f"/api/applications/{created['id']}/audit").json()

    assert trail["intact"] is True
    events = {e["eventType"]: e for e in trail["entries"]}
    assert events["evidence_requested"]["payload"]["items"] == ["Recent chest X-ray"]
    assert events["evidence_requested"]["payload"]["note"] == "The film supplied was from 2019."
    assert events["evidence_requested"]["actorName"] == "Test Underwriter"
    assert "evidence_received" in events
