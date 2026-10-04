"""Mirai: five-year breast-cancer risk from a four-view screening mammogram.

Mirai (Yala et al., Science Translational Medicine 2021, MIT CSAIL) reads the
four standard views — right and left MLO, right and left CC — and returns the
probability of a breast-cancer diagnosis within one to five years. Reported
C-index 0.76 at MGH, 0.81 at Karolinska and 0.79 at Chang Gung.

It runs on this machine, on the CPU, as the authors' own serving container
(`mitjclinic/mirai`, started by `docker compose`). It cannot live in the API
process: it pins Python 3.8 and torch 1.9, which cannot share our venv. What
lives here is everything around it:

- **The four views are checked before anything is sent.** Mirai arranges the
  views by their `ImageLaterality` and `ViewPosition` tags. Missing one view,
  two of the same, or unlabelled files is an error here, with the view named —
  not a vague refusal from the server.
- **The DICOMs are de-identified first** (`app.intake` strips the patient,
  physician and institution tags and keeps the pixels and the view tags). This
  was verified not to change the answer: the authors' demo exam gives the same
  risks to four decimal places before and after.
- **The score is the five-year risk on the arm scale.** An average-risk
  screening-age woman carries about 1.7% five-year risk; that sits at the top
  of the low tier. Around 4.5% — roughly Mirai's own high-risk cut, the top
  decile — reaches senior review. Log-linear between, as the mortality arm.

**Image only.** The served model ignores clinical risk factors even when sent
(reginabarzilaygroup/Mirai#14: `run_model` passes `risk_factor_vector = None`),
so this arm sends none and claims none. The declared history reaches the score
through the scoring rules, not through Mirai.

An exam takes about 43 seconds on an Intel Core Ultra 5 at 8 threads, which is
why it runs in the background scoring task.

**The heatmap** comes from a second server in the same image
(`Mirai/explain`): gradient x activation at the locations Mirai's max pool
kept, which is exact for this network, checked against occlusion
(docs/HEATMAPS.md). It is asked for only when the risk is above the low tier —
below it there is nothing to explain — and it is kept only if that server's
risk matches this one's to the last digit, so the map always belongs to the
number on the screen.
"""

import base64
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
VERSION = "2.0.0-ark-0.8.0-mirai-0.14.1"
PREPROCESSING_VERSION = "dicom-deidentified-4-views"
# The serving image, by digest: the weights are inside it, so this is what
# identifies the model that produced a reading.
WEIGHT_HASH = (
    "mitjclinic/mirai@sha256:"
    "c3a57f16657ba98ee2098bc200ea52012f9b0168a66544b680b1db7d4e56acc8"
)
VALIDATION = (
    "Mirai (Yala 2021): 5-year C-index 0.76 MGH, 0.81 Karolinska, 0.79 Chang Gung. Trained on "
    "Hologic screening exams in the US; NOT validated in South Asia, on digitised film, or on "
    "diagnostic (symptomatic) exams. Reads the images only — no clinical risk factors"
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

# The server answers "Year 1" .. "Year 5".
_YEARS = tuple(f"Year {n}" for n in range(1, 6))


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
    """The four views under `dicom`, and the `data` field the server requires.

    `data` is free-form JSON the server echoes back. It is sent empty: nothing
    about the applicant needs to reach the model, and Mirai would ignore it.
    """
    boundary = f"----homelander{uuid.uuid4().hex}"
    body = bytearray()
    for (laterality, view), raw in files.items():
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="dicom"; filename="{laterality}_{view}.dcm"\r\n'
            "Content-Type: application/dicom\r\n\r\n"
        ).encode()
        body += raw + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="data"\r\n\r\n{}\r\n'
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def call(files: dict[tuple[str, str], bytes]) -> dict:
    """POST the four views to the local Mirai service and return its JSON.

    A refusal arrives as HTTP 400 with the reason in `message`. That body is
    returned like any other answer rather than raised, so the reason reaches
    the screen instead of a bare status code.
    """
    body, content_type = _multipart(files)
    request = urllib.request.Request(
        f"{settings.mirai_url.rstrip('/')}/dicom/files",
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.mirai_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except ValueError:
            raise exc from None


def _post(url: str, files: dict[tuple[str, str], bytes], timeout: int) -> dict:
    body, content_type = _multipart(files)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": content_type, "Content-Length": str(len(body))},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def explain(files: dict[tuple[str, str], bytes], risks: list[float]) -> tuple[bytes | None, dict]:
    """(heatmap PNG or None, what to say about it). Never raises."""
    account: dict = {
        "method": "gradient x activation at Mirai's max-pool locations",
        "drawn": False,
    }
    if not settings.mirai_explain_url:
        return None, {**account, "reason": "The mammogram heatmap service is turned off."}
    try:
        answer = _post(
            f"{settings.mirai_explain_url.rstrip('/')}/explain",
            files,
            settings.mirai_explain_timeout_seconds,
        )
    except Exception as exc:
        reason = getattr(exc, "reason", exc)
        return None, {
            **account,
            "reason": (
                f"The heatmap could not be made ({reason}); start it with "
                "`docker compose up -d mirai-explain`. The risk above does not depend on it."
            ),
        }
    if risks_from(answer) != risks:
        # A map of a different number would be worse than no map.
        return None, {
            **account,
            "reason": (
                "The heatmap service gave a different risk from the reader, "
                "so its map was not used."
            ),
        }
    try:
        png = base64.b64decode(answer["heatmap_png"], validate=True)
        shares = sorted(answer.get("views") or [], key=lambda v: -float(v.get("share", 0)))
        lead = f"{shares[0]['view']} ({float(shares[0]['share']):.0%})" if shares else "the views"
    except (KeyError, TypeError, ValueError, IndexError):
        return None, {**account, "reason": "The heatmap service's answer carried no usable map."}
    return png, {
        **account,
        "drawn": True,
        "views": shares,
        "note": (
            "Red marks where in the four views the five-year risk came from: for each of the "
            "features Mirai keeps, the one place it was taken from, weighted by how much it "
            f"raised the risk. Most came from the {lead}. A prompt to look, not a finding."
        ),
    }


def risks_from(answer: dict) -> list[float] | None:
    """The five yearly risks, or None if the answer does not carry all five."""
    predictions = (answer.get("data") or {}).get("predictions")
    if not isinstance(predictions, dict):
        return None
    try:
        return [round(float(predictions[year]), 5) for year in _YEARS]
    except (KeyError, TypeError, ValueError):
        return None


def run_set(files: list[bytes]) -> ArmResult:
    """Score one applicant's four-view mammogram. Never raises."""
    if not available():
        return ArmResult(score=None, error="MIRAI_URL is not set")
    try:
        views = arrange(files)
    except ValueError as exc:
        return ArmResult(score=None, error=f"a four-view mammogram is needed: {exc}")

    timed_out = (
        f"the mammogram reader did not finish within {settings.mirai_timeout_seconds} seconds, "
        "so this reading is missing; the rest of the application was scored without it"
    )
    try:
        answer = call(views)
    except TimeoutError:
        return ArmResult(score=None, error=timed_out)
    except urllib.error.URLError as exc:
        # A socket timeout arrives wrapped in URLError, so check inside it too.
        if isinstance(exc.reason, TimeoutError):
            return ArmResult(score=None, error=timed_out)
        return ArmResult(
            score=None,
            error=(
                f"the mammogram reader is not running ({exc.reason}); "
                "start it with `docker compose up -d mirai`"
            ),
        )
    except Exception as exc:
        return ArmResult(
            score=None,
            error=f"the mammogram reader failed: {type(exc).__name__}: {exc}",
        )

    risks = risks_from(answer)
    if risks is None:
        reason = answer.get("message") or "no prediction returned"
        return ArmResult(
            score=None,
            error=f"the mammogram reader could not read this exam: {reason}"[:240],
        )

    five_year = risks[4]
    score = score_from(five_year)
    artifacts: dict[str, bytes] = {}
    if score > _LOW_TOP[1]:
        png, heatmap = explain(views, risks)
        if png:
            artifacts["gradcam"] = png
    else:
        heatmap = {
            "drawn": False,
            "reason": "The risk is in the low tier, so there is nothing for a map to explain.",
        }
    digest = hashlib.sha256(
        b"".join(hashlib.sha256(v).digest() for v in views.values())
    ).hexdigest()
    return ArmResult(
        score=score,
        raw_score=five_year,
        details={
            "risk_by_year": risks,
            "one_year_risk": risks[0],
            "five_year_risk": five_year,
            "views": [VIEW_LABELS[v] for v in views],
            "anchors": {"low_tier_top": _LOW_TOP, "senior_review": _SENIOR},
            # How long the model itself took, as the server measured it.
            "runtime": answer.get("runtime"),
            "scorer": f"{NAME} v{VERSION}",
            "validation": VALIDATION,
            "input_hash": digest,
            "heatmap": heatmap,
        },
        artifacts=artifacts,
    )
