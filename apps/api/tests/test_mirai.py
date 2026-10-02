"""The Mirai arm: four de-identified mammogram views to the local Mirai service.

Two kinds of test. Most pin everything around the model — a mammogram is
stored as a de-identified DICOM, the four views are checked before anything is
sent, the server's answer and its refusals land where the design says, and the
pipeline runs the arm once over all four views. Those replace `mirai.call`, so
they run anywhere.

The last section runs the **real model** in its container and checks it gives
the risks the authors publish for their own demo exam. Those skip, saying why,
when the container is not running (`docker compose up -d mirai`).
"""

import io
import json
import urllib.request
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app import intake, pipeline, triage
from app.arms import ARMS, mirai
from app.evidence import EvidenceKind


def film(laterality: str | None = "R", view: str | None = "MLO", seed: int = 0) -> bytes:
    """A tiny synthetic mammogram DICOM with a patient name on it."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.DigitalMammographyXRayImageStorageForPresentation
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientName = "Rahima^Begum"
    ds.PatientID = "P_00038"
    ds.PatientBirthDate = "19700101"
    ds.InstitutionName = "Somewhere Hospital"
    ds.Modality = "MG"
    ds.Manufacturer = "MathWorks"
    if laterality:
        ds.ImageLaterality = laterality
    if view:
        ds.ViewPosition = view
    ds.Rows, ds.Columns = 32, 24
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
    rng = np.random.default_rng(seed)
    ds.PixelData = rng.integers(0, 4000, (32, 24), dtype=np.uint16).tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


FOUR = [film("R", "MLO", 1), film("L", "MLO", 2), film("L", "CC", 3), film("R", "CC", 4)]


# ── intake ───────────────────────────────────────────────────────────────────


def test_a_mammogram_is_stored_as_a_dicom_without_the_patient():
    processed = intake.process_upload(film(), "RIGHT_MLO.dcm")
    assert processed.source_format == "mammogram"
    assert processed.mime_type == "application/dicom"
    assert processed.deidentified is True
    ds = pydicom.dcmread(io.BytesIO(processed.data))
    # The server wants a patient to exist, so it gets an anonymous one.
    assert str(ds.PatientName) == "ANONYMOUS" and ds.PatientID != "P_00038"
    assert "PatientBirthDate" not in ds and "InstitutionName" not in ds
    assert ds.ImageLaterality == "R" and ds.ViewPosition == "MLO" and ds.Modality == "MG"
    assert ds.PatientIdentityRemoved == "YES"
    assert b"Rahima" not in processed.data
    assert processed.clinical_tags["ViewPosition"] == "MLO"


def test_a_stored_mammogram_passes_through_intake_unchanged():
    stored = intake.process_upload(film(), "x.dcm").data
    assert intake.process_upload(stored, "x.dcm").data == stored


def test_an_unlabelled_film_is_stored_with_a_warning():
    processed = intake.process_upload(film(None, None), "scan.dcm")
    assert any("which breast or view" in w for w in processed.warnings)


def test_other_dicom_still_becomes_a_png():
    raw = film()
    ds = pydicom.dcmread(io.BytesIO(raw))
    ds.Modality = "DX"
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    assert intake.process_upload(buffer.getvalue(), "chest.dcm").source_format == "dicom"


def test_triage_calls_it_a_mammogram_from_its_tags():
    processed = intake.process_upload(film(), "x.dcm")
    verdict = triage.classify(processed.data, "x.dcm", processed.clinical_tags)
    assert verdict.kind is EvidenceKind.MAMMOGRAM


def test_the_stored_dicom_can_be_drawn():
    stored = intake.process_upload(film(), "x.dcm").data
    assert intake.dicom_to_png(stored)[:8] == b"\x89PNG\r\n\x1a\n"


# ── the four views ───────────────────────────────────────────────────────────


def test_the_four_views_are_arranged_by_their_tags():
    views = mirai.arrange(FOUR)
    assert set(views) == set(mirai.VIEWS)


@pytest.mark.parametrize(
    ("files", "reason"),
    [
        (FOUR[:3], r"missing view\(s\): right CC"),
        (FOUR + [film("R", "CC", 9)], "two files are labelled right CC"),
        (FOUR[:3] + [film(None, None)], "carry no laterality/view tags"),
    ],
)
def test_anything_but_four_distinct_views_is_refused(files, reason):
    with pytest.raises(ValueError, match=reason):
        mirai.arrange(files)


def test_run_set_refuses_before_calling_the_server(monkeypatch):
    monkeypatch.setattr(mirai, "call", lambda views: pytest.fail("must not be called"))
    result = mirai.run_set(FOUR[:2])
    assert result.score is None and "four-view mammogram" in result.error


# ── the score ────────────────────────────────────────────────────────────────


def test_the_anchors_hold():
    assert mirai.score_from(0.017) == 30.0
    assert mirai.score_from(0.045) == 65.0
    assert mirai.score_from(0.0) == 0.0
    assert mirai.score_from(0.5) == 100.0
    assert mirai.score_from(0.01) < 30.0 < mirai.score_from(0.02)


# ── the server's answer ──────────────────────────────────────────────────────


def answer(*risks: float) -> dict:
    """What the service sends back, exactly as it is shaped."""
    return {
        "data": {"predictions": {f"Year {i + 1}": r for i, r in enumerate(risks)}},
        "message": None,
        "metadata": None,
        "runtime": "43.10s",
        "statusCode": 200,
    }


def test_the_server_answer_becomes_a_reading(monkeypatch):
    monkeypatch.setattr(mirai, "call", lambda views: answer(0.001, 0.0028, 0.0052, 0.0084, 0.0115))
    result = mirai.run_set(FOUR)
    assert result.error is None
    assert result.score == mirai.score_from(0.0115) == 15.95
    assert result.details["risk_by_year"] == [0.001, 0.0028, 0.0052, 0.0084, 0.0115]
    assert result.details["five_year_risk"] == 0.0115
    assert len(result.details["views"]) == 4
    assert result.details["runtime"] == "43.10s"
    assert "simulated" not in result.details


def test_a_refusal_carries_the_servers_reason(monkeypatch):
    """The service refuses with HTTP 400 and a message. The message is what the
    operator needs, so it reaches the screen rather than a bare status."""
    monkeypatch.setattr(
        mirai,
        "call",
        lambda views: {
            "data": None,
            "message": "ValueError: Require exactly 4 images, instead we got 3",
            "statusCode": 400,
        },
    )
    result = mirai.run_set(FOUR)
    assert result.score is None
    assert "Require exactly 4 images" in result.error


def test_an_answer_missing_a_year_is_not_a_reading(monkeypatch):
    partial = answer(0.01, 0.02, 0.03, 0.04, 0.05)
    del partial["data"]["predictions"]["Year 3"]
    monkeypatch.setattr(mirai, "call", lambda views: partial)
    assert mirai.run_set(FOUR).score is None


def test_a_stopped_service_says_how_to_start_it(monkeypatch):
    """Nothing listening is the likeliest failure on a demo laptop: the
    operator is told what to run, not shown a socket error."""
    from app.config import settings

    monkeypatch.setattr(settings, "mirai_url", "http://127.0.0.1:9")  # nothing listens on 9
    result = mirai.run_set(FOUR)
    assert result.score is None
    assert "docker compose up -d mirai" in result.error


def test_the_request_carries_four_views_and_the_data_field(monkeypatch):
    """The service requires the `data` field and rejects the request without it,
    and reads every file under `dicom`."""
    sent: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(answer(0.01, 0.02, 0.03, 0.04, 0.05)).encode()

    def capture(request, timeout):
        sent["url"] = request.full_url
        sent["body"] = request.data
        sent["timeout"] = timeout
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", capture)
    assert mirai.run_set(FOUR).score is not None
    assert sent["url"].endswith("/dicom/files")
    assert sent["body"].count(b'name="dicom"') == 4
    assert sent["body"].count(b'name="data"') == 1


def test_the_arm_never_sends_risk_factors():
    """The served model ignores them (reginabarzilaygroup/Mirai#14), so sending
    them would only imply they count. The `data` field goes empty."""
    body, _ = mirai._multipart(mirai.arrange(FOUR))
    assert b'name="data"\r\n\r\n{}\r\n' in body


# ── through the pipeline ─────────────────────────────────────────────────────


def test_the_pipeline_runs_mirai_once_over_all_four_views(monkeypatch):
    calls: list[int] = []

    def fake_call(views):
        calls.append(len(views))
        return answer(0.01, 0.02, 0.03, 0.04, 0.06)

    monkeypatch.setattr(mirai, "call", fake_call)
    processed = [intake.process_upload(f, f"{i}.dcm") for i, f in enumerate(FOUR)]
    kinds = {p.content_hash: EvidenceKind.MAMMOGRAM for p in processed}
    result = pipeline.evaluate(
        [(p.data, f"{i}.dcm") for i, p in enumerate(processed)],
        {},
        age=52,
        kinds=kinds,
        sex="female",
        models_requested=["mirai"],
    )
    assert calls == [4], "one call with all four views, not four calls"
    assert [r.arm_name for r in result.runs] == ["mirai"]
    assert result.status == pipeline.STATUS_SCORED
    assert result.runs[0].result.score == mirai.score_from(0.06)


def test_the_arm_is_registered_for_mammograms():
    arm = ARMS["mirai"]
    assert arm.accepts == frozenset({EvidenceKind.MAMMOGRAM})
    assert arm.run_set is not None and arm.run is None
    assert "NOT validated in South Asia" in arm.validation


def test_nothing_can_produce_a_simulated_reading():
    """The stand-in that covered for the dead remote server is gone. No setting,
    no function, no path through the arm can return a number the model did not
    compute."""
    from app.config import settings

    assert not hasattr(settings, "mirai_simulate")
    assert not hasattr(mirai, "simulate")
    assert not hasattr(mirai, "seed_simulation")


# ── the real model ───────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[3]
# The authors' own demo exam (reginabarzilaygroup/Mirai, release v0.14.1,
# `mirai_demo_data.zip`), and the risks their documentation publishes for it.
OFFICIAL_DEMO = ROOT / "data" / "mirai" / "demo"
PUBLISHED = [0.0298, 0.0483, 0.0684, 0.09, 0.1016]


def _service_up() -> bool:
    from app.config import settings

    try:
        with urllib.request.urlopen(f"{settings.mirai_url}/info", timeout=5) as response:
            return json.loads(response.read())["data"]["modelName"] == "mirai"
    except Exception:
        return False


needs_service = pytest.mark.skipif(
    not _service_up(), reason="Mirai is not running — `docker compose up -d mirai`"
)


@needs_service
def test_the_service_is_the_pinned_model():
    from app.config import settings

    with urllib.request.urlopen(f"{settings.mirai_url}/info", timeout=10) as response:
        info = json.loads(response.read())["data"]
    assert info == {"apiVersion": "0.8.0", "modelName": "mirai", "modelVersion": "0.14.1"}


@needs_service
@pytest.mark.skipif(
    len(list(OFFICIAL_DEMO.glob("*.dcm"))) != 4,
    reason="the authors' demo exam is not in data/mirai/demo — scripts/fetch_mirai_demo.py",
)
def test_the_real_model_reproduces_the_published_risks():
    """The strongest check available: the authors publish what Mirai returns for
    their demo exam, and this runs it through the same path an application
    takes — de-identified by intake, then sent by the arm."""
    views = sorted(OFFICIAL_DEMO.glob("*.dcm"))
    files = [intake.process_upload(f.read_bytes(), f.name).data for f in views]
    result = mirai.run_set(files)
    assert result.error is None, result.error
    assert result.details["risk_by_year"] == PUBLISHED


@needs_service
def test_the_real_model_reads_our_demo_films():
    """Our demo mammograms are CBIS-DDSM (digitised film, not the Hologic
    screening exams Mirai was trained on). The model accepts them; this pins
    what it says, so a change in either the films or the image shows up."""
    folder = ROOT / "demo" / "test" / "test-02-fatema"
    films = sorted(folder.glob("mammogram-*.dcm"))
    if len(films) != 4:
        pytest.skip("demo films not present")
    result = mirai.run_set([intake.process_upload(f.read_bytes(), f.name).data for f in films])
    assert result.error is None, result.error
    assert result.details["risk_by_year"] == [0.001, 0.0028, 0.0052, 0.0084, 0.0115]
    assert result.score == 15.95
