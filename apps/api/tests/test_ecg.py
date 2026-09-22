"""The ECG arm: reading an export, storing it, and scoring it.

The reading side is pinned without the networks: a machine's CSV must come
out as twelve leads in the right order at 400 Hz, whatever the device called
the leads, whatever rate it sampled at, and in millivolts whether it wrote
millivolts or microvolts. Anything short of that is refused with a reason,
because a wrong sampling rate or a missing lead gives a confident wrong
answer downstream. The scoring rule is pinned on hand-made probabilities. The
networks themselves run only when their converted weights are present.
"""

import io

import numpy as np
import pytest
from PIL import Image

from app import ecg, intake, triage
from app.arms import ecg_12lead
from app.evidence import EvidenceKind
from tests.conftest import needs_database

needs_weights = pytest.mark.skipif(
    not (ecg_12lead.available() and ecg_12lead.weights_present()),
    reason="run scripts/fetch_ecg_models.py",
)


def synthetic(
    rate: float = 500.0,
    seconds: float = 10.0,
    header: tuple[str, ...] = ecg.LEADS,
    scale: float = 1.0,
    time_column: str | None = "time",
    comment: str | None = None,
    delimiter: str = ",",
) -> bytes:
    """A plausible tracing: a 1 mV spike every 0.8 s on a little noise."""
    n = int(rate * seconds)
    t = np.arange(n) / rate
    rng = np.random.default_rng(0)
    beat = ((t % 0.8) < 0.04).astype(np.float32)
    rows = []
    columns = ([time_column] if time_column else []) + list(header)
    lines = ([comment] if comment else []) + [delimiter.join(columns)]
    for i in range(n):
        values = [
            f"{(beat[i] + rng.normal(0, 0.02)) * (1 + 0.05 * k) * scale:.4f}" for k in range(12)
        ]
        rows.append(delimiter.join(([f"{t[i]:.4f}"] if time_column else []) + values))
    lines += rows
    return "\n".join(lines).encode()


# ── reading an export ────────────────────────────────────────────────────────


def test_a_plain_export_is_read_in_lead_order_at_its_own_rate():
    signal = ecg.parse_csv(synthetic(rate=500.0))
    assert signal.leads.shape == (12, 5000)
    assert signal.sample_rate == pytest.approx(500.0)
    assert signal.seconds == pytest.approx(10.0)
    assert signal.notes == []


def test_lead_names_are_matched_however_the_device_spells_them():
    shuffled = ("V6", "V5", "V4", "V3", "V2", "V1", "aVF", "aVL", "aVR", "DIII", "DII", "DI")
    raw = synthetic(header=shuffled)
    signal = ecg.parse_csv(raw)
    # Column k of the file was labelled shuffled[k]; it must come back as that lead.
    table = np.array(
        [[float(v) for v in line.split(",")] for line in raw.decode().splitlines()[1:]]
    )
    for k, name in enumerate(shuffled):
        lead = ecg.LEADS.index({"DI": "I", "DII": "II", "DIII": "III"}.get(name, name))
        np.testing.assert_allclose(signal.leads[lead], table[:, k + 1], atol=1e-6)


def test_the_rate_can_come_from_a_comment_line_instead_of_a_time_column():
    signal = ecg.parse_csv(synthetic(time_column=None, comment="# fs=250 Hz, mV"))
    assert signal.sample_rate == 250.0


def test_a_tab_separated_export_reads_the_same():
    signal = ecg.parse_csv(synthetic(delimiter="\t"))
    assert signal.leads.shape == (12, 5000)


def test_microvolts_are_recognised_and_converted():
    signal = ecg.parse_csv(synthetic(scale=1000.0))
    assert float(np.percentile(np.abs(signal.leads), 99.9)) < 5
    assert any("microvolts" in note for note in signal.notes)


@pytest.mark.parametrize(
    ("make", "reason"),
    [
        pytest.param(lambda: synthetic(header=ecg.LEADS[:11]), "11 of 12 leads", id="lead"),
        pytest.param(lambda: synthetic(time_column=None), "sampling rate unknown", id="rate"),
        pytest.param(lambda: synthetic(seconds=3.0), "at least 5 s", id="short"),
        pytest.param(lambda: b"name,age\nx,1\ny,2\n", "no lead columns", id="table"),
        pytest.param(lambda: b"\x89PNG\r\n\x1a\n" + bytes(64), "not a text file", id="png"),
        pytest.param(lambda: synthetic(scale=1e-4), "not an ECG in millivolts", id="flat"),
    ],
)
def test_what_cannot_be_read_is_refused_with_the_reason(make, reason):
    with pytest.raises(ecg.NotAnEcg, match=reason):
        ecg.parse_csv(make())


# ── the stored form ──────────────────────────────────────────────────────────


def test_canonical_is_twelve_by_4096_at_400_hz_in_millivolts():
    signal = ecg.parse_csv(synthetic(rate=500.0, seconds=10.0))
    array = ecg.canonical(signal)
    assert array.shape == (12, ecg.LENGTH) and array.dtype == np.float32
    # Ten seconds at 400 Hz is 4000 samples; the last 96 are the zero padding.
    assert np.all(array[:, 4000:] == 0)
    assert np.any(array[:, :4000] != 0)
    # A beat every 0.8 s survives the resampling: 12 to 13 spikes in ten seconds.
    spikes = np.sum(np.diff((array[0] > 0.5).astype(int)) == 1)
    assert 12 <= spikes <= 13


def test_a_long_tracing_is_cut_and_a_short_one_padded():
    long = ecg.canonical(ecg.parse_csv(synthetic(rate=400.0, seconds=20.0)))
    short = ecg.canonical(ecg.parse_csv(synthetic(rate=400.0, seconds=6.0)))
    assert long.shape == short.shape == (12, ecg.LENGTH)
    assert np.all(short[:, 2400:] == 0)


def test_the_bytes_round_trip_and_hash_the_same():
    array = ecg.canonical(ecg.parse_csv(synthetic()))
    stored = ecg.to_bytes(array)
    assert ecg.is_canonical(stored)
    assert ecg.to_bytes(array) == stored
    np.testing.assert_array_equal(ecg.from_bytes(stored), array)


def test_a_stored_array_of_the_wrong_shape_is_refused():
    buffer = io.BytesIO()
    np.save(buffer, np.zeros((12, 100), dtype=np.float32))
    with pytest.raises(ecg.NotAnEcg, match="expected"):
        ecg.from_bytes(buffer.getvalue())


def test_render_draws_twelve_rows_as_a_png():
    array = ecg.canonical(ecg.parse_csv(synthetic()))
    png = ecg.render(array, saliency=np.linspace(0, 1, ecg.LENGTH), width=800, row_height=40)
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.size == (800, 40 * 12 + 32)


# ── intake and triage ────────────────────────────────────────────────────────


def test_intake_stores_the_signal_not_a_picture_and_keeps_no_header():
    raw = synthetic(comment="# Patient: Rahim Uddin, recorded 2026-03-01, fs=500")
    processed = intake.process_upload(raw, "ecg_export.csv")
    assert processed.source_format == "ecg"
    assert processed.mime_type == "application/x-npy"
    assert processed.deidentified is True
    assert ecg.is_canonical(processed.data)
    assert b"Rahim" not in processed.data
    assert processed.clinical_tags == {"SampleRate": "500", "Seconds": "10.0"}


def test_a_stored_ecg_passes_through_intake_unchanged():
    # The pipeline re-reads evidence from disk under its original filename.
    stored = intake.process_upload(synthetic(), "export.csv").data
    again = intake.process_upload(stored, "export.csv")
    assert again.data == stored and again.source_format == "ecg"


def test_intake_refuses_a_csv_that_is_not_an_ecg_with_the_reason():
    with pytest.raises(intake.IntakeError, match="12-lead ECG export"):
        intake.process_upload(b"test,value\nHbA1c,6.1\n", "labs.csv")


def test_triage_recognises_an_export_and_the_stored_signal():
    raw = synthetic()
    verdict = triage.classify(raw, "export.csv")
    assert verdict.kind is EvidenceKind.ECG
    assert "500 Hz" in verdict.reason
    stored = intake.process_upload(raw, "export.csv").data
    assert triage.classify(stored, "abc.npy").kind is EvidenceKind.ECG


def test_triage_still_calls_an_ordinary_csv_a_document():
    assert triage.classify(b"test,value\nHbA1c,6.1\n", "labs.csv").kind is EvidenceKind.DOCUMENT


# ── the scoring rule ─────────────────────────────────────────────────────────


def quiet(**overrides: float) -> dict[str, float]:
    probabilities = {c: 0.001 for c in ecg_12lead.CLASSES}
    probabilities.update(overrides)
    return probabilities


def test_nothing_reported_stays_in_the_low_tier_and_never_crosses_it():
    score, reported = ecg_12lead.score_from(quiet())
    assert reported == [] and score < 1
    # Just under a threshold: near the top of the low tier, still under it.
    almost = quiet(AF=ecg_12lead.THRESHOLDS["AF"] * 0.99)
    score, reported = ecg_12lead.score_from(almost)
    assert reported == [] and 29 < score < 30


def test_a_reported_abnormality_scores_its_weight():
    score, reported = ecg_12lead.score_from(quiet(ST=0.5))
    assert reported == ["ST"] and score == 35.0
    score, reported = ecg_12lead.score_from(quiet(AF=0.9))
    assert reported == ["AF"] and score == 100.0


def test_the_highest_reported_weight_governs():
    score, reported = ecg_12lead.score_from(quiet(ST=0.5, RBBB=0.2, LBBB=0.1))
    assert set(reported) == {"ST", "RBBB", "LBBB"}
    assert score == 100.0 * ecg_12lead.WEIGHTS["LBBB"]


def test_thresholds_are_the_authors_operating_points_not_a_half():
    # Recovered from the published decisions on CODE-test; 0.5 would miss most
    # blocks, whose probabilities the network keeps low even when it is sure.
    assert ecg_12lead.THRESHOLDS["LBBB"] < 0.1
    assert all(0 < t < 0.5 for t in ecg_12lead.THRESHOLDS.values())


def test_expected_ecg_age_follows_the_fit_on_the_public_test_set():
    # The age model reads young adults older and the old younger; the gap is
    # measured against that, not against the true age.
    assert ecg_12lead.expected_ecg_age(20) > 20
    assert ecg_12lead.expected_ecg_age(90) < 90


def test_the_arm_is_registered_for_ecg_evidence_only():
    from app.arms import ARMS, arm_for_intake, arms_for

    arm = ARMS["ecg_12lead"]
    assert arm.accepts == frozenset({EvidenceKind.ECG})
    assert arms_for(EvidenceKind.ECG) == [arm]
    assert arm_for_intake("ecg") is arm
    assert "NOT validated in South Asia" in arm.validation


def test_run_never_raises_on_bad_bytes():
    result = ecg_12lead.run(b"not a tracing")
    assert result.score is None and result.error


# ── the networks, when their weights are present ─────────────────────────────


@needs_weights
def test_the_networks_score_a_synthetic_tracing_and_draw_it():
    stored = intake.process_upload(synthetic(), "export.csv").data
    result = ecg_12lead.run(stored)
    assert result.error is None
    assert result.score is not None and 0 <= result.score <= 100
    details = result.details
    assert set(details["probabilities"]) == set(ecg_12lead.CLASSES)
    assert all(0 <= p <= 1 for p in details["probabilities"].values())
    assert set(details["findings"]) == set(ecg_12lead.LABELS.values())
    assert 0 < details["ecg_age"] < 150
    assert "gradcam" in result.artifacts
    assert Image.open(io.BytesIO(result.artifacts["gradcam"])).format == "PNG"


@needs_weights
def test_the_converted_weights_match_their_pins():
    spec = ecg_12lead._SPEC["converted_weights"]
    assert spec["dx"]["sha256"] and spec["age"]["sha256"], "run scripts/fetch_ecg_models.py"
    ecg_12lead._verify(ecg_12lead.DX_PATH, spec["dx"]["sha256"])
    ecg_12lead._verify(ecg_12lead.AGE_PATH, spec["age"]["sha256"])


# ── through the API ──────────────────────────────────────────────────────────


@needs_weights
@needs_database
def test_an_ecg_export_is_scored_and_served_as_a_picture(carrier):
    """The whole path: the CSV is stored as the signal (not a PNG, not the
    file), the arm scores it, and the review screen gets a drawing of it."""
    import asyncio
    import json

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_applications import intake_payload, sign_in

    payload = intake_payload(
        modelsRequested=["ecg"],
        declaredHistory={"ecg": {"history": {"palpitations": True}}},
    )
    raw = synthetic(comment="# Patient: Rahim Uddin, fs=500")
    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        response = client.post(
            "/api/applications",
            data={"payload": payload, "file_arms": ["ecg"]},
            files={"files": ("export.csv", raw, "text/csv")},
        )
        assert response.status_code == 201, response.text
        detail = client.get(f"/api/applications/{response.json()['id']}").json()
        assert detail["status"] == "scored", json.dumps(detail, indent=1)

        arms = {a["arm"]: a for a in detail["arms"]}
        assert arms["ecg_12lead"]["error"] is None
        assert set(arms["ecg_12lead"]["details"]["probabilities"]) == set(ecg_12lead.CLASSES)
        assert detail["findings"], "the six abnormalities feed the findings panel"

        kinds = {f["kind"] for f in detail["files"]}
        assert {"evidence", "gradcam"} <= kinds
        for file in detail["files"]:
            served = client.get(f"/api/files/{file['id']}")
            assert served.status_code == 200
            assert served.headers["content-type"].startswith("image/png")
            assert Image.open(io.BytesIO(served.content)).format == "PNG"
