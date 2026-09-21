"""Diabetic retinopathy arm.

Split the same way as the chest arm's tests: the scoring maths is pure numpy and
always runs; anything that loads the backbone is skipped when torch or the
533 MB weights file is absent, so the suite stays green for teammates who never
run `uv sync --extra vision`.
"""

from pathlib import Path

import numpy as np
import pytest

from app import catalogue
from app.arms import ARMS, arm_for_intake, arms_for, dr_fundus
from app.evidence import EvidenceKind
from app.scoring import score

SAMPLES = Path(__file__).resolve().parents[3] / "samples" / "retina"

needs_model = pytest.mark.skipif(
    not (dr_fundus.available() and dr_fundus.BACKBONE_PATH.exists()),
    reason="vision extra or FLAIR weights not present (python scripts/fetch_dr_data.py models)",
)
needs_samples = pytest.mark.skipif(not SAMPLES.exists(), reason="sample photographs not present")

# The first rows of the Kaggle DR 2015 `trainLabels.csv`, ICDR 0-4.
#
# NOT a validation set, and never to be reported as one: FLAIR's pretraining
# included EyePACS with its grades, so the backbone has seen these photographs.
# They are here to prove the arm runs end to end on real camera output, and as
# the fixed point the pixel-counting heuristic this arm replaced failed on —
# it scored 16_left, a proliferative eye, at 17.5, below two healthy ones.
SAMPLE_GRADES = {
    "10_left": 0, "10_right": 0, "13_left": 0, "13_right": 0, "15_left": 1,
    "15_right": 2, "16_left": 4, "16_right": 4, "17_left": 0, "17_right": 1,
}  # fmt: skip


# ── the model file ───────────────────────────────────────────────────────────


def test_model_file_is_present_and_sane():
    spec = dr_fundus._SPEC

    assert len(spec["classes"]) == 5
    assert spec["classes"][0] == "No DR"
    assert spec["classes"][4] == "Proliferative DR"
    assert spec["trained_on"] == "ddr"

    width = len(spec["referable"]["coef"])
    assert width == 2048, "one weight per FLAIR feature"
    assert len(spec["grading"]["coef"]) == 5, "one row of weights per ICDR grade"
    assert all(len(row) == width for row in spec["grading"]["coef"])
    assert len(spec["grading"]["intercept"]) == 5


def test_the_validation_claim_is_about_data_the_backbone_never_saw():
    """The arm this replaced claimed 0.942 AUC on APTOS and had never been run
    on APTOS. The claim shown beside every score has to be one the metrics in
    the same file support, and only from sets FLAIR was not pretrained on."""
    spec = dr_fundus._SPEC

    assert "NOT clinically validated" in spec["validation"]
    assert "never saw" in spec["validation"]

    assert spec["validated_on"], "the claim quotes no result at all"
    # DDR, APTOS and the whole of IDRiD were in FLAIR's pretraining with their
    # grades. A number from any of them is not evidence, so none may be quoted.
    assert not {"ddr_test", "aptos", "idrid"} & set(spec["validated_on"])

    for name in spec["validated_on"]:
        metrics = spec["metrics"][name]
        assert metrics["clean"] is True, f"{name} is quoted but the backbone has seen it"
        assert f"{metrics['auc_referable']:.3f}" in spec["validation"], name
        low, high = metrics["auc_ci95"]
        assert low <= metrics["auc_referable"] <= high


# ── scoring — pure maths, no torch needed ────────────────────────────────────


def test_predict_returns_a_probability_and_a_grade_distribution():
    referable, grades = dr_fundus.predict(np.zeros(2048))

    assert 0.0 <= referable <= 1.0
    assert len(grades) == 5
    assert sum(grades) == pytest.approx(1.0)
    assert all(0.0 <= p <= 1.0 for p in grades)


def test_predict_moves_with_the_features_the_head_weights():
    """Pushing the features along the referable weights must raise the referable
    probability. If this fails, the folded scaler or a sign is wrong."""
    direction = np.array(dr_fundus._SPEC["referable"]["coef"])

    toward, _ = dr_fundus.predict(direction)
    away, _ = dr_fundus.predict(-direction)

    assert toward > away


def test_extreme_features_do_not_overflow():
    referable, grades = dr_fundus.predict(np.full(2048, 1e4))

    assert np.isfinite(referable)
    assert all(np.isfinite(grades))


# ── registry ─────────────────────────────────────────────────────────────────


def test_arm_is_registered_and_reads_only_fundus_photographs():
    arm = ARMS["dr_fundus"]

    assert arm.arm_type == "vision"
    assert arm.accepts == frozenset({EvidenceKind.FUNDUS})
    assert [a.name for a in arms_for(EvidenceKind.FUNDUS)] == ["dr_fundus"]
    # A chest X-ray must never reach it: see test_pipeline's routing tests.
    assert "dr_fundus" not in [a.name for a in arms_for(EvidenceKind.CHEST_XRAY)]


def test_the_form_panel_still_resolves():
    """The intake panel keeps the id `eyepacs`, which past applications store."""
    arm = arm_for_intake("eyepacs")

    assert arm is not None
    assert arm.name == dr_fundus.NAME


def test_the_weight_hash_names_both_halves():
    """A score has to say which backbone file and which head produced it."""
    assert dr_fundus.BACKBONE_SHA256[:16] in dr_fundus.WEIGHT_HASH
    assert "logreg:sha256:" in dr_fundus.WEIGHT_HASH
    assert len(ARMS["dr_fundus"].preprocessing_version) <= 50, "model_arms column width"
    assert len(ARMS["dr_fundus"].version) <= 50


def test_the_catalogue_carries_the_caveat():
    entry = next(e for e in catalogue.as_dicts() if e["id"] == "eyepacs")

    assert entry["available"] is True
    assert entry["arm_name"] == "dr_fundus"
    assert "NOT clinically validated" in entry["validation"]


# ── failure paths — guarded before anything heavy is imported ────────────────


def test_empty_input_returns_an_error_not_an_exception():
    result = dr_fundus.run(b"")

    assert result.score is None
    assert result.error


def test_garbage_input_returns_an_error_not_an_exception():
    result = dr_fundus.run(b"definitely not an image")

    assert result.score is None
    assert result.error
    assert result.usable is False


def test_a_chest_xray_is_declined_not_scored():
    """The backstop behind triage and `Arm.accepts`. The heuristic this replaced
    returned 98.8 on a lung, with no error, and won every application."""
    from io import BytesIO

    from PIL import Image

    if not dr_fundus.available():
        pytest.skip("vision extra not installed")

    grey = Image.new("L", (512, 512))
    grey.putdata([(x * 7 + y * 3) % 256 for y in range(512) for x in range(512)])
    buffer = BytesIO()
    grey.save(buffer, format="PNG")

    result = dr_fundus.run(buffer.getvalue())

    assert result.score is None, "a greyscale radiograph must never be graded"
    assert "not gradable" in result.error


# ── real inference ───────────────────────────────────────────────────────────


@needs_model
@needs_samples
def test_scores_a_real_photograph_with_its_provenance():
    result = dr_fundus.run((SAMPLES / "13_left.jpeg").read_bytes())

    assert result.error is None
    assert 0.0 <= result.score <= 100.0
    assert result.raw_score == pytest.approx(result.score / 100.0, abs=1e-3)

    details = result.details
    assert details["backbone"] == dr_fundus.BACKBONE
    assert "logistic_regression" in details["scorer"]
    assert "NOT clinically validated" in details["validation"]
    assert details["grade_name"] in dr_fundus.ICDR_CLASSES
    assert sum(details["class_probabilities"].values()) == pytest.approx(1.0, abs=1e-3)


@needs_model
@needs_samples
def test_the_review_screen_gets_findings_it_can_draw():
    """`get_application` builds its "what moved the score" panel from `findings`
    and `contributions`. The heuristic supplied neither, so a retina application
    opened onto an empty panel."""
    details = dr_fundus.run((SAMPLES / "16_left.jpeg").read_bytes()).details

    assert set(details["findings"]) == set(dr_fundus.ICDR_CLASSES)
    assert set(details["contributions"]) == set(dr_fundus.ICDR_CLASSES)
    # Grades below moderate argue against a referable call, the rest for it.
    assert details["contributions"]["No DR"] <= 0
    assert details["contributions"]["Proliferative DR"] >= 0


@needs_model
@needs_samples
def test_proliferative_eyes_outscore_healthy_ones():
    """The check the heuristic failed. Not validation — see SAMPLE_GRADES."""
    scores = {
        name: dr_fundus.run((SAMPLES / f"{name}.jpeg").read_bytes()).score
        for name in ("13_left", "13_right", "16_left", "16_right")
    }

    assert min(scores["16_left"], scores["16_right"]) > 65, "proliferative eyes must be elevated"
    assert max(scores["13_left"], scores["13_right"]) < 30, "healthy eyes must be low"


@needs_model
@needs_samples
def test_score_is_deterministic():
    raw = (SAMPLES / "15_right.jpeg").read_bytes()
    assert dr_fundus.run(raw).score == dr_fundus.run(raw).score


# ── the heatmap ──────────────────────────────────────────────────────────────


@needs_model
@needs_samples
def test_the_heatmap_is_the_score_taken_apart_by_location():
    """It is drawn from weights . activations per grid cell, and claims to be
    exact rather than estimated. That is checkable: averaged over the grid and
    added to the intercept, those cells must reproduce the logit."""
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO((SAMPLES / "16_right.jpeg").read_bytes())) as image:
        framed = dr_fundus.frame(image, dr_fundus.INPUT_SIZE)
    found, activations = dr_fundus._forward(
        dr_fundus._get_model(), dr_fundus.to_tensor(framed.image)
    )

    binary = dr_fundus._SPEC["referable"]
    coef = np.array(binary["coef"])
    from_features = found @ coef + binary["intercept"]
    from_map = np.tensordot(coef, activations, axes=1).mean() + binary["intercept"]

    assert from_map == pytest.approx(from_features, abs=1e-3)


@needs_model
@needs_samples
def test_the_heatmap_stays_on_the_retina():
    """The first version lit up the black corner of the frame. Outside the disc
    there is nothing to be evidence of, so the overlay must leave it black."""
    from io import BytesIO

    from PIL import Image

    result = dr_fundus.run((SAMPLES / "16_right.jpeg").read_bytes())

    assert list(result.artifacts) == ["gradcam"], "the enum knows no other image overlay"
    overlay = np.asarray(Image.open(BytesIO(result.artifacts["gradcam"])), dtype=np.float32)
    assert overlay.shape == (dr_fundus.INPUT_SIZE, dr_fundus.INPUT_SIZE, 3)

    # 16_right's disc is clipped top and bottom, so the padded bands are black.
    assert overlay[:20].max() < 40, "the overlay painted the black padding"
    assert overlay[-20:].max() < 40, "the overlay painted the black padding"
    # And it does highlight something: cyan lifts green and blue over red.
    assert (overlay[..., 2] - overlay[..., 0]).max() > 60


# ── underwriting rules that read the retina panel ────────────────────────────


def test_diabetes_history_adjusts_a_retina_score():
    base = 25.0
    assert score(base, declared_history={}).tier == "low"

    adjusted = score(
        base, declared_history={"diabetes_duration": "Over 10 years", "hypertension": True}
    )

    assert adjusted.crs == 50.0  # +15 for the duration, +10 for the hypertension
    assert adjusted.tier == "moderate"
    assert {a.key for a in adjusted.adjustments} >= {
        "diabetes_duration_over_10_years",
        "diabetes_with_hypertension",
    }
