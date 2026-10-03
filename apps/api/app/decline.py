"""Declining an application: the reasons, and what the client is told.

A decline is always a person's decision, always with a reason, and never made
by a model (docs/SPEC.md §1). The reason is a code so it can be counted and
audited; each code has two wordings: the staff label, and the plain sentence
the client reads on their portal. The client is never told a score or a
model's finding: a decline letter that says "your ECG reader scored 74" would
be delivering an unvalidated clinical impression through an insurance portal.

A decline can say when the client may apply again: a postponement, as for an
illness under treatment, is a decline with a date.
"""

REASONS: dict[str, tuple[str, str]] = {
    "medical_risk": (
        "The medical evidence shows a risk too high to insure",
        "Based on the medical evidence, we are not able to offer you cover at this time.",
    ),
    "under_treatment": (
        "A condition under treatment: postpone until it is resolved",
        "You are being treated for a condition at the moment. We can look at your "
        "application again once the treatment is complete.",
    ),
    "non_disclosure": (
        "What was declared does not match the evidence",
        "Some of the information we received did not match what was declared on your "
        "application, so we cannot offer you cover.",
    ),
    "incomplete_evidence": (
        "The documents asked for were not provided",
        "We did not receive the documents we needed to assess your application.",
    ),
    "outside_limits": (
        "Outside the product's limits (age or amount)",
        "The cover you asked for is outside what we can offer for your age or for the "
        "amount requested.",
    ),
    "other": (
        "Another reason (explained in the note)",
        "We are not able to offer you cover at this time.",
    ),
}

# The most a client may be asked to wait before applying again.
MAX_REAPPLY_MONTHS = 24


def staff_label(code: str | None) -> str | None:
    return REASONS[code][0] if code in REASONS else None


def client_text(code: str | None) -> str | None:
    return REASONS[code][1] if code in REASONS else None
