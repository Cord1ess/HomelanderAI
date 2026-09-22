"""What a piece of evidence is.

One vocabulary, used in three places that must agree: triage decides which of
these a file is, arms declare which they accept, and the intake review screen
shows the operator both. Keeping it in its own module means none of those three
imports the others just to name a document type.

Deliberately coarse. These are the distinctions that change which model reads a
file, not a clinical taxonomy — `CHEST_XRAY` rather than `PA_CHEST_RADIOGRAPH`,
because nothing downstream does anything different with the view position.
"""

from enum import StrEnum


class EvidenceKind(StrEnum):
    """The kinds of document the platform can tell apart.

    `UNKNOWN` is a first-class outcome, not a failure. Triage that guesses when
    it is unsure produces a confident wrong score, which looks exactly like a
    right one; triage that says so sends the file to a human. Every code path
    handling these must handle UNKNOWN.
    """

    CHEST_XRAY = "chest_xray"
    FUNDUS = "fundus"
    MAMMOGRAM = "mammogram"
    SKIN_LESION = "skin_lesion"
    BRAIN_MRI = "brain_mri"
    # A 12-lead tracing exported as a signal file, not a picture of one.
    ECG = "ecg"
    # Lab results, discharge summaries, physician notes, prescriptions. Stored
    # as text and shown to the underwriter; the medication check reads the
    # prescriptions in them against the declared history.
    DOCUMENT = "document"
    UNKNOWN = "unknown"


# What an operator should see. The enum values are for storage and comparison;
# these are for the review screen, where "chest_xray" would read as a bug.
LABELS: dict[EvidenceKind, str] = {
    EvidenceKind.CHEST_XRAY: "Chest X-ray",
    EvidenceKind.FUNDUS: "Retinal photo",
    EvidenceKind.MAMMOGRAM: "Mammogram",
    EvidenceKind.SKIN_LESION: "Skin lesion photo",
    EvidenceKind.BRAIN_MRI: "Brain MRI",
    EvidenceKind.ECG: "12-lead ECG",
    EvidenceKind.DOCUMENT: "Document",
    EvidenceKind.UNKNOWN: "Not recognised",
}


def label(kind: EvidenceKind | str) -> str:
    """Display name for a kind, falling back to the raw value."""
    try:
        return LABELS[EvidenceKind(kind)]
    except (ValueError, KeyError):
        return str(kind)
