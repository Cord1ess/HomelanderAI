"""End-to-end pipeline: raw uploaded bytes in, score and tier out.

No database, no HTTP — the pipeline is deliberately independent of both.
"""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.arms import tb_xray
from app.pipeline import STATUS_INSUFFICIENT, STATUS_SCORED, evaluate
from app.scoring import INSUFFICIENT, Thresholds

SAMPLES = (
    Path(__file__).resolve().parents[3] / "Reference" / "Nirnoy" / "assets" / "samples"
)

needs_vision = pytest.mark.skipif(
    not tb_xray.available(), reason="vision extra not installed"
)
needs_samples = pytest.mark.skipif(
    not SAMPLES.exists(), reason="reference samples not present"
)


def png(color=128, size=(256, 256)) -> bytes:
    buffer = BytesIO()
    Image.new("L", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def history(**flags) -> dict:
    from tests.test_scoring import history as build

    return build(**flags)


# ── nothing usable ───────────────────────────────────────────────────────────


def test_no_files_is_insufficient():
    result = evaluate([], history())

    assert result.status == STATUS_INSUFFICIENT
    assert result.tier == INSUFFICIENT
    assert result.crs is None
    assert any("No readable evidence" in e for e in result.errors)


def test_unreadable_file_is_insufficient_not_a_crash():
    result = evaluate([(b"not an image", "junk.txt")], history())

    assert result.status == STATUS_INSUFFICIENT
    assert result.crs is None
    assert result.errors


def test_one_bad_file_does_not_sink_a_good_one():
    """A junk upload alongside a valid X-ray must not lose the whole application."""
    if not tb_xray.available():
        pytest.skip("vision extra not installed")

    result = evaluate([(b"junk", "bad.txt"), (png(), "chest.png")], history())

    assert result.status == STATUS_SCORED
    assert result.crs is not None
    assert any("bad.txt" in e for e in result.errors), "the failure should still be recorded"


# ── scoring path ─────────────────────────────────────────────────────────────


@needs_vision
def test_scores_and_deidentifies_in_one_pass():
    result = evaluate([(png(), "chest.png")], history())

    assert result.status == STATUS_SCORED
    assert 0.0 <= result.crs <= 100.0
    assert result.tier in ("low", "moderate", "elevated")

    assert len(result.processed_files) == 1
    assert result.processed_files[0].content_hash
    assert result.processed_files[0].deidentified


@needs_vision
def test_run_records_which_evidence_it_scored():
    """Each run carries the hash of the exact bytes it read — the audit link
    between a score and its input."""
    result = evaluate([(png(), "chest.png")], history())

    run = result.runs[0]
    assert run.arm_name == "tb_xray"
    assert run.arm_version
    assert run.evidence_hash == result.processed_files[0].content_hash


@needs_vision
def test_highest_scoring_film_governs():
    """Two films, the more concerning one sets the score. A clean view must not
    average away an abnormal one."""
    both = evaluate([(png(color=0), "a.png"), (png(color=255), "b.png")], history())
    individual = [
        evaluate([(png(color=0), "a.png")], history()).crs,
        evaluate([(png(color=255), "b.png")], history()).crs,
    ]

    assert both.crs == max(individual)
    assert len(both.runs) == 2


@needs_vision
def test_declared_history_moves_the_score():
    """The pipeline must actually apply the scoring rules, not just the model."""
    image = png()

    plain = evaluate([(image, "chest.png")], history())
    scarring = evaluate(
        [(image, "chest.png")],
        history(prior_tb=True, prior_tb_treatment_completed=True),
    )

    assert scarring.crs < plain.crs
    assert any(a.key == "prior_tb_scarring" for a in scarring.adjustments)
    assert all(a.reason for a in scarring.adjustments), "every adjustment needs a reason"


@needs_vision
def test_thresholds_are_carried_through():
    result = evaluate([(png(), "chest.png")], history(), thresholds=Thresholds(5.0, 10.0))

    assert result.thresholds.as_dict() == {"low_max": 5.0, "moderate_max": 10.0}
    assert result.tier == "elevated"


@needs_vision
def test_artifacts_are_namespaced_by_arm():
    result = evaluate([(png(), "chest.png")], history())

    assert result.artifacts
    for key in result.artifacts:
        assert key.startswith("tb_xray."), "artifacts must be attributable to an arm"


@needs_vision
@needs_samples
def test_real_xray_end_to_end():
    sample = next(iter(sorted((SAMPLES / "TB").glob("*.png"))))

    result = evaluate(
        [(sample.read_bytes(), sample.name)],
        history(cough_over_2_weeks=True, weight_loss=True, diabetes=True),
        age=64,
    )

    assert result.status == STATUS_SCORED
    assert result.crs is not None
    assert {a.key for a in result.adjustments} >= {
        "multiple_symptoms",
        "diabetes",
        "age_over_60",
    }
    assert "tb_xray.gradcam" in result.artifacts


# ── invariant ────────────────────────────────────────────────────────────────


@needs_vision
def test_pipeline_never_denies():
    for flags in (history(), history(hiv=True, haemoptysis=True, diabetes=True)):
        result = evaluate([(png(), "chest.png")], flags, age=80)
        assert result.tier in ("low", "moderate", "elevated", INSUFFICIENT)
