"""End-to-end pipeline: raw uploaded bytes in, score and tier out.

No database, no HTTP — the pipeline is deliberately independent of both.
"""

import contextlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.arms import tb_xray
from app.evidence import EvidenceKind
from app.intake import process_upload
from app.pipeline import STATUS_INSUFFICIENT, STATUS_SCORED
from app.pipeline import evaluate as _evaluate
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


def evaluate(files, *args, kinds=None, **kwargs):
    """`pipeline.evaluate` with every file declared a chest X-ray.

    The real pipeline will not score evidence whose kind is unknown, because an
    unclassified file handed to an arbitrary model is how a retina model comes
    to report 98.8 on a lung. These tests are about the pipeline's plumbing
    rather than about routing, so they declare the kind up front; the routing
    itself is covered by its own tests.

    Files that fail intake never reach an arm, so they are simply absent from
    the map, which is what the pipeline expects.
    """
    if kinds is None:
        kinds = {}
        for raw, name in files:
            # A file that fails intake never reaches an arm, so leaving it out
            # of the map is exactly right.
            with contextlib.suppress(Exception):
                kinds[process_upload(raw, name).content_hash] = EvidenceKind.CHEST_XRAY
    return _evaluate(files, *args, kinds=kinds, **kwargs)


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


# ── evidence only reaches the models that can read it ────────────────────────


@needs_vision
def test_an_arm_never_sees_evidence_it_cannot_read():
    """The bug this prevents, stated plainly.

    Every arm used to run over every file. The retina model handed a chest
    X-ray returns 98.8 out of 100 with no error, because it has never seen a
    lung and has no way to say so. Since the highest score governs, that
    fabricated number won on every application containing a chest film: a
    healthy chest correctly scored 1.23 by the chest model was reported as 81.
    """
    from app.arms import ARMS

    if "eyepacs_dr" not in ARMS:
        pytest.skip("the retina arm is not registered")

    image = png()
    result = evaluate([(image, "chest.png")], history())

    assert result.status == STATUS_SCORED
    ran = {r.arm_name for r in result.runs}
    assert ran == {"tb_xray"}, f"only the chest model should have run, got {ran}"


def test_unclassified_evidence_is_stored_but_not_scored():
    """A file whose kind was never established must not be handed to whichever
    model happens to be registered. Storing it unread is the honest outcome."""
    result = evaluate([(png(), "mystery.png")], history(), kinds={})

    assert result.status == STATUS_INSUFFICIENT
    assert result.runs == []
    # The processed file still exists, so nothing the client handed over is lost.
    assert len(result.processed_files) == 1
    assert any("not classified" in e for e in result.errors)


def test_evidence_no_model_reads_is_reported_not_dropped():
    """Lab reports and notes have no arm yet. The underwriter is told they
    exist and were not read, rather than the platform pretending otherwise."""
    image = png()
    processed = process_upload(image, "bloods.png")
    result = evaluate(
        [(image, "bloods.png")],
        history(),
        kinds={processed.content_hash: EvidenceKind.DOCUMENT},
    )

    assert result.runs == []
    assert any("no model reads this" in e for e in result.errors)
