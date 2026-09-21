"""Work out what an uploaded document is, so it reaches the model that reads it.

The operator drags in everything the client brought. This decides what each
file appears to be; the operator confirms or corrects it on the review screen
before anything is scored.

**Rules, not a model.** Every signal here is a measurable property of the file
itself, so each answer can be explained in one sentence and there is no training
data to collect first. That matters because there is no labelled set for this
task yet: the corrections operators make on the review screen are what will
build one, and a learned classifier can replace this module later without any
caller changing.

**Abstaining is the point.** Returning UNKNOWN sends a file to a human. Guessing
sends it to a model, and a model handed the wrong document does not decline: the
retina arm returns 98.8 out of 100 on a chest X-ray. A wrong guess is therefore
not a smaller version of the right answer, it is a confident fabrication, so the
thresholds below are set to abstain rather than stretch.
"""

import logging
from dataclasses import dataclass
from io import BytesIO

from app.evidence import EvidenceKind

log = logging.getLogger(__name__)

# Extensions that are documents rather than images, whatever is inside them.
_DOCUMENT_SUFFIXES = (".pdf", ".txt", ".rtf", ".doc", ".docx", ".csv")

# DICOM says what it is. `Modality` is a two-letter code; `BodyPartExamined` is
# free text in practice, so it is matched loosely.
_MODALITY_KINDS: dict[str, EvidenceKind] = {
    "MG": EvidenceKind.MAMMOGRAM,
    "MR": EvidenceKind.BRAIN_MRI,
}

# How much the three colour channels differ, averaged per pixel. Radiographs are
# stored greyscale and measure exactly 0.00; the most washed-out fundus photo in
# our samples measures 5.9. Six is comfortably between them and well clear of
# the JPEG noise that can lift a true greyscale image off zero.
_GREY_MAX_SPREAD = 6.0

# A fundus photo is a circle on black, filling roughly half the frame. A chest
# film fills over 90%. Anything between is not confidently either.
_FUNDUS_MAX_LIT = 0.80
_CHEST_MIN_LIT = 0.85


@dataclass(frozen=True)
class Verdict:
    """What a file looks like, and why.

    `reason` is shown to the operator on the review screen. A classification
    nobody can question is one nobody can correct, and the corrections are the
    training data.
    """

    kind: EvidenceKind
    reason: str

    @property
    def certain(self) -> bool:
        return self.kind is not EvidenceKind.UNKNOWN


def classify(raw: bytes, filename: str = "", clinical_tags: dict | None = None) -> Verdict:
    """Identify one uploaded file.

    `clinical_tags` are the DICOM tags intake already pulled out, which are
    authoritative when present. Never raises: an unreadable file is UNKNOWN,
    which is a route to a human rather than an error page.
    """
    name = (filename or "").lower()

    if name.endswith(_DOCUMENT_SUFFIXES):
        return Verdict(
            EvidenceKind.DOCUMENT,
            f"{name.rsplit('.', 1)[-1].upper()} file, so it is a document rather than a scan",
        )

    # A DICOM header states the modality outright. Nothing inferred from pixels
    # beats the scanner saying what it produced.
    if clinical_tags:
        stated = _from_dicom(clinical_tags)
        if stated is not None:
            return stated

    try:
        return _from_pixels(raw)
    except Exception as exc:
        log.warning("Could not read %s for classification: %s", filename or "file", exc)
        return Verdict(EvidenceKind.UNKNOWN, "The file could not be read as an image")


def _from_dicom(tags: dict) -> Verdict | None:
    """Modality and body part, when the file carries them."""
    modality = str(tags.get("Modality", "")).strip().upper()
    body = str(tags.get("BodyPartExamined", "")).strip().upper()

    if modality in _MODALITY_KINDS:
        kind = _MODALITY_KINDS[modality]
        # A head MR is a brain MRI; a knee MR is not, and nothing reads it.
        if kind is EvidenceKind.BRAIN_MRI and body and not any(
            w in body for w in ("BRAIN", "HEAD", "SKULL")
        ):
            return Verdict(EvidenceKind.UNKNOWN, f"MRI of {body.title()}, which no model reads")
        return Verdict(kind, f"DICOM says modality {modality}")

    # Chest radiography is CR, DX or XA depending on the machine, so the body
    # part is what distinguishes a chest film from any other plain X-ray.
    if modality in ("CR", "DX", "XA", "RF"):
        if any(w in body for w in ("CHEST", "THORAX", "LUNG")):
            return Verdict(EvidenceKind.CHEST_XRAY, f"DICOM says {modality} of {body.title()}")
        if body:
            return Verdict(EvidenceKind.UNKNOWN, f"X-ray of {body.title()}, which no model reads")
        # An X-ray with no body part recorded. Let the pixels decide.
        return None

    return None


def _from_pixels(raw: bytes) -> Verdict:
    """Classify from what the image actually looks like."""
    from PIL import Image

    image = Image.open(BytesIO(raw))
    image.load()
    # 64x64 is enough for these statistics and keeps a 4752x3168 fundus photo
    # from costing real time on a step that runs on every upload.
    small = image.convert("RGB").resize((64, 64))
    pixels = list(small.getdata())
    total = len(pixels)

    spread = sum(max(p) - min(p) for p in pixels) / total
    lit = [p for p in pixels if sum(p) / 3 > 18]
    lit_fraction = len(lit) / total
    red_dominant = sum(1 for p in lit if p[0] > p[2] + 18) / max(len(lit), 1)

    if spread <= _GREY_MAX_SPREAD:
        # Greyscale. Chest films fill the frame; a greyscale image that does not
        # is something else, and guessing which would be inventing an answer.
        if lit_fraction >= _CHEST_MIN_LIT:
            return Verdict(EvidenceKind.CHEST_XRAY, "Greyscale scan filling the frame")
        return Verdict(
            EvidenceKind.UNKNOWN,
            "Greyscale, but not shaped like a chest film",
        )

    # Colour. A fundus photo is a red-orange circle on black.
    if red_dominant >= 0.20 and lit_fraction <= _FUNDUS_MAX_LIT:
        return Verdict(EvidenceKind.FUNDUS, "Round red-toned image on a dark background")

    return Verdict(
        EvidenceKind.UNKNOWN,
        "Colour image that does not match anything the platform screens",
    )
