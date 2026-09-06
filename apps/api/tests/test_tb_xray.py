"""Chest X-ray arm.

Split in two: the composite maths is pure and always runs; anything that loads
the model is skipped when torch is not installed, so the suite stays green for
teammates who never run `uv sync --extra vision`.
"""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.arms import ARMS, ArmResult, tb_xray

SAMPLES = (
    Path(__file__).resolve().parents[3] / "Reference" / "Nirnoy" / "assets" / "samples"
)

needs_vision = pytest.mark.skipif(
    not tb_xray.available(), reason="vision extra not installed"
)
needs_samples = pytest.mark.skipif(
    not SAMPLES.exists(), reason="reference samples not present"
)


def png(size=(256, 256), color=128) -> bytes:
    buffer = BytesIO()
    Image.new("L", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


# ── pure maths — no torch needed ─────────────────────────────────────────────


def test_composite_is_peak_weighted():
    """max * 0.6 + mean * 0.4, over the TB-suggestive findings only."""
    findings = dict.fromkeys(tb_xray.TB_SUGGESTIVE, 0.0)
    findings["Nodule"] = 1.0

    expected = 1.0 * 0.6 + (1.0 / len(tb_xray.TB_SUGGESTIVE)) * 0.4
    assert tb_xray.composite(findings) == pytest.approx(expected)


def test_composite_ignores_findings_outside_the_tb_set():
    """Cardiomegaly is a real finding but says nothing about TB."""
    assert tb_xray.composite({"Cardiomegaly": 1.0, "Hernia": 1.0}) == 0.0


def test_composite_handles_empty_input():
    assert tb_xray.composite({}) == 0.0


def test_composite_is_bounded():
    assert tb_xray.composite(dict.fromkeys(tb_xray.TB_SUGGESTIVE, 1.0)) == pytest.approx(1.0)
    assert tb_xray.composite(dict.fromkeys(tb_xray.TB_SUGGESTIVE, 0.0)) == 0.0


# ── the learned scorer — pure maths, no torch needed ─────────────────────────


def test_model_file_is_present_and_sane():
    spec = tb_xray._get_spec()

    assert len(spec["features"]) == 18
    for key in ("mean", "scale", "coef"):
        assert len(spec[key]) == 18, f"{key} must line up with the features"
    assert spec["trained_on"] == "shenzhen"
    assert 0.0 < spec["cv_auc_mean"] <= 1.0


def test_predict_returns_probability_and_contributions():
    spec = tb_xray._get_spec()
    found = dict.fromkeys(spec["features"], 0.5)

    probability, contributions = tb_xray.predict(found)

    assert 0.0 <= probability <= 1.0
    assert set(contributions) == set(spec["features"])


def test_predict_is_monotonic_in_a_positive_feature():
    """Raising a finding the model weights toward TB must raise the score.
    If this fails, the standardisation or sign handling is wrong."""
    spec = tb_xray._get_spec()
    top = max(zip(spec["features"], spec["coef"], strict=True), key=lambda kv: kv[1])[0]

    low = dict.fromkeys(spec["features"], 0.0)
    high = {**low, top: 1.0}

    assert tb_xray.predict(high)[0] > tb_xray.predict(low)[0]


def test_predict_beats_composite_on_held_out_intuition():
    """The learned scorer and the old heuristic must genuinely differ — if they
    agreed everywhere, replacing one with the other bought nothing."""
    spec = tb_xray._get_spec()
    found = dict.fromkeys(spec["features"], 0.0)
    found["Lung Lesion"] = 0.9

    learned = tb_xray.predict(found)[0]
    heuristic = tb_xray.composite(found)

    assert abs(learned - heuristic) > 0.01


def test_missing_features_default_to_zero_rather_than_raising():
    probability, _ = tb_xray.predict({"Nodule": 0.4})
    assert 0.0 <= probability <= 1.0


# ── registry ─────────────────────────────────────────────────────────────────


def test_arm_is_registered():
    arm = ARMS["tb_xray"]

    assert arm.arm_type == "vision"
    assert arm.version
    assert callable(arm.run)
    assert callable(arm.available)


def test_arm_result_usable_reflects_score_presence():
    assert ArmResult(score=12.0).usable is True
    assert ArmResult(score=None, error="boom").usable is False


# ── failure paths — no torch needed, run() guards before importing ───────────


def test_garbage_input_returns_error_not_exception():
    result = tb_xray.run(b"definitely not an image")

    assert result.score is None
    assert result.error
    assert result.usable is False


def test_empty_input_returns_error_not_exception():
    result = tb_xray.run(b"")

    assert result.score is None
    assert result.error


# ── real inference ───────────────────────────────────────────────────────────


@needs_vision
def test_scores_a_synthetic_image():
    result = tb_xray.run(png())

    assert result.error is None
    assert result.usable
    assert 0.0 <= result.score <= 100.0
    assert result.details["findings"]
    assert result.details["backbone"] == tb_xray.WEIGHTS
    assert result.details["contributions"]
    # The score must be reported alongside how it was produced and how well it
    # was validated — an underwriter and an examiner both need that context.
    assert "logistic_regression" in result.details["scorer"]
    assert "NOT externally validated" in result.details["validation"]


@needs_vision
@needs_samples
def test_scores_a_real_chest_xray():
    sample = next(iter(sorted((SAMPLES / "TB").glob("*.png"))))
    result = tb_xray.run(sample.read_bytes())

    assert result.error is None
    assert 0.0 <= result.score <= 100.0

    findings = result.details["findings"]
    assert len(findings) == 18, "expected the full 18-label output"
    assert all(0.0 <= v <= 1.0 for v in findings.values())

    # Every TB-suggestive label the composite reads must actually be present,
    # otherwise the composite is silently averaging over missing keys.
    for label in tb_xray.TB_SUGGESTIVE:
        assert label in findings, f"{label} missing from model output"


@needs_vision
@needs_samples
def test_produces_a_readable_gradcam():
    sample = next(iter(sorted((SAMPLES / "TB").glob("*.png"))))
    result = tb_xray.run(sample.read_bytes())

    assert "gradcam" in result.artifacts
    overlay = Image.open(BytesIO(result.artifacts["gradcam"]))
    overlay.load()
    assert overlay.format == "PNG"
    assert overlay.size == (224, 224)


@needs_vision
def test_score_is_deterministic():
    """Same bytes in, same score out. The model is in eval mode with no
    dropout, so any drift here means state is leaking between calls."""
    image = png()
    assert tb_xray.run(image).score == tb_xray.run(image).score


# ── the known limitation, recorded rather than hidden ────────────────────────


@needs_vision
@needs_samples
def test_tb_and_normal_both_score_but_separation_is_not_assumed():
    """This model has NO tuberculosis label.

    The reference project measured -0.051 separation between TB and Normal on
    labelled data — the wrong direction — and that reproduces here. This test
    therefore asserts only that both classes produce *valid* readings.

    Do not "fix" this by asserting tb_score > normal_score. It will fail, and it
    would be asserting something the model was never trained to do. The real fix
    is a fine-tuned TB classifier, which changes tb_xray.py and nothing else.
    """
    tb = tb_xray.run(next(iter(sorted((SAMPLES / "TB").glob("*.png")))).read_bytes())
    normal = tb_xray.run(next(iter(sorted((SAMPLES / "Normal").glob("*.png")))).read_bytes())

    for result in (tb, normal):
        assert result.usable
        assert 0.0 <= result.score <= 100.0


# ── the heatmap has to line up with what the model saw ───────────────────────


SHENZHEN = Path(__file__).resolve().parents[3] / "data" / "shenzhen"

needs_shenzhen = pytest.mark.skipif(
    not SHENZHEN.exists(), reason="run scripts/fetch_tb_data.py shenzhen"
)


@needs_vision
@needs_shenzhen
def test_the_heatmap_is_drawn_on_the_image_the_model_was_given():
    """Preprocessing centre-crops to a square before resizing to 224.

    The overlay used to be built by resizing the *original* image to 224x224
    instead, which is a different framing — and chest radiographs are not
    square. On the widest image in the set that put the backdrop 35 pixels out
    of 224 while the CAM itself is only 7x7, so the highlight could sit more
    than a whole cell away from the finding that produced it. For a feature
    whose entire purpose is "show me where", that is the one thing it must not
    do.

    Correlation rather than equality: the red channel carries the heat, so the
    overlay is never a pixel-perfect copy of the backdrop.
    """
    import numpy as np

    # The least square image available — where the two framings differ most.
    candidates = sorted(SHENZHEN.glob("*.png"))[:60]
    path = min(candidates, key=lambda p: min(Image.open(p).size) / max(Image.open(p).size))

    original = Image.open(path)
    original.load()
    result = tb_xray.run(path.read_bytes())

    assert "gradcam" in result.artifacts, "no heatmap was produced"
    overlay = np.asarray(Image.open(BytesIO(result.artifacts["gradcam"])), dtype=np.float32) / 255.0
    assert overlay.shape == (224, 224, 3)

    def correlation(a, b):
        a = a.ravel() - a.mean()
        b = b.ravel() - b.mean()
        return float((a @ b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # Green is the backdrop damped by the heat, so it tracks the backdrop.
    green = overlay[..., 1]
    model_input = np.clip((tb_xray._preprocess(original)[0].numpy() + 1024.0) / 2048.0, 0, 1)
    plain_resize = np.asarray(original.convert("L").resize((224, 224)), dtype=np.float32) / 255.0

    assert correlation(green, model_input) > correlation(green, plain_resize), (
        "the heatmap backdrop matches a plain resize better than the model's own "
        "input — the centre-crop alignment has regressed"
    )


@needs_vision
@needs_shenzhen
def test_the_heatmap_actually_highlights_something():
    """A uniform overlay would pass an alignment check and tell nobody
    anything."""
    import numpy as np

    path = sorted(SHENZHEN.glob("*_1.png"))[0]
    result = tb_xray.run(path.read_bytes())

    overlay = np.asarray(Image.open(BytesIO(result.artifacts["gradcam"])), dtype=np.float32) / 255.0
    heat = overlay[..., 0] - overlay[..., 2]  # red lifted, blue damped

    assert heat.max() - heat.min() > 0.1, "the heatmap is flat"
