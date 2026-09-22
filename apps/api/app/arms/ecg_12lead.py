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

**Explanation.** The gradient of the reported abnormality's probability with
respect to the input, summed over leads and smoothed, shades the tracing where
the network looked. It is the ECG's counterpart to the chest arm's heatmap.

Both weights are downloaded from Zenodo (CC-BY-4.0) and converted once by
`scripts/fetch_ecg_models.py`; the arm loads the converted files strictly and
refuses one whose hash has changed. Brazilian training data; not validated in
South Asia, and the arm says so on every reading.
"""

import hashlib
import json
import threading
from pathlib import Path

import numpy as np

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


def _saliency(models, tensor, class_index: int) -> np.ndarray:
    """|d p_class / d input|, summed over leads, smoothed to 0.25 s, scaled to [0, 1]."""
    x = tensor.clone().requires_grad_(True)
    prob = models["dx"](x)[0, class_index]
    prob.backward()
    grad = x.grad[0].abs().sum(dim=0).numpy()
    kernel = np.ones(ecg.SAMPLE_RATE // 4) / (ecg.SAMPLE_RATE // 4)
    smooth = np.convolve(grad, kernel, mode="same")
    peak = float(smooth.max())
    return smooth / peak if peak > 0 else smooth


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

    # The heatmap follows the abnormality that set the score, or the closest
    # call when nothing was reported.
    focus = (
        max(reported, key=lambda c: WEIGHTS[c])
        if reported
        else max(CLASSES, key=lambda c: probabilities[c] / THRESHOLDS[c])
    )
    artifacts: dict[str, bytes] = {}
    try:
        heat = _saliency(models, tensor, CLASSES.index(focus))
        artifacts["gradcam"] = ecg.render(array, saliency=heat)
    except Exception:
        # The picture supports the reading; losing it must not cost the reading.
        pass

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
            "ecg_age": round(ecg_age, 1),
            "age_calibration": _SPEC["age_calibration"],
            "age_validation": _SPEC["age_validation"],
            "scorer": f"{_SPEC['model']} v{_SPEC['version']}",
            "validation": VALIDATION,
        },
        artifacts=artifacts,
    )
