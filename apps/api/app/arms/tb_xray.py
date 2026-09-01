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

# The backbone weights are pinned by name and fetched by torchxrayvision, so
# what identifies *our* scorer is the logistic-regression spec. Hashing the file
# means a retrained model can never be mistaken for this one in the audit trail.
WEIGHT_HASH = (
    f"{WEIGHTS}+logreg:sha256:"
    + hashlib.sha256(Path(__file__).with_name("tb_xray_model.json").read_bytes()).hexdigest()[:32]
)

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


_model_spec: dict | None = None


def _get_spec() -> dict:
    """The trained logistic regression, loaded once.

    Plain JSON rather than a pickle: 18 weights, an intercept and the scaler's
    mean/scale are small enough to read and review, and JSON does not break
    across scikit-learn versions. Scoring is a dot product, so scikit-learn is
    not needed at runtime — only numpy.
    """
    global _model_spec
    if _model_spec is None:
        _model_spec = json.loads(MODEL_PATH.read_text())
    return _model_spec


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
    try:
        overlay = _gradcam(model, tensor, contributions, pil)
        if overlay:
            artifacts["gradcam"] = overlay
    except Exception:
        # The heatmap is supporting evidence, not the result. Losing it must not
        # cost the underwriter their score.
        pass

    # Top positive contributors, for the review screen.
    drivers = sorted(contributions.items(), key=lambda kv: -kv[1])[:5]

    return ArmResult(
        score=round(probability * 100.0, 2),
        raw_score=round(probability, 4),
        details={
            "findings": found,
            "contributions": contributions,
            "top_drivers": [name for name, weight in drivers if weight > 0],
            "backbone": WEIGHTS,
            "scorer": f"{spec['model']} v{spec['version']} trained on {spec['trained_on']}",
            "validation": spec["validation"],
            "cv_auc": spec["cv_auc_mean"],
        },
        artifacts=artifacts,
    )


def _gradcam(model, tensor, contributions: dict[str, float], original) -> bytes | None:
    """Heatmap over the finding that contributed most to the TB score.

    Targeting the top *contributor* rather than the highest raw probability
    matters: the heatmap should show what actually moved the decision, not
    whatever the backbone happened to be most confident about. A finding the
    model weighs at zero is not evidence, however high its probability.
    """
    import torch
    from PIL import Image
    from pytorch_grad_cam import GradCAM
    from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

    ranked = sorted(contributions, key=lambda k: -contributions[k])
    target_name = next(
        (k for k in ranked if contributions[k] > 0 and k in model.pathologies), None
    )
    if target_name is None:
        return None

    index = list(model.pathologies).index(target_name)

    cam = GradCAM(model=model, target_layers=[model.features[-1]])
    grayscale = cam(
        input_tensor=tensor[None, ...].clone().requires_grad_(True),
        targets=[ClassifierOutputTarget(index)],
    )[0]

    heat = (grayscale - grayscale.min()) / (np.ptp(grayscale) or 1.0)

    # Blend against the same 224x224 view the model saw, so the highlight lines
    # up with the pixels that produced it.
    base = np.asarray(original.convert("L").resize((224, 224)), dtype=np.float32) / 255.0
    rgb = np.stack([base, base, base], axis=-1)

    # Red overlay: raise red where the model looked, damp green and blue.
    rgb[..., 0] = np.clip(rgb[..., 0] + heat * 0.6, 0, 1)
    rgb[..., 1] *= 1.0 - heat * 0.4
    rgb[..., 2] *= 1.0 - heat * 0.4

    buffer = BytesIO()
    Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB").save(buffer, format="PNG")
    assert torch  # keep the import meaningful to linters
    return buffer.getvalue()
