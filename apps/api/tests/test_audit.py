"""Audit chain.

The point of these tests is that a quiet edit to a historical record cannot pass
verification.
"""

from dataclasses import replace

from app.audit import GENESIS, Entry, append, canonical, entry_hash, verify


def build_chain() -> list[Entry]:
    entries: list[Entry] = []
    previous = None
    for event, payload in (
        ("application_submitted", {"application_id": "abc", "files": 1}),
        ("model_run_completed", {"arm": "tb_xray", "score": 41.2}),
        ("composite_scored", {"crs": 51.2, "tier": "moderate"}),
        ("decision_recorded", {"decision": "escalated_senior_review", "by": "u-1"}),
    ):
        previous = append(previous, event, payload)
        entries.append(previous)
    return entries


# ── determinism ──────────────────────────────────────────────────────────────


def test_canonical_form_is_key_order_independent():
    assert canonical({"b": 2, "a": 1}) == canonical({"a": 1, "b": 2})


def test_same_payload_and_parent_hash_identically():
    payload = {"crs": 12.5, "tier": "low"}
    assert entry_hash("abc", payload) == entry_hash("abc", payload)


def test_hash_depends_on_the_parent():
    """Otherwise identical payloads at different chain positions must differ,
    or entries could be reordered undetected."""
    payload = {"crs": 12.5}
    assert entry_hash("aaa", payload) != entry_hash("bbb", payload)


def test_first_entry_links_to_genesis():
    first = append(None, "application_submitted", {"x": 1})
    assert first.prev_hash == GENESIS


# ── verification ─────────────────────────────────────────────────────────────


def test_intact_chain_verifies():
    ok, reason = verify(build_chain())
    assert ok
    assert reason is None


def test_empty_chain_verifies():
    ok, _ = verify([])
    assert ok


def test_edited_payload_is_detected():
    """The whole point: change a stored score, verification must fail."""
    chain = build_chain()
    chain[2] = replace(chain[2], payload={"crs": 5.0, "tier": "low"})

    ok, reason = verify(chain)
    assert not ok
    assert "does not match its hash" in reason


def test_deleted_entry_is_detected():
    chain = build_chain()
    del chain[1]

    ok, reason = verify(chain)
    assert not ok
    assert "broken link" in reason


def test_reordered_entries_are_detected():
    chain = build_chain()
    chain[1], chain[2] = chain[2], chain[1]

    ok, reason = verify(chain)
    assert not ok


def test_appended_forgery_without_rehashing_is_detected():
    """Someone appends a favourable record but cannot recompute the chain."""
    chain = build_chain()
    forged = Entry(
        event_type="composite_scored",
        payload={"crs": 1.0, "tier": "low"},
        prev_hash=chain[-1].payload_hash,
        payload_hash="deadbeef" * 8,
    )
    chain.append(forged)

    ok, reason = verify(chain)
    assert not ok
    assert "does not match its hash" in reason


def test_tampering_invalidates_everything_after_it():
    """A single edited entry must not be repairable by fixing only its own hash —
    the following entries still point at the old value."""
    chain = build_chain()
    edited_payload = {"crs": 5.0, "tier": "low"}
    chain[1] = Entry(
        event_type=chain[1].event_type,
        payload=edited_payload,
        prev_hash=chain[1].prev_hash,
        payload_hash=entry_hash(chain[1].prev_hash, edited_payload),
    )

    ok, reason = verify(chain)
    assert not ok
    assert "broken link" in reason


def test_payload_types_survive_canonicalisation():
    """Decimals, datetimes and UUIDs reach the audit log; none may crash it."""
    import datetime as dt
    import uuid
    from decimal import Decimal

    payload = {
        "crs": Decimal("51.20"),
        "at": dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC),
        "id": uuid.uuid4(),
    }
    first = append(None, "composite_scored", payload)

    ok, _ = verify([first])
    assert ok
