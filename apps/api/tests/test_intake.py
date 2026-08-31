"""Evidence intake and de-identification.

The important test is `test_dicom_identifiers_do_not_survive` — it builds a DICOM
stuffed with identifying data and proves none of it reaches storage.
"""

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.intake import IntakeError, is_dicom, process_upload, sha256

# Real chest X-rays shipped with the reference project. Skipped rather than
# failed if the folder is absent, so the suite still runs on a clean checkout.
SAMPLES = (
    Path(__file__).resolve().parents[3] / "Reference" / "Nirnoy" / "assets" / "samples"
)

IDENTIFIERS = {
    "PatientName": "DOE^JANE",
    "PatientID": "MRN-99887766",
    "InstitutionName": "St Elsewhere Hospital",
    "ReferringPhysicianName": "HOUSE^GREGORY",
}


def make_dicom(
    pixels: np.ndarray | None = None,
    photometric: str = "MONOCHROME2",
    **extra,
) -> bytes:
    """A minimal but valid single-frame DICOM carrying identifying tags."""
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    if pixels is None:
        pixels = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64)

    ds = Dataset()
    ds.PatientName = IDENTIFIERS["PatientName"]
    ds.PatientID = IDENTIFIERS["PatientID"]
    ds.PatientBirthDate = "19800101"
    ds.InstitutionName = IDENTIFIERS["InstitutionName"]
    ds.ReferringPhysicianName = IDENTIFIERS["ReferringPhysicianName"]
    ds.StudyDate = "20240101"

    ds.Modality = "DX"
    ds.BodyPartExamined = "CHEST"
    ds.ViewPosition = "PA"

    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = photometric
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = pixels.astype(np.uint16).tobytes()

    for key, value in extra.items():
        setattr(ds, key, value)

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta

    buffer = BytesIO()
    try:  # pydicom 3
        ds.save_as(buffer, enforce_file_format=True)
    except TypeError:  # pydicom 2
        ds.save_as(buffer, write_like_original=False)
    assert pydicom  # silence the unused-import linter in the 2.x branch
    return buffer.getvalue()


def png_bytes(mode: str = "L", size: tuple[int, int] = (32, 32)) -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color=128).save(buffer, format="PNG")
    return buffer.getvalue()


# ── the point of this module ─────────────────────────────────────────────────


def test_dicom_identifiers_do_not_survive():
    raw = make_dicom()

    # Sanity: the identifiers really are in the input, so a pass means something.
    for value in IDENTIFIERS.values():
        assert value.encode() in raw

    result = process_upload(raw, "scan.dcm")

    for name, value in IDENTIFIERS.items():
        assert value.encode() not in result.data, f"{name} survived into storage"

    assert b"19800101" not in result.data, "date of birth survived into storage"
    assert result.deidentified is True
    assert result.mime_type == "image/png"
    assert result.source_format == "dicom"


def test_clinical_tags_are_kept():
    result = process_upload(make_dicom(), "scan.dcm")

    assert result.clinical_tags["Modality"] == "DX"
    assert result.clinical_tags["BodyPartExamined"] == "CHEST"
    assert result.clinical_tags["ViewPosition"] == "PA"

    # ...and nothing identifying rode along in the tag dict.
    assert not {"PatientName", "PatientID", "StudyDate"} & set(result.clinical_tags)


def test_output_is_a_readable_png():
    result = process_upload(make_dicom(), "scan.dcm")

    image = Image.open(BytesIO(result.data))
    image.load()
    assert image.format == "PNG"
    assert image.size == (64, 64)


# ── DICOM handling details ───────────────────────────────────────────────────


def test_monochrome1_is_inverted():
    """MONOCHROME1 stores tone inverted; without the flip, X-rays render wrong."""
    pixels = np.zeros((16, 16), dtype=np.uint16)
    pixels[0, 0] = 4095  # one bright corner

    normal = Image.open(BytesIO(process_upload(make_dicom(pixels, "MONOCHROME2")).data))
    inverted = Image.open(BytesIO(process_upload(make_dicom(pixels, "MONOCHROME1")).data))

    assert normal.getpixel((0, 0)) == 255
    assert inverted.getpixel((0, 0)) == 0


def test_uniform_image_does_not_divide_by_zero():
    flat = np.full((16, 16), 500, dtype=np.uint16)
    result = process_upload(make_dicom(flat))

    assert Image.open(BytesIO(result.data)).getpixel((0, 0)) == 0


def test_burned_in_annotation_is_flagged_not_silently_accepted():
    """Header stripping cannot remove text drawn into the pixels, so say so."""
    result = process_upload(make_dicom(BurnedInAnnotation="YES"))

    assert any("burned-in" in w.lower() for w in result.warnings)


def test_dicom_without_pixels_is_rejected_clearly():
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    ds = Dataset()
    ds.PatientName = "NO^PIXELS"
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    buffer = BytesIO()
    try:
        ds.save_as(buffer, enforce_file_format=True)
    except TypeError:
        ds.save_as(buffer, write_like_original=False)
    assert pydicom

    with pytest.raises(IntakeError, match="pixel"):
        process_upload(buffer.getvalue(), "empty.dcm")


# ── plain images ─────────────────────────────────────────────────────────────


def test_plain_png_passes_through():
    result = process_upload(png_bytes(), "xray.png")

    assert result.source_format == "image"
    assert result.mime_type == "image/png"
    Image.open(BytesIO(result.data)).load()


def test_jpeg_exif_is_stripped():
    """EXIF can carry camera and location data. Re-encoding is what removes it."""
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(
        buffer, format="JPEG", comment=b"SECRET-CAMERA-ID"
    )
    raw = buffer.getvalue()
    assert b"SECRET-CAMERA-ID" in raw

    result = process_upload(raw, "photo.jpg")
    assert b"SECRET-CAMERA-ID" not in result.data


# ── rejections ───────────────────────────────────────────────────────────────


def test_empty_file_rejected():
    with pytest.raises(IntakeError, match="empty"):
        process_upload(b"", "nothing.png")


def test_garbage_rejected_as_intake_error_not_crash():
    with pytest.raises(IntakeError):
        process_upload(b"this is not an image at all", "junk.txt")


def test_oversized_file_rejected_before_decoding():
    with pytest.raises(IntakeError, match="limit"):
        process_upload(b"\x00" * (51 * 1024 * 1024), "huge.png")


# ── hashing ──────────────────────────────────────────────────────────────────


def test_content_hash_is_stable_and_matches_stored_bytes():
    raw = make_dicom()
    first, second = process_upload(raw), process_upload(raw)

    assert first.content_hash == second.content_hash
    assert first.content_hash == sha256(first.data)
    assert len(first.content_hash) == 64


def test_different_images_hash_differently():
    # Both must be non-uniform: a flat image normalises to all-black whatever
    # its original value, so two flat images legitimately share a hash.
    gradient = np.arange(256, dtype=np.uint16).reshape(16, 16)

    a = process_upload(make_dicom(gradient))
    b = process_upload(make_dicom(gradient[::-1].copy()))

    assert a.content_hash != b.content_hash


def test_is_dicom_detects_by_magic_not_extension():
    assert is_dicom(make_dicom())
    assert not is_dicom(png_bytes())
    assert not is_dicom(b"short")


# ── against the reference project's real X-rays ──────────────────────────────


@pytest.mark.skipif(not SAMPLES.exists(), reason="reference samples not present")
def test_real_reference_xrays_process():
    files = sorted(SAMPLES.glob("*.png"))[:5]
    assert files, "expected sample PNGs in the reference project"

    for path in files:
        result = process_upload(path.read_bytes(), path.name)
        assert result.content_hash
        Image.open(BytesIO(result.data)).load()
