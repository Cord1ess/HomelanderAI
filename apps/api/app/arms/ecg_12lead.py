"""12-lead ECG arm: six rhythm and conduction abnormalities, and an ECG age.

Two published networks from the same group, run on the same tracing:

**Abnormalities** (Ribeiro et al. 2020). First-degree AV block, right and
left bundle branch block, sinus bradycardia, atrial fibrillation, sinus
tachycardia — the six findings the paper's model reported at above 80% F1,
outperforming cardiology residents. Our PyTorch port reproduces the authors'
own decisions on their public test set at 99.6–100% per class, at the
thresholds recovered from those decisions. Those thresholds, not 0.5, decide
what is reported.

**ECG age** (Lima et al. 2021). An age estimated from the tracing; in 1.56
million patients an ECG reading more than eight years older than the person
carried 1.79 times the mortality. On the public test set our run of the model
is far less precise than the paper's headline (MAE 11.6 years, and it reads
young adults about fifteen years older), so the gap is shown against what the
model reads for a typical person of that age, and it is a prompt to look,
never part of the score.

**The score.** A reported abnormality moves the score by its weight in
`ecg_12lead_model.json` — atrial fibrillation or a left bundle branch block go
straight to senior review; a sinus tachycardia is a prompt. With nothing
reported the score stays in the low tier, rising towards its top as any
probability approaches its threshold.

**Explanation.** For the reported abnormality, each lead is flattened in turn
and the network run again: the share of the probability that disappears is
that lead's weight, printed beside it and tinted on the tracing. Measured, not
estimated. Two other methods were tested on CODE-test true positives and
dropped (see docs/HEATMAPS.md): the input gradient this arm used to draw was
no better than random at finding the windows that mattered, and no 0.25 s
window of any lead mattered on its own, because the network reads these
findings from every beat — so a map along the time axis would be painting
noise. With nothing reported there is nothing to explain, and no map is drawn.

Both weights are downloaded from Zenodo (CC-BY-4.0) and converted once by
`scripts/fetch_ecg_models.py`; the arm loads the converted files strictly and
refuses one whose hash has changed. Brazilian training data; not validated in
South Asia, and the arm says so on every reading.
"""

import hashlib
import json
import threading
from pathlib import Path

from app import ecg
from app.arms import ArmResult
from app.config import settings

NAME = "ecg_12lead"
VERSION = "1.0.0-ribeiro2020-lima2021"

MODEL_PATH = Path(__file__).with_name("ecg_12lead_model.json")
_SPEC: dict = json.loads(MODEL_PATH.read_text())

MODELS_DIR = settings.data_dir / "ecg" / "models"
DX_PATH = MODELS_DIR / _SPEC["converted_weights"]["dx"]["file"]
AGE_PATH = MODELS_DIR / _SPEC["converted_weights"]["age"]["file"]
AGE_CONFIG_PATH = MODELS_DIR / "ecg_age_config.json"

PREPROCESSING_VERSION = "12-lead-400hz-4096-0.1mV"
WEIGHT_HASH = (
    f"dx:sha256:{_SPEC['converted_weights']['dx']['sha256'][:16] or 'unconverted'}"
    f"+age:sha256:{_SPEC['converted_weights']['age']['sha256'][:16] or 'unconverted'}"
    f"+spec:sha256:{hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:16]}"
)
VALIDATION: str = _SPEC["dx_validation"]

CLASSES: tuple[str, ...] = tuple(_SPEC["classes"])
LABELS: dict[str, str] = dict(_SPEC["labels"])
THRESHOLDS: dict[str, float] = dict(_SPEC["thresholds"])
WEIGHTS: dict[str, float] = dict(_SPEC["weights"])

# With nothing reported, the score climbs towards the top of the low tier as
# the closest probability approaches its threshold, and never crosses it.
_UNFLAGGED_CEILING = 29.9

_models: dict = {}
_lock = threading.Lock()


def available() -> bool:
    try:
        import safetensors  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def weights_present() -> bool:
    return DX_PATH.exists() and AGE_PATH.exists() and AGE_CONFIG_PATH.exists()


def _verify(path: Path, expected: str) -> None:
    if not expected:
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(
            f"{path.name} does not match the pinned hash; re-run fetch_ecg_models.py"
        )


def _load():
    """Both networks, loaded once per process and locked against the worker
    threads that score applications in parallel."""
    with _lock:
        if _models:
            return _models
        import torch
        from safetensors.torch import load_file

        from app.arms import ecg_nets

        if not weights_present():
            raise FileNotFoundError(
                f"ECG weights not found in {MODELS_DIR}; run scripts/fetch_ecg_models.py"
            )
        _verify(DX_PATH, _SPEC["converted_weights"]["dx"]["sha256"])
        _verify(AGE_PATH, _SPEC["converted_weights"]["age"]["sha256"])

        dx = ecg_nets.EcgDx()
        dx.load_state_dict(load_file(str(DX_PATH)), strict=True)
        age = ecg_nets.age_net(json.loads(AGE_CONFIG_PATH.read_text()))
        age.load_state_dict(load_file(str(AGE_PATH)), strict=True)
        _models["dx"] = dx.eval()
        _models["age"] = age.eval()
        _models["torch"] = torch
        return _models


def expected_ecg_age(age: float) -> float:
    """What the age model reads for a typical person of this age, from the
    fit on the public test set; the gap is measured against this."""
    fit = _SPEC["age_calibration"]
    return fit["slope"] * age + fit["intercept"]


def points_for(name: str, probability: float) -> float:
    """The score this one abnormality would set on its own: its weight when
    reported, otherwise a low-tier value that grows with its probability."""
    if probability >= THRESHOLDS[name]:
        return round(100.0 * WEIGHTS[name], 2)
    return round(min(_UNFLAGGED_CEILING, 30.0 * probability / THRESHOLDS[name]), 2)


def score_from(probabilities: dict[str, float]) -> tuple[float, list[str]]:
    """The arm's score and the abnormalities reported at the authors' thresholds.
    The highest single reading governs, as it does across arms."""
    reported = [c for c in CLASSES if probabilities[c] >= THRESHOLDS[c]]
    return max(points_for(c, probabilities[c]) for c in CLASSES), reported


def lead_importance(models, tensor, class_index: int) -> dict[str, float]:
    """Share of the class probability lost when each lead is flattened, 0-1.

    Twelve extra forward passes in one batch. Flattening a lead to zero is the
    isoelectric line: the lead stops carrying anything, and the fall in the
    probability is how much the reading leaned on it.
    """
    torch = models["torch"]
    with torch.no_grad():
        base = float(models["dx"](tensor)[0, class_index])
        batch = tensor.repeat(12, 1, 1)
        for lead in range(12):
            batch[lead, lead, :] = 0.0
        flattened = models["dx"](batch)[:, class_index].numpy()
    if base <= 0:
        return {}
    return {
        lead: round(float(max(0.0, base - p) / base), 3)
        for lead, p in zip(ecg.LEADS, flattened, strict=True)
    }


def run(raw: bytes) -> ArmResult:
    """Score one stored tracing (the canonical .npy). Never raises."""
    if not available():
        return ArmResult(score=None, error="torch not installed (uv sync --extra vision)")
    try:
        array = ecg.from_bytes(raw)
    except Exception as exc:
        return ArmResult(score=None, error=f"unreadable ECG: {exc}")
    try:
        models = _load()
    except Exception as exc:
        return ArmResult(score=None, error=f"ECG models unavailable: {exc}")

    torch = models["torch"]
    tensor = torch.from_numpy(ecg.to_model_units(array))[None, ...]

    try:
        with torch.no_grad():
            probs = models["dx"](tensor)[0].numpy()
            ecg_age = float(models["age"](tensor)[0, 0])
    except Exception as exc:
        return ArmResult(score=None, error=f"inference failed: {type(exc).__name__}: {exc}")

    probabilities = {c: round(float(p), 4) for c, p in zip(CLASSES, probs, strict=True)}
    score, reported = score_from(probabilities)

    # The map explains the abnormality that set the score. With none reported
    # there is nothing to explain, and a map of a near-zero probability would
    # be noise drawn as if it meant something.
    focus = max(reported, key=lambda c: WEIGHTS[c]) if reported else None
    artifacts: dict[str, bytes] = {}
    heatmap: dict = {
        "method": "lead flattening",
        "shows": None,
        "drawn": False,
        "reason": "No abnormality was reported, so there is nothing for a map to explain.",
    }
    if focus is not None:
        try:
            weights = lead_importance(models, tensor, CLASSES.index(focus))
            artifacts["gradcam"] = ecg.render(array, lead_weights=weights)
            top = [k for k in sorted(weights, key=lambda k: -weights[k])[:3] if weights[k] >= 0.05]
            carried = (
                f"{', '.join(top)} carried the most."
                if top
                else "no lead carries it on its own: it is read from all of them, "
                "so none is tinted."
            )
            heatmap = {
                "method": "lead flattening",
                "shows": LABELS[focus],
                "drawn": True,
                "lead_shares": weights,
                "note": (
                    f"Each lead was flattened in turn and the network run again. The tint and "
                    f"the figure beside each lead are the share of the {LABELS[focus].lower()} "
                    f"probability lost without it; {carried} "
                    "The finding is read from every beat, so no single moment is marked."
                ),
            }
        except Exception as exc:
            # The picture supports the reading; losing it must not cost the reading.
            heatmap = {**heatmap, "reason": f"the map could not be drawn: {type(exc).__name__}"}

    return ArmResult(
        score=score,
        raw_score=round(float(max(probs)), 4),
        details={
            # The review screen's "what moved the score" reads these two, keyed
            # by the label the underwriter sees, as it does for the chest arm.
            "findings": {LABELS[c]: probabilities[c] for c in CLASSES},
            "contributions": {LABELS[c]: points_for(c, probabilities[c]) for c in CLASSES},
            "probabilities": probabilities,
            "thresholds": THRESHOLDS,
            "weights": WEIGHTS,
            "labels": LABELS,
            "reported": reported,
            "reported_labels": [LABELS[c] for c in reported],
            "focus": focus,
            "heatmap": heatmap,
            "ecg_age": round(ecg_age, 1),
            "age_calibration": _SPEC["age_calibration"],
            "age_validation": _SPEC["age_validation"],
            "scorer": f"{_SPEC['model']} v{_SPEC['version']}",
            "validation": VALIDATION,
        },
        artifacts=artifacts,
    )
