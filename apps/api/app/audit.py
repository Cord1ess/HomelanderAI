"""Tamper-evident audit chain.

Each entry stores the hash of the previous entry plus its own payload, so
altering any historical record breaks every hash after it. Verification walks
the chain from the first entry forward.

This is **tamper-evident, not tamper-proof** — someone with write access to the
whole table could recompute the entire chain. Say that precisely rather than
overclaiming; the value is that a quiet edit of one row cannot go unnoticed.

Pure functions over dicts. The database layer supplies storage and the
append-only trigger (docs/DATABASE.md §E).
"""

import hashlib
import json
from dataclasses import dataclass

# Chain start. A fixed, non-empty seed so the first entry's hash still depends
# on something, and an empty chain is distinguishable from a tampered one.
GENESIS = "0" * 64


def canonical(payload: dict) -> str:
    """Deterministic JSON. Key order and separators must never vary or the same
    payload would hash differently on different runs."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(prev_hash: str | None, payload: dict) -> str:
    material = f"{prev_hash or GENESIS}{canonical(payload)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Entry:
    event_type: str
    payload: dict
    prev_hash: str
    payload_hash: str


def append(previous: Entry | None, event_type: str, payload: dict) -> Entry:
    """Build the next entry in the chain."""
    prev_hash = previous.payload_hash if previous else GENESIS
    return Entry(
        event_type=event_type,
        payload=payload,
        prev_hash=prev_hash,
        payload_hash=entry_hash(prev_hash, payload),
    )


def verify(entries: list[Entry]) -> tuple[bool, str | None]:
    """Walk the chain. Returns (ok, reason_for_failure).

    Checks both that each hash matches its payload and that each entry links to
    the one before it — a forged payload fails the first check, a deleted entry
    fails the second.
    """
    expected_prev = GENESIS

    for index, entry in enumerate(entries):
        if entry.prev_hash != expected_prev:
            return False, f"entry {index} ({entry.event_type}): broken link to previous entry"

        recomputed = entry_hash(entry.prev_hash, entry.payload)
        if recomputed != entry.payload_hash:
            return False, f"entry {index} ({entry.event_type}): payload does not match its hash"

        expected_prev = entry.payload_hash

    return True, None
