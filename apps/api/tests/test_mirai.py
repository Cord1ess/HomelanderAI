"""The Mirai arm: four de-identified mammogram views to a remote model.

The model is not here, so what is pinned is everything around it: a mammogram
DICOM is stored as a DICOM with the patient stripped and the view tags kept,
the four views are checked before anything is sent, the pipeline runs the arm
once over all of them, and the server's five numbers land on the arm scale
where the design says they should.
"""

import io

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


def test_the_server_answer_becomes_a_reading(monkeypatch):
    monkeypatch.setattr(
        mirai,
        "call",
        lambda views: {
            "prediction": [0.001, 0.0028, 0.0052, 0.0084, 0.0115],
            "model_name": "2D_Mammo_Cancer_Mirai",
            "onconet_version": "0.2.0",
            "oncoserve_version": "0.2.0",
            "msg": "OK",
        },
    )
    result = mirai.run_set(FOUR)
    assert result.error is None
    assert result.score == mirai.score_from(0.0115) == 15.95
    assert result.details["five_year_risk"] == 0.0115
    assert len(result.details["views"]) == 4
    assert result.details["server"]["model_name"] == "2D_Mammo_Cancer_Mirai"


def test_a_server_error_is_a_reason_not_a_score(monkeypatch):
    monkeypatch.setattr(mirai, "call", lambda views: {"prediction": None, "msg": "Error. x"})
    result = mirai.run_set(FOUR)
    assert result.score is None and "without a prediction" in result.error


# ── through the pipeline ─────────────────────────────────────────────────────


def test_the_pipeline_runs_mirai_once_over_all_four_views(monkeypatch):
    calls: list[int] = []

    def fake_call(views):
        calls.append(len(views))
        return {"prediction": [0.01, 0.02, 0.03, 0.04, 0.06], "model_name": "m"}

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
