"""Diabetic retinopathy screening from a colour fundus photograph.

Built the same way as the chest X-ray arm, for the same reason. A published
backbone turns the photograph into features; a logistic regression we trained
turns the features into a score; and the score is judged on hospitals the model
has never seen.

**The backbone is FLAIR** (Silva-Rodriguez et al., Medical Image Analysis 2025;
Apache-2.0): a ResNet-50 pretrained on 288,307 fundus photographs from 37 public
datasets. We use its vision tower unchanged and frozen.

**The head is ours**, fitted on DDR: 12,522 photographs from 147 hospitals and
42 camera types (`scripts/dr_experiment.py`; weights in `dr_fundus_model.json`).
Many sites is the point. With one hospital per class a model learns the camera,
which is exactly what went wrong with the Kaggle TB set.

**What the score means.** The probability, times 100, that the photograph shows
*referable* retinopathy: ICDR grade 2 (moderate) or worse. That is the decision
every regulated screening system is judged on, so it is the one with published
numbers to compare against. The five-point grade is reported beside it for the
underwriter to read, and does not set the score.

**Which numbers are honest.** FLAIR's pretraining included DDR, APTOS and the
IDRiD training set *with their grades*, so a result on any of those says nothing
about a new patient — the backbone has seen the answers. Measured on a small
pilot, that alone was worth five points of AUC (0.983 on all of IDRiD against
0.934 on the part FLAIR never saw). Only results on data it never saw are
reported as validation; see `_SPEC["validation"]`, which every screen that shows
a score also shows.

This replaces `eyepacs_dr.py`, which described itself as a ResNet-50 validated
at 0.942 AUC and was in fact a count of dark and bright pixels. Measured on ten
real photographs it scored a proliferative eye below two healthy ones.

An abnormal reading is grounds for a closer look, never a diagnosis.

torch is an optional dependency (`uv sync --extra vision`). Without it
`available()` returns False and the pipeline degrades rather than crashing.
"""

import hashlib
import json
import threading
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np

from app.arms import ArmResult
from app.arms.fundus import NotAFundusPhoto, frame
from app.config import settings

NAME = "dr_fundus"
VERSION = "1.0.0-flair-logreg"

MODEL_PATH = Path(__file__).with_name("dr_fundus_model.json")

# The side, in pixels, of the square FLAIR was trained on.
INPUT_SIZE = 512

# Versioned separately from the weights, as for every arm: the same weights fed
# a differently framed image are a different model in practice.
PREPROCESSING_VERSION = "fov-crop-pad-square-512-unit-range"

# 533 MB, so it is not in the repository. Fetched once, on first use, the way
# torchxrayvision fetches the chest model's. Pinned by hash: a file that does
# not match is refused rather than loaded, because weights that changed under
# us would make every stored score unattributable.
BACKBONE = "flair-resnet50"
BACKBONE_URL = "https://huggingface.co/jusiro2/FLAIR/resolve/main/model.safetensors"
BACKBONE_SHA256 = "050334cd934fa3126435c202c41f493ca222fc3fe3ea9c50cf21f67c792a1440"
BACKBONE_PATH = settings.data_dir / "dr" / "models" / "flair.safetensors"

_SPEC: dict = json.loads(MODEL_PATH.read_text())

WEIGHT_HASH = (
    f"{BACKBONE}:sha256:{BACKBONE_SHA256[:16]}+logreg:sha256:"
    + hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:32]
)

VALIDATION: str = _SPEC["validation"]
ICDR_CLASSES: tuple[str, ...] = tuple(_SPEC["classes"])

# ICDR grade 2, moderate non-proliferative retinopathy, is where a patient is
# referred to an ophthalmologist.
REFERABLE_FROM = 2

_model = None
_model_lock = threading.Lock()


def available() -> bool:
    try:
        import safetensors  # noqa: F401
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError:
        return False
    return True


def _fetch_backbone() -> None:
    """Download the backbone weights, to a `.part` first so an interrupted
    download is never mistaken for a finished one."""
    BACKBONE_PATH.parent.mkdir(parents=True, exist_ok=True)
    partial = BACKBONE_PATH.with_name(BACKBONE_PATH.name + ".part")

    request = urllib.request.Request(BACKBONE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    partial.replace(BACKBONE_PATH)


def _get_model():
    """FLAIR's vision tower, loaded once per process.

    Locked, because scoring runs on worker threads and two applications arriving
    together would otherwise both start a 533 MB download.
    """
    global _model
    with _model_lock:
        if _model is not None:
            return _model

        import torch
        import torchvision
        from safetensors.torch import load_file

        if not BACKBONE_PATH.exists():
            _fetch_backbone()

        digest = hashlib.sha256()
        with open(BACKBONE_PATH, "rb") as handle:
            while chunk := handle.read(1 << 22):
                digest.update(chunk)
        if digest.hexdigest() != BACKBONE_SHA256:
            raise RuntimeError(
                f"{BACKBONE_PATH.name} does not match the pinned hash; delete it to re-download"
            )

        # The checkpoint also holds a text encoder. Only the vision tower is
        # used, and it is a stock torchvision ResNet-50 with the classifier
        # removed, so no FLAIR code is needed to run it.
        prefix = "vision_model.model."
        state = load_file(str(BACKBONE_PATH))
        resnet = torchvision.models.resnet50(weights=None)
        resnet.fc = torch.nn.Identity()
        resnet.load_state_dict(
            {k[len(prefix) :]: v for k, v in state.items() if k.startswith(prefix)}
        )
        _model = resnet.eval()
        return _model


def to_tensor(framed_image):
    """The framed photograph as FLAIR expects it: RGB in [0, 1], and nothing
    else. No mean, no standard deviation — FLAIR was trained without them, and
    adding the usual ImageNet ones fails silently, as confident nonsense."""
    import torch

    pixels = np.asarray(framed_image, dtype=np.float32) / 255.0
    return torch.from_numpy(pixels).permute(2, 0, 1)


def _forward(model, tensor) -> tuple[np.ndarray, np.ndarray]:
    """(features, activations) for one photograph, from a single pass.

    `activations` is the last convolutional block's output, 2048 channels on a
    16x16 grid. `features` is its average over that grid — which is all a
    ResNet's pooling layer does — so the two are the same forward pass and the
    heatmap below costs nothing extra.
    """
    import torch

    with torch.inference_mode():
        x = tensor[None, ...]
        x = model.maxpool(model.relu(model.bn1(model.conv1(x))))
        x = model.layer4(model.layer3(model.layer2(model.layer1(x))))
        activations = x[0].numpy()
    return activations.mean(axis=(1, 2)), activations


def features(image_bytes: bytes) -> np.ndarray:
    """The 2048 numbers FLAIR reduces one photograph to.

    Raises on failure; `run()` wraps it. Exposed so offline experiments can
    extract features through exactly the code the platform serves with.
    """
    from PIL import Image

    with Image.open(BytesIO(image_bytes)) as image:
        framed = frame(image, INPUT_SIZE)
    return _forward(_get_model(), to_tensor(framed.image))[0]


def predict(found: np.ndarray) -> tuple[float, list[float]]:
    """(probability of referable retinopathy, probability of each ICDR grade).

    Two logistic regressions over the same features. Plain JSON and numpy, as
    for the chest arm: scikit-learn trains them and is not needed to run them.
    The scaler is folded into the weights, so each is one dot product.
    """
    binary = _SPEC["referable"]
    logit = float(found @ np.array(binary["coef"]) + binary["intercept"])
    referable = 1.0 / (1.0 + np.exp(-logit))

    grading = _SPEC["grading"]
    logits = np.array(grading["coef"]) @ found + np.array(grading["intercept"])
    shifted = np.exp(logits - logits.max())
    return float(referable), [float(p) for p in shifted / shifted.sum()]


def run(image_bytes: bytes) -> ArmResult:
    """Score one fundus photograph. Never raises — a failure comes back as an
    ArmResult with `score=None` and the reason, so the pipeline records why and
    moves the application to insufficient evidence."""
    if not available():
        return ArmResult(score=None, error="torch not installed (uv sync --extra vision)")

    try:
        from PIL import Image

        with Image.open(BytesIO(image_bytes)) as image:
            framed = frame(image, INPUT_SIZE)
    except NotAFundusPhoto as exc:
        # Declining is the right answer here, not a failure. A grading model
        # given something else does not decline, it answers.
        return ArmResult(score=None, error=f"not gradable: {exc}")
    except Exception as exc:
        return ArmResult(score=None, error=f"unreadable image: {exc}")

    try:
        found, activations = _forward(_get_model(), to_tensor(framed.image))
    except Exception as exc:
        return ArmResult(score=None, error=f"inference failed: {type(exc).__name__}: {exc}")

    try:
        referable, grades = predict(found)
    except Exception as exc:
        return ArmResult(score=None, error=f"scoring failed: {type(exc).__name__}: {exc}")

    artifacts = {}
    try:
        overlay = _heatmap(activations, framed.image)
        if overlay:
            artifacts["gradcam"] = overlay
    except Exception:
        # The heatmap is supporting evidence, not the result. Losing it must not
        # cost the underwriter their score.
        pass

    grade = int(np.argmax(grades))
    probabilities = {
        name: round(p, 4) for name, p in zip(ICDR_CLASSES, grades, strict=True)
    }

    return ArmResult(
        score=round(referable * 100.0, 2),
        raw_score=round(referable, 4),
        details={
            # What the review screen's "what moved the score" panel reads. Each
            # grade pushes toward referable by its own probability or away from
            # it, and the five add up to exactly the distance from an even call.
            "findings": probabilities,
            "contributions": {
                name: round(p if index >= REFERABLE_FROM else -p, 4)
                for index, (name, p) in enumerate(zip(ICDR_CLASSES, grades, strict=True))
            },
            "icdr_grade": grade,
            "grade_name": ICDR_CLASSES[grade],
            "referable_dr": bool(referable >= 0.5),
            "referable_probability": round(referable, 4),
            "class_probabilities": probabilities,
            "framing": {
                "lit_fraction": framed.lit_fraction,
                "colour_spread": framed.colour_spread,
                "brightness": framed.brightness,
            },
            "backbone": BACKBONE,
            "scorer": f"{_SPEC['model']} v{_SPEC['version']} trained on {_SPEC['trained_on']}",
            "validation": VALIDATION,
        },
        artifacts=artifacts,
    )


def _heatmap(activations: np.ndarray, framed_image) -> bytes | None:
    """Where in the photograph the referable call came from.

    Exact, not estimated. The head is a linear layer on features that are an
    average over a 16x16 grid, so the score is *itself* an average over that
    grid: weights . activations, cell by cell. Drawing those cells is the score
    taken apart by location. Grad-CAM reduces to precisely this for a network of
    this shape, which is why the artifact is filed as one; computing it directly
    needs no backward pass and has none of Grad-CAM's smoothing to go wrong —
    the first version, built on Grad-CAM, lit up the black corner of the frame.
    """
    from PIL import Image

    coef = np.array(_SPEC["referable"]["coef"], dtype=np.float32)
    toward = np.maximum(np.tensordot(coef, activations, axes=1), 0.0)
    if toward.max() <= 0:
        # Nothing in the photograph pushed toward a referable call.
        return None

    size = framed_image.size
    heat = np.asarray(
        Image.fromarray(toward / toward.max()).resize(size, Image.Resampling.BICUBIC),
        dtype=np.float32,
    )

    # Only the retina can be evidence. The network's cells along the rim of the
    # disc overlap the black surround, and a highlight out there tells the
    # underwriter nothing and looks like a bug.
    base = np.asarray(framed_image, dtype=np.float32) / 255.0
    heat = np.clip(heat, 0.0, 1.0) * (base.mean(axis=2) > 0.06)

    # Cyan, not the red the chest arm uses: a retina is already red, and
    # haemorrhages are the darkest red in it, so a red highlight would bury
    # exactly what it is pointing at.
    strength = np.clip((heat - 0.25) / 0.75, 0.0, 1.0)[..., None] * 0.65
    blended = base * (1.0 - strength) + np.array([0.0, 1.0, 1.0]) * strength

    buffer = BytesIO()
    Image.fromarray((blended * 255).astype(np.uint8), mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()
