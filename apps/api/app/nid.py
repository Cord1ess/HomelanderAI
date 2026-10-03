"""Reading a Bangladeshi national ID card from a photo.

The front of the card (old laminated and new smart card alike) prints, in
English: the holder's **Name**, **Date of Birth** ("12 Mar 1985") and the
**ID NO** (10 digits on the smart card, 13 or 17 on older cards). Those three
are what intake needs. The Bangla lines and the back (address) are not read.

OCR is RapidOCR on ONNX Runtime: it runs on the CPU, needs no internet, and
its models ship inside the package. It reads the English lines well; it is
not asked to read Bangla.

**What comes back is a proposal.** The operator sees it beside the card and
confirms or corrects it, the same rule as for evidence: a misread ID number
accepted silently would attach one person's application to another's
identity. Where the card and the typed details disagree, the form says so.
"""

import io
import re
import threading
from dataclasses import dataclass, field
from datetime import date

from PIL import Image, ImageOps

_engine = None
_lock = threading.Lock()

_MONTHS = {
    m: i
    for i, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for m in names
}

# Labels on the card that are not the holder's name.
_NOT_NAMES = (
    "father",
    "mother",
    "date",
    "birth",
    "id no",
    "nid",
    "government",
    "republic",
    "people",
    "national",
    "card",
    "bangladesh",
    "signature",
)


@dataclass
class NidReading:
    number: str | None = None
    name: str | None = None
    date_of_birth: date | None = None
    # Every line the OCR read, for the operator to check against.
    lines: list[str] = field(default_factory=list)
    confidence: float | None = None
    # What could not be found, in words.
    missing: list[str] = field(default_factory=list)


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
        return _engine


def _prepare(raw: bytes):
    """Upright, greyscale and not tiny: what the OCR reads best."""
    import numpy as np

    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    if image.width < 900:
        scale = 900 / image.width
        image = image.resize((900, int(image.height * scale)))
    return np.array(image)


def read(raw: bytes) -> NidReading:
    """OCR one image of the front of a card and pick out the three fields."""
    result, _ = _ocr()(_prepare(raw))
    # Each item: [box, text, score]; sorted top to bottom, then left to right.
    items = sorted(result or [], key=lambda r: (round(r[0][0][1] / 12), r[0][0][0]))
    lines = [str(r[1]).strip() for r in items if str(r[1]).strip()]
    scores = [float(r[2]) for r in items]
    reading = parse(lines)
    reading.confidence = round(sum(scores) / len(scores), 3) if scores else None
    return reading


def parse(lines: list[str]) -> NidReading:
    """The three fields from the card's text lines. Separate from `read` so it
    is tested without an image."""
    out = NidReading(lines=list(lines))
    out.number = _number(lines)
    out.date_of_birth = _birth(lines)
    out.name = _name(lines)
    if not out.number:
        out.missing.append("ID number")
    if not out.date_of_birth:
        out.missing.append("date of birth")
    if not out.name:
        out.missing.append("name")
    return out


def _number(lines: list[str]) -> str | None:
    def digits(text: str) -> str:
        # OCR reads a zero as O and a one as I or l often enough to matter.
        fixed = text.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"}))
        return re.sub(r"\D", "", fixed)

    # No word boundary after the label: OCR often runs the number on ("ID NO1539…").
    labelled = [ln for ln in lines if re.search(r"\b(ID\s*NO|NID\s*NO|ID\s*NUMBER)", ln, re.I)]
    for index, line in enumerate(lines):
        if line in labelled:
            after = re.split(r"(?i)ID\s*NO|NID\s*NO|ID\s*NUMBER", line, maxsplit=1)[-1]
            candidates = [digits(after)]
            if index + 1 < len(lines):
                candidates.append(digits(lines[index + 1]))
            for found in candidates:
                if len(found) in (10, 13, 17):
                    return found
    for line in lines:
        found = digits(line)
        if len(found) in (10, 13, 17) and not re.search(r"[A-Za-z]{4,}", line):
            return found
    return None


def _birth(lines: list[str]) -> date | None:
    text = " ".join(lines)
    pattern = re.compile(r"(\d{1,2})[\s\-./]*([A-Za-z]{3,9})[\s\-./,]*(\d{4})")
    labelled = re.search(r"(?i)date\s*of\s*birth\s*:?\s*(.{0,24})", text)
    for source in ([labelled.group(1)] if labelled else []) + [text]:
        match = pattern.search(source)
        if match:
            month = _MONTHS.get(match.group(2).lower())
            if month:
                try:
                    return date(int(match.group(3)), month, int(match.group(1)))
                except ValueError:
                    continue
    numeric = re.search(r"(\d{2})[\-./](\d{2})[\-./](\d{4})", text)
    if numeric:
        try:
            return date(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
        except ValueError:
            return None
    return None


def _name(lines: list[str]) -> str | None:
    def clean(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z.\s-]", "", text)).strip(" .-")

    for index, line in enumerate(lines):
        match = re.match(r"(?i)^\s*name\s*[:.]?\s*(.*)$", line)
        if not match:
            continue
        same = clean(match.group(1))
        if len(same) >= 3:
            return same.title()
        if index + 1 < len(lines):
            following = clean(lines[index + 1])
            if len(following) >= 3 and not any(w in following.lower() for w in _NOT_NAMES):
                return following.title()
    return None


def name_matches(card: str | None, typed: str | None) -> bool:
    """Whether two spellings of a name are plausibly the same person's: every
    word of the shorter appears in the longer, ignoring case and dots (MD, Md.,
    Mohammad are left to the operator)."""
    if not card or not typed:
        return True
    a = {w for w in re.sub(r"[^a-z\s]", " ", card.lower()).split() if len(w) > 1}
    b = {w for w in re.sub(r"[^a-z\s]", " ", typed.lower()).split() if len(w) > 1}
    if not a or not b:
        return True
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return small <= big
