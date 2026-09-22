"""Mirai: five-year breast-cancer risk from a four-view screening mammogram.

Mirai (Yala et al., Science Translational Medicine 2021, MIT CSAIL) reads the
four standard views — right and left MLO, right and left CC — and returns the
probability of a breast-cancer diagnosis within one to five years. It was
validated on 128,793 screening exams across MGH, Karolinska and Chang Gung,
with a five-year AUC of 0.76–0.81 and equal accuracy across races.

The model runs on a teammate's server (the published OncoServe container,
`2D_Mammo_Cancer_Mirai`); this arm sends the four DICOMs to it and reads the
answer. Nothing about the model lives here — what does is:

- **The four views are checked before anything is sent.** Mirai arranges the
  views by their `ImageLaterality` and `ViewPosition` tags. Missing one view,
  two of the same, or unlabelled files is an error here, not a wrong answer
  from the server.
- **The DICOMs are de-identified first** (`app.intake` strips the patient,
  physician and institution tags and keeps the pixels and the view tags), so
  the name on the exam never leaves this machine.
- **The score is the five-year risk on the arm scale.** An average-risk
  screening-age woman carries about 1.7% five-year risk; that sits at the top
  of the low tier. Around 4.5% — roughly Mirai's own high-risk cut, the top
  decile — reaches senior review. Log-linear between, as the mortality arm.

The call takes minutes (four 25 MB files, then a GPU-less inference), which is
fine in the background task and why the timeout is generous.
"""

import hashlib
import io
import json
import logging
import math
import urllib.error
import urllib.request
import uuid

from app.arms import ArmResult
from app.config import settings

log = logging.getLogger(__name__)

NAME = "mirai"
VERSION = "1.0.0-oncoserve-0.2.0"
PREPROCESSING_VERSION = "dicom-deidentified-4-views"
WEIGHT_HASH = "remote:2D_Mammo_Cancer_Mirai"
VALIDATION = (
    "Mirai (Yala 2021): 5-year AUC 0.76 MGH, 0.81 Karolinska, 0.79 Chang Gung on 128,793 exams; "
    "run remotely on the published OncoServe model. Screening populations in the US, Sweden and "
    "Taiwan; NOT validated in South Asia, and not validated for diagnostic (symptomatic) exams"
)

VIEWS: tuple[tuple[str, str], ...] = (("R", "MLO"), ("L", "MLO"), ("L", "CC"), ("R", "CC"))
VIEW_LABELS = {
    ("R", "MLO"): "right MLO",
    ("L", "MLO"): "left MLO",
    ("L", "CC"): "left CC",
    ("R", "CC"): "right CC",
}

# Five-year risk to the arm scale: 1.7% (average risk at screening age) sits
# at the top of the low tier; 4.5% (about Mirai's high-risk decile) at senior
# review. Log-linear between, clamped.
_LOW_TOP = (0.017, 30.0)
_SENIOR = (0.045, 65.0)


def available() -> bool:
    return bool(settings.mirai_url)


def score_from(five_year_risk: float) -> float:
    if five_year_risk <= 0:
        return 0.0
    (r0, s0), (r1, s1) = _LOW_TOP, _SENIOR
    slope = (s1 - s0) / (math.log(r1) - math.log(r0))
    return round(max(0.0, min(100.0, s0 + slope * (math.log(five_year_risk) - math.log(r0)))), 2)


def view_of(raw: bytes) -> tuple[str, str] | None:
    """(laterality, view) from the DICOM tags, or None when either is missing."""
    import pydicom

    try:
        ds = pydicom.dcmread(io.BytesIO(raw), stop_before_pixels=True, force=True)
    except Exception:
        return None
    laterality = str(ds.get("ImageLaterality", "") or ds.get("Laterality", "")).strip().upper()
    view = str(ds.get("ViewPosition", "")).strip().upper()
    if laterality in ("R", "L") and view in ("MLO", "CC"):
        return laterality, view
    return None


def arrange(files: list[bytes]) -> dict[tuple[str, str], bytes]:
    """The four views by (laterality, view). Raises ValueError with the reason."""
    found: dict[tuple[str, str], bytes] = {}
    unlabelled = 0
    for raw in files:
        view = view_of(raw)
        if view is None:
            unlabelled += 1
            continue
        if view in found:
            raise ValueError(f"two files are labelled {VIEW_LABELS[view]}")
        found[view] = raw
    missing = [VIEW_LABELS[v] for v in VIEWS if v not in found]
    if missing:
        detail = f"; {unlabelled} file(s) carry no laterality/view tags" if unlabelled else ""
        raise ValueError(f"missing view(s): {', '.join(missing)}{detail}")
    return found


def _multipart(files: dict[tuple[str, str], bytes]) -> tuple[bytes, str]:
    boundary = f"----homelander{uuid.uuid4().hex}"
    body = bytearray()
    for (laterality, view), raw in files.items():
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="dicom"; filename="{laterality}_{view}.dcm"\r\n'
            "Content-Type: application/dicom\r\n\r\n"
        ).encode()
        body += raw + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def call(files: dict[tuple[str, str], bytes]) -> dict:
    """POST the four views to the server and return its JSON."""
    body, content_type = _multipart(files)
    request = urllib.request.Request(
        settings.mirai_url,
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
    )
    with urllib.request.urlopen(request, timeout=settings.mirai_timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def run_set(files: list[bytes]) -> ArmResult:
    """Score one applicant's four-view mammogram. Never raises."""
    if not available():
        return ArmResult(score=None, error="MIRAI_URL is not set")
    try:
        views = arrange(files)
    except ValueError as exc:
        return ArmResult(score=None, error=f"a four-view mammogram is needed: {exc}")

    try:
        answer = call(views)
    except urllib.error.URLError as exc:
        return ArmResult(score=None, error=f"the Mirai server could not be reached: {exc.reason}")
    except Exception as exc:
        return ArmResult(score=None, error=f"the Mirai server failed: {type(exc).__name__}: {exc}")

    prediction = answer.get("prediction")
    if not isinstance(prediction, list) or len(prediction) != 5:
        return ArmResult(
            score=None,
            error=f"the Mirai server answered without a prediction: {answer.get('msg', '')}"[:200],
        )
    risks = [round(float(p), 5) for p in prediction]
    five_year = risks[4]
    digest = hashlib.sha256(
        b"".join(hashlib.sha256(v).digest() for v in views.values())
    ).hexdigest()
    return ArmResult(
        score=score_from(five_year),
        raw_score=five_year,
        details={
            "risk_by_year": risks,
            "one_year_risk": risks[0],
            "five_year_risk": five_year,
            "views": [VIEW_LABELS[v] for v in views],
            "anchors": {"low_tier_top": _LOW_TOP, "senior_review": _SENIOR},
            "server": {
                "model_name": answer.get("model_name"),
                "onconet_version": answer.get("onconet_version"),
                "oncoserve_version": answer.get("oncoserve_version"),
            },
            "scorer": f"{NAME} v{VERSION}",
            "validation": VALIDATION,
            "input_hash": digest,
        },
    )
