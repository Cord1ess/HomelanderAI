"""Chest X-ray screening arm.

Ported from the Nirnoy reference project
(`Reference/Nirnoy/backend/specialists/txrv.py`).

Two things carried over verbatim because getting them wrong fails silently:

1. **Preprocessing.** Normalise to [-1024, 1024], centre-crop, resize to 224.
   Skip any of it and the model returns confident nonsense rather than an error.
2. **Weights must be `densenet121-res224-all`.** Other weight sets in
   torchxrayvision have untrained labels that predict essentially at random.

**The underlying model has no tuberculosis label.** It reports 18 general
radiological findings. We turn those into a TB score with a logistic regression
trained on the Shenzhen dataset (`scripts/tb_experiment.py`; weights in
`tb_xray_model.json`).

Measured on our own code:

| Scoring | Data | AUC |
|---|---|---|
| Hand-weighted composite | Kaggle samples (source-confounded) | 0.450 |
| Hand-weighted composite | Shenzhen (single source) | 0.772 |
| **Logistic regression** | **Shenzhen, 5-fold CV** | **0.877** |

The first two rows are why the dataset matters more than the model: identical
code, and the only thing that changed is whether both classes came from the same
hospital. See docs/SPEC.md §9.

**This is internal validation.** The model has never been tested on a different
hospital, and published TB work routinely sees large drops when it is (one study
fell from 85% to 65%). Treat 0.877 as an upper bound, not a promise. Montgomery
is the intended external test set and is not yet obtainable — see
`scripts/fetch_tb_data.py`.

An abnormal reading is grounds for escalation, never a diagnosis.

torch is an optional dependency (`uv sync --extra vision`). Without it,
`available()` returns False and the pipeline degrades rather than crashing, so
nobody working on the dashboard or database needs a multi-GB download.
"""

import hashlib
import json
import math
from io import BytesIO
from pathlib import Path

import numpy as np

from app.arms import ArmResult

NAME = "tb_xray"
VERSION = "1.0.0-txrv-logreg"

MODEL_PATH = Path(__file__).with_name("tb_xray_model.json")

WEIGHTS = "densenet121-res224-all"

# Versioned separately from the weights: the same weights with different
# preprocessing are a different model in practice, and every stored score has to
# say which one produced it.
PREPROCESSING_VERSION = "xrv-normalize-centercrop-224"

# The trained scorer, read once. Small enough (about 1.5 KB) that loading it at
# import costs nothing, and it is needed immediately to describe the arm.
_SPEC: dict = json.loads(MODEL_PATH.read_text())

# The backbone weights are pinned by name and fetched by torchxrayvision, so
# what identifies *our* scorer is the logistic-regression spec. Hashing the file
# means a retrained model can never be mistaken for this one in the audit trail.
WEIGHT_HASH = (
    f"{WEIGHTS}+logreg:sha256:"
    + hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:32]
)

# How this model was tested. Carried on the arm so it reaches the intake form
# and the review screen without either of them hard-coding it.
VALIDATION: str = _SPEC["validation"]

# The map is drawn only to explain a reading above the low tier.
LOW_TIER_TOP = 30.0
# Occlusion map: a 7x7 grid of 32 px regions on the 224 px film; a region
# must lower the TB logit by at least this much for any map to be drawn.
OCCLUSION_GRID = 7
MIN_LOGIT_FALL = 0.05

# Findings that raise TB suspicion on a plain film. The model returns all 18;
# these are the ones the composite is built from.
TB_SUGGESTIVE = (
    "Consolidation",
    "Infiltration",
    "Nodule",
    "Lung Opacity",
    "Fibrosis",
    "Effusion",
    "Pleural_Thickening",
    "Lung Lesion",
)

_model = None


def available() -> bool:
    try:
        import torch  # noqa: F401
        import torchxrayvision  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model():
    """Loaded once per process. Model construction downloads weights on first
    use and takes seconds, which we do not want on every application."""
    global _model
    if _model is None:
        import torchxrayvision as xrv

        _model = xrv.models.DenseNet(weights=WEIGHTS).eval()
    return _model


def _get_spec() -> dict:
    """The trained logistic regression.

    Plain JSON rather than a pickle: 18 weights, an intercept and the scaler's
    mean/scale are small enough to read and review, and JSON does not break
    across scikit-learn versions. Scoring is a dot product, so scikit-learn is
    not needed at runtime — only numpy.
    """
    return _SPEC


def predict(found: dict[str, float]) -> tuple[float, dict[str, float]]:
    """TB probability for one set of findings, plus each feature's signed
    contribution to the decision.

    The contributions are what makes this explainable: they say which findings
    pushed the score up and by how much, which is exactly what an underwriter
    needs and what a bare probability cannot give.
    """
    spec = _get_spec()

    values = np.array([found.get(name, 0.0) for name in spec["features"]])
    standardised = (values - np.array(spec["mean"])) / np.array(spec["scale"])
    weighted = standardised * np.array(spec["coef"])

    logit = float(weighted.sum()) + spec["intercept"]
    probability = 1.0 / (1.0 + np.exp(-logit))

    contributions = {
        name: round(float(value), 4)
        for name, value in zip(spec["features"], weighted, strict=True)
    }
    return float(probability), contributions


# A radiograph has contrast: lungs dark, bone and soft tissue light. Real
# films sit far above this spread of grey levels (0-255); a blank or flat image
# sits at zero, and the model handed one still answers — it read a featureless
# grey square as 75, elevated.
MIN_GREY_SPREAD = 8.0
# Radiographs are grey. A colour photograph — a fundus photo, a phone picture
# of something else — has channels that disagree by far more than this.
MAX_COLOUR_SPREAD = 25.0


def not_a_radiograph(pil) -> str | None:
    """Why this image cannot be a radiograph, or None if it could be."""
    rgb = np.asarray(pil.convert("RGB"), dtype=np.float32)
    colour = float((rgb.max(axis=2) - rgb.min(axis=2)).mean())
    if colour > MAX_COLOUR_SPREAD:
        return "it is a colour photograph; radiographs are greyscale"
    if float(rgb.mean(axis=2).std()) < MIN_GREY_SPREAD:
        return "it is blank or nearly uniform; a radiograph has contrast"
    return None


def score_from(probability: float) -> float:
    """The model's probability placed on the 0-100 tier scale.

    Not the probability itself. The model was fitted on Shenzhen, where half
    the films are TB, so an ordinary film reads high: as a score, its
    probability put 71% of Montgomery's normal films above the low tier and
    half of TBX11K's healthy films in senior review. The anchors put the top
    of the low tier at the 90th percentile of films without TB and senior
    review at the 98th, linear in the logit and clamped
    (scripts/tb_calibrate.py). Without anchors the probability is used as
    before.
    """
    anchors = _get_spec().get("score_anchors")
    if not anchors:
        return round(probability * 100.0, 2)
    p = min(max(probability, 1e-9), 1 - 1e-9)
    logit = math.log(p / (1 - p))
    low, senior = anchors["logit_low_tier_top"], anchors["logit_senior_review"]
    return round(max(0.0, min(100.0, 30.0 + 35.0 * (logit - low) / (senior - low))), 2)


def composite(found: dict[str, float]) -> float:
    """Collapse the TB-suggestive findings into one 0-1 number.

    Peak-weighted: one strongly abnormal finding matters more than several mild
    ones, but the spread still counts. Same formula the reference project used
    for its validation, kept so its published numbers remain comparable.

    Measured AUC 0.450 on the reference samples — see docs/SPEC.md §6. This is
    the baseline the learned model has to beat.
    """
    values = [found.get(k, 0.0) for k in TB_SUGGESTIVE]
    if not values:
        return 0.0
    return max(values) * 0.6 + (sum(values) / len(values)) * 0.4


def _preprocess(pil):
    """The exact preprocessing the weights expect. Carried over verbatim from
    the reference project — getting any step wrong fails silently."""
    import torch
    import torchvision
    import torchxrayvision as xrv

    img = np.array(pil.convert("L")).astype(np.float32)
    img = xrv.datasets.normalize(img, 255)  # -> [-1024, 1024]
    img = img[None, ...]  # add channel dim

    transform = torchvision.transforms.Compose(
        [xrv.datasets.XRayCenterCrop(), xrv.datasets.XRayResizer(224)]
    )
    return torch.from_numpy(transform(img))


def findings(image_bytes: bytes) -> dict[str, float]:
    """The 18 pathology probabilities for one image.

    Raises on failure — `run()` wraps this and converts errors into an
    ArmResult. Exposed separately so offline experiments can extract features
    over a whole dataset without paying for Grad-CAM on every image.
    """
    import torch
    from PIL import Image

    pil = Image.open(BytesIO(image_bytes))
    pil.load()

    tensor = _preprocess(pil)
    model = _get_model()
    with torch.no_grad():
        output = model(tensor[None, ...])[0]

    return {
        pathology: round(float(value), 4)
        for pathology, value in zip(model.pathologies, output, strict=False)
        if pathology  # torchxrayvision pads unused slots with empty labels
    }


def run(image_bytes: bytes) -> ArmResult:
    """Score one chest X-ray. Never raises — failures come back as an
    ArmResult with `score=None` and an error, so the pipeline can record the
    reason and move the application to insufficient evidence."""
    if not available():
        return ArmResult(score=None, error="torch not installed (uv sync --extra vision)")

    try:
        from PIL import Image
    except ImportError as exc:
        return ArmResult(score=None, error=f"vision dependencies missing: {exc}")

    try:
        pil = Image.open(BytesIO(image_bytes))
        pil.load()
    except Exception as exc:
        return ArmResult(score=None, error=f"unreadable image: {exc}")

    # Refuse rather than answer: the model has no way to say "this is not a
    # chest film", so it would invent a number.
    problem = not_a_radiograph(pil)
    if problem:
        return ArmResult(score=None, error=f"not a radiograph: {problem}")

    try:
        found = findings(image_bytes)
        tensor = _preprocess(pil)
        model = _get_model()
    except Exception as exc:
        return ArmResult(score=None, error=f"inference failed: {type(exc).__name__}: {exc}")

    try:
        probability, contributions = predict(found)
    except Exception as exc:
        return ArmResult(score=None, error=f"scoring failed: {type(exc).__name__}: {exc}")

    spec = _get_spec()

    artifacts = {}
    heatmap: dict = {
        "method": f"occlusion, {OCCLUSION_GRID}x{OCCLUSION_GRID} regions",
        "drawn": False,
        "reason": "The reading is in the low tier, so there is nothing for a map to explain.",
    }
    score = score_from(probability)
    if score > LOW_TIER_TOP:
        try:
            overlay = _heatmap(model, tensor)
            if overlay:
                artifacts["gradcam"] = overlay
                heatmap = {
                    **heatmap,
                    "drawn": True,
                    "reason": None,
                    "note": (
                        "Each region of the film was greyed out in turn and the model run again; "
                        "red marks the regions whose loss lowered the TB score most. It shows "
                        "what the model leaned on, which is not always where a radiologist "
                        "would point: on films with expert-marked TB it found the marked area "
                        "about four times in ten."
                    ),
                }
            else:
                heatmap = {
                    **heatmap,
                    "reason": "No single region of the film lowers the TB score when hidden.",
                }
        except Exception as exc:
            # The heatmap is supporting evidence, not the result. Losing it must not
            # cost the underwriter their score.
            heatmap = {**heatmap, "reason": f"the map could not be drawn: {type(exc).__name__}"}

    # Top positive contributors, for the review screen.
    drivers = sorted(contributions.items(), key=lambda kv: -kv[1])[:5]

    return ArmResult(
        score=score,
        raw_score=round(probability, 4),
        details={
            "findings": found,
            "contributions": contributions,
            "top_drivers": [name for name, weight in drivers if weight > 0],
            "backbone": WEIGHTS,
            "scorer": f"{spec['model']} v{spec['version']} trained on {spec['trained_on']}",
            "validation": spec["validation"],
            "cv_auc": spec["cv_auc_mean"],
            "heatmap": heatmap,
        },
        artifacts=artifacts,
    )


def _tb_logit(model, batch):
    """The TB score's logit for a batch of preprocessed films — the regression
    over the backbone's findings, differentiable end to end."""
    import torch

    spec = _get_spec()
    names = list(model.pathologies)
    index = [names.index(f) for f in spec["features"]]
    weight = torch.tensor(
        np.array(spec["coef"]) / np.array(spec["scale"]), dtype=torch.float32
    )
    return (model(batch)[:, index] * weight).sum(1)


def _heatmap(model, tensor) -> bytes | None:
    """Which regions of the film the TB score depends on: occlusion.

    The film is cut into a 7x7 grid; each region is greyed out in turn and the
    model run again, 49 films in one batch. A region is as red as the TB logit
    falls without it. Measured, not estimated.

    Chosen by measurement (docs/HEATMAPS.md). On TBX11K films with
    radiologist-drawn TB boxes, the Grad-CAM this arm used to draw put its
    brightest point inside a box no more often than chance (13% against 9%)
    and less of its heat in the boxes than their area. Occlusion: 38%, and 1.8
    times their area. SmoothGrad sat between the two.
    """
    import torch
    import torch.nn.functional as F
    from PIL import Image

    step = tensor.shape[-1] // OCCLUSION_GRID
    with torch.no_grad():
        base = float(_tb_logit(model, tensor[None])[0])
        batch = tensor[None].repeat(OCCLUSION_GRID * OCCLUSION_GRID, 1, 1, 1)
        for i in range(OCCLUSION_GRID):
            for j in range(OCCLUSION_GRID):
                rows, cols = slice(i * step, (i + 1) * step), slice(j * step, (j + 1) * step)
                # 0 is mid-grey in the model's units, [-1024, 1024].
                batch[i * OCCLUSION_GRID + j, :, rows, cols] = 0.0
        falls = base - _tb_logit(model, batch).numpy()
    falls = np.maximum(falls.reshape(OCCLUSION_GRID, OCCLUSION_GRID), 0.0)
    if falls.max() < MIN_LOGIT_FALL:
        # Nothing on its own matters: the reading comes from the film as a whole.
        return None
    heat = torch.from_numpy((falls / falls.max()).astype(np.float32))[None, None]
    heat = F.interpolate(heat, size=tensor.shape[-2:], mode="bilinear", align_corners=False)
    heat = heat[0, 0].numpy()

    # The backdrop is the tensor the model was actually given, mapped back from
    # [-1024, 1024] to [0, 1] — the same framing the regions were cut from.
    base_img = np.clip((tensor[0].numpy() + 1024.0) / 2048.0, 0.0, 1.0)
    rgb = np.stack([base_img, base_img, base_img], axis=-1)

    # Red, with a ring round the strongest regions so the anatomy inside stays
    # visible.
    strength = np.clip((heat - 0.3) / 0.7, 0.0, 1.0)[..., None] * 0.45
    rgb = rgb * (1.0 - strength) + np.array([1.0, 0.1, 0.05]) * strength
    marked = torch.from_numpy((heat >= 0.6).astype(np.float32))[None, None]
    ring = (F.max_pool2d(marked, 5, stride=1, padding=2) - marked)[0, 0].numpy() > 0
    rgb[ring] = np.array([1.0, 0.15, 0.1])

    buffer = BytesIO()
    Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()
