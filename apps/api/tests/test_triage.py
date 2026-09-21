"""Working out what an uploaded document is.

The property that matters is not accuracy, it is what happens when triage is
unsure. A wrong guess sends a file to a model that cannot decline it: the retina
arm returns 98.8 out of 100 on a chest X-ray, with no error. So these tests care
far more about abstaining than about getting every file right.
"""

from io import BytesIO

import pytest
from PIL import Image

from app.evidence import EvidenceKind
from app.triage import classify


def grey(size=(256, 256), value=140) -> bytes:
    """A greyscale image filling the frame, like a radiograph."""
    image = Image.new("L", size)
    image.putdata([(value + (x * 7 + y * 3) % 40) for y in range(size[1]) for x in range(size[0])])
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def fundus(size=(256, 256)) -> bytes:
    """A red-orange circle on black, like a retinal photograph."""
    image = Image.new("RGB", size, (0, 0, 0))
    from PIL import ImageDraw

    pad = size[0] // 10
    ImageDraw.Draw(image).ellipse(
        [pad, pad, size[0] - pad, size[1] - pad], fill=(180, 70, 25)
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ── the cases it should get right ────────────────────────────────────────────


def test_a_greyscale_scan_filling_the_frame_is_a_chest_film():
    verdict = classify(grey(), "scan.png")
    assert verdict.kind is EvidenceKind.CHEST_XRAY
    assert verdict.certain


def test_a_red_circle_on_black_is_a_retinal_photo():
    verdict = classify(fundus(), "IMG_2291.jpg")
    assert verdict.kind is EvidenceKind.FUNDUS


@pytest.mark.parametrize("name", ["bloods.pdf", "notes.txt", "summary.docx", "results.csv"])
def test_documents_are_recognised_by_extension(name):
    """A PDF is a document whatever its bytes contain, and never reaches a
    model that expects pixels."""
    verdict = classify(b"%PDF-1.4 whatever", name)
    assert verdict.kind is EvidenceKind.DOCUMENT


# ── abstaining, which is the point ───────────────────────────────────────────


def test_an_unreadable_file_abstains_rather_than_raising():
    verdict = classify(b"not an image at all", "mystery.png")
    assert verdict.kind is EvidenceKind.UNKNOWN
    assert not verdict.certain
    assert verdict.reason


def test_a_colour_image_of_something_else_abstains():
    """A photo of a passport or a form is neither a scan nor a document by
    extension. Guessing would send it to a model."""
    image = Image.new("RGB", (256, 256), (40, 120, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    verdict = classify(buffer.getvalue(), "photo.png")
    assert verdict.kind is EvidenceKind.UNKNOWN


def test_a_greyscale_image_that_is_not_frame_filling_abstains():
    """Greyscale alone does not make something a chest film."""
    image = Image.new("L", (256, 256), 0)
    from PIL import ImageDraw

    ImageDraw.Draw(image).ellipse([90, 90, 166, 166], fill=200)
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    verdict = classify(buffer.getvalue(), "small.png")
    assert verdict.kind is EvidenceKind.UNKNOWN


def test_every_verdict_explains_itself():
    """The reason is shown on the review screen. A classification nobody can
    question is one nobody can correct, and the corrections are what will train
    a real classifier later."""
    for raw, name in ((grey(), "a.png"), (fundus(), "b.png"), (b"x", "c.pdf"), (b"x", "d.png")):
        assert classify(raw, name).reason.strip()


# ── DICOM headers win, because the scanner said so ───────────────────────────


def test_dicom_modality_and_body_part_are_authoritative():
    verdict = classify(fundus(), "scan.dcm", {"Modality": "DX", "BodyPartExamined": "CHEST"})
    assert verdict.kind is EvidenceKind.CHEST_XRAY
    assert "DICOM" in verdict.reason


def test_an_xray_of_something_we_do_not_screen_abstains():
    """A knee X-ray is a perfectly good radiograph that no model here reads."""
    verdict = classify(grey(), "knee.dcm", {"Modality": "DX", "BodyPartExamined": "KNEE"})
    assert verdict.kind is EvidenceKind.UNKNOWN
    assert "Knee" in verdict.reason


def test_a_brain_mri_is_told_apart_from_other_mri():
    brain = classify(grey(), "s.dcm", {"Modality": "MR", "BodyPartExamined": "BRAIN"})
    assert brain.kind is EvidenceKind.BRAIN_MRI

    spine = classify(grey(), "s.dcm", {"Modality": "MR", "BodyPartExamined": "LSPINE"})
    assert spine.kind is EvidenceKind.UNKNOWN


# ── against the real samples ─────────────────────────────────────────────────


def test_never_confidently_wrong_on_the_demo_set():
    """The measurable guarantee: triage may abstain on a hard file, but it must
    not confidently route one to the wrong model."""
    import glob
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    groups = [
        (EvidenceKind.CHEST_XRAY, glob.glob(str(root / "data" / "demo" / "*" / "*.png"))),
        (EvidenceKind.FUNDUS, glob.glob(str(root / "samples" / "retina" / "*.jpeg"))),
    ]

    checked = wrong = 0
    for expected, paths in groups:
        for path in paths[:10]:
            verdict = classify(Path(path).read_bytes(), Path(path).name)
            checked += 1
            if verdict.kind not in (expected, EvidenceKind.UNKNOWN):
                wrong += 1

    if not checked:
        pytest.skip("no sample images present")
    assert wrong == 0, f"{wrong} of {checked} files were confidently misclassified"
