"""Evidence intake: de-identify an uploaded file and hand back what to store.

The de-identification approach is deliberately blunt. Rather than stripping
identifying DICOM tags one by one and hoping the list is complete, we **discard
the DICOM entirely** and keep only a rendered PNG of the pixels, plus a handful
of clinical tags copied out explicitly.

A tag that is never stored cannot leak. This is both simpler and strictly safer
than a removal list, and it means everything downstream receives one format.

The trade is that the original file is gone, so the image cannot later be
re-windowed. For screening that is fine.

Pure functions over bytes — no database, no filesystem, no framework. The caller
decides where the result goes.
"""

import hashlib
from dataclasses import dataclass, field
from io import BytesIO

import numpy as np
from PIL import Image

from app import ecg

# 50 MB. Chest radiographs are a few MB; anything far larger is a mistake or an
# attack, and we would rather say so than try to process it.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# DICOM files carry the magic "DICM" at byte 128, after a 128-byte preamble.
_DICOM_MAGIC_OFFSET = 128
_DICOM_MAGIC = b"DICM"

# Tags worth keeping. Everything else — names, IDs, dates, institution,
# referring physician — is dropped with the rest of the header.
_CLINICAL_TAGS = (
    "Modality",
    "BodyPartExamined",
    "ViewPosition",
    "PhotometricInterpretation",
    "Rows",
    "Columns",
)


class IntakeError(ValueError):
    """The upload cannot be turned into something scoreable."""


@dataclass
class ProcessedFile:
    """What to store, and what we know about it."""

    data: bytes
    content_hash: str
    mime_type: str
    source_format: str
    deidentified: bool
    clinical_tags: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def is_dicom(raw: bytes) -> bool:
    return (
        len(raw) > _DICOM_MAGIC_OFFSET + 4
        and raw[_DICOM_MAGIC_OFFSET : _DICOM_MAGIC_OFFSET + 4] == _DICOM_MAGIC
    )


def process_upload(raw: bytes, filename: str = "") -> ProcessedFile:
    """Normalise one uploaded file into its stored form.

    Images and DICOMs become a PNG. A 12-lead ECG export (CSV) becomes the
    canonical signal array — numbers only, so a name in the export's comment
    line never reaches storage. A note or report (PDF with a text layer, or a
    text file) becomes plain UTF-8 text. Raises IntakeError for anything
    unreadable; the caller turns that into an `insufficient_evidence` outcome,
    not a 500.
    """
    if not raw:
        raise IntakeError("File is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise IntakeError(
            f"File is {len(raw) / 1_048_576:.1f} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB"
        )

    if ecg.is_canonical(raw):
        # Already the stored form: the pipeline re-reads evidence from disk
        # under its original filename, and a second pass must change nothing.
        try:
            ecg.from_bytes(raw)
        except Exception as exc:
            raise IntakeError(f"not a readable stored ECG: {exc}") from exc
        return ProcessedFile(
            data=raw,
            content_hash=sha256(raw),
            mime_type="application/x-npy",
            source_format="ecg",
            deidentified=True,
        )

    if raw[:5] == b"%PDF-":
        return _document(_pdf_text(raw))

    if _looks_like_signal_export(raw, filename):
        try:
            signal = ecg.parse_csv(raw)
        except ecg.NotAnEcg as exc:
            if exc.looked_like_ecg:
                raise IntakeError(f"not a readable 12-lead ECG export: {exc}") from exc
            # A text file that never had lead columns is a note, a report or a
            # table, and is kept as text for the underwriter and the medication
            # check to read.
            return _document(_decode_text(raw))
        data = ecg.to_bytes(ecg.canonical(signal))
        return ProcessedFile(
            data=data,
            content_hash=sha256(data),
            mime_type="application/x-npy",
            source_format="ecg",
            # Numbers only. Whatever the export's header said is not kept.
            deidentified=True,
            clinical_tags={
                "SampleRate": f"{signal.sample_rate:g}",
                "Seconds": f"{signal.seconds:.1f}",
            },
            warnings=list(signal.notes),
        )

    if is_dicom(raw) and _is_mammogram(raw):
        # Mirai reads the DICOM itself, so a mammogram is kept as one — with
        # the patient, physician and institution tags removed and the pixels
        # and view tags left. Everything else DICOM becomes a PNG below.
        return _mammogram(raw)

    if is_dicom(raw):
        png, tags, warnings = _dicom_to_png(raw)
        return ProcessedFile(
            data=png,
            content_hash=sha256(png),
            mime_type="image/png",
            source_format="dicom",
            deidentified=True,
            clinical_tags=tags,
            warnings=warnings,
        )

    png = _image_to_png(raw, filename)
    return ProcessedFile(
        data=png,
        content_hash=sha256(png),
        mime_type="image/png",
        source_format="image",
        # Re-encoding drops EXIF, which can carry device and location data.
        deidentified=True,
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Text files: a signal export, or a note. Which one is decided by reading it.
_SIGNAL_SUFFIXES = (".csv", ".txt", ".tsv", ".md", ".text")
# PDF, PNG and JPEG magic: a mis-named picture or document is not text.
_NOT_TEXT_MAGIC = (b"%", b"\x89", b"\xff")

# A note longer than this is not a note. Keeps a mis-uploaded data dump out
# of the database.
MAX_DOCUMENT_CHARS = 200_000


def _looks_like_signal_export(raw: bytes, filename: str) -> bool:
    return (filename or "").lower().endswith(_SIGNAL_SUFFIXES) and raw[:1] not in _NOT_TEXT_MAGIC


# ── documents ────────────────────────────────────────────────────────────────


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IntakeError("not a readable text file")


def _pdf_text(raw: bytes) -> str:
    """The PDF's text layer. A scanned page has none, and saying so beats
    storing an empty note as if it had been read."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise IntakeError(f"not a readable PDF: {exc}") from exc
    text = "\n\n".join(pages)
    if not any(ch.isalpha() for ch in text):
        raise IntakeError(
            "the PDF has no text layer (a scanned document); export or type the text instead"
        )
    return text


def _document(text: str) -> ProcessedFile:
    """A note, report or prescription, kept as plain UTF-8 text.

    Not de-identified: a clinical note names its patient throughout and cannot
    be stripped without reading it, so the row records that honestly and the
    note is shown only to the underwriter who holds the case.
    """
    text = text.replace("\r\n", "\n").replace("\x00", "").strip()
    if not any(ch.isalpha() for ch in text):
        raise IntakeError("the document contains no text")
    if len(text) > MAX_DOCUMENT_CHARS:
        raise IntakeError(
            f"the document is {len(text):,} characters; the limit is {MAX_DOCUMENT_CHARS:,}"
        )
    data = text.encode("utf-8")
    return ProcessedFile(
        data=data,
        content_hash=sha256(data),
        mime_type="text/plain",
        source_format="document",
        deidentified=False,
        clinical_tags={"Characters": str(len(text)), "Lines": str(text.count("\n") + 1)},
    )


# ── mammograms ───────────────────────────────────────────────────────────────

# Tags that name or locate the person. Removed from a mammogram before it is
# stored; everything else stays, because the Mirai server reads the file as
# a whole and refuses one stripped to the pixels and view tags.
_MAMMOGRAM_IDENTIFYING = (
    "PatientName",
    "PatientID",
    "OtherPatientIDs",
    "OtherPatientNames",
    "PatientBirthDate",
    "PatientBirthTime",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "PatientMotherBirthName",
    "EthnicGroup",
    "Occupation",
    "AdditionalPatientHistory",
    "PatientComments",
    "InstitutionName",
    "InstitutionAddress",
    "InstitutionalDepartmentName",
    "ReferringPhysicianName",
    "ReferringPhysicianAddress",
    "ReferringPhysicianTelephoneNumbers",
    "PerformingPhysicianName",
    "PhysiciansOfRecord",
    "NameOfPhysiciansReadingStudy",
    "OperatorsName",
    "RequestingPhysician",
    "AccessionNumber",
    "StudyID",
    "StationName",
    "DeviceSerialNumber",
    "RequestAttributesSequence",
    "ReferencedPatientSequence",
)


def _is_mammogram(raw: bytes) -> bool:
    import pydicom

    try:
        ds = pydicom.dcmread(BytesIO(raw), stop_before_pixels=True, force=True)
    except Exception:
        return False
    return str(ds.get("Modality", "")).upper() == "MG"


def _mammogram(raw: bytes) -> ProcessedFile:
    import pydicom

    try:
        ds = pydicom.dcmread(BytesIO(raw), force=True)
        _ = ds.pixel_array  # unreadable pixels fail here, not at scoring time
    except Exception as exc:
        raise IntakeError(f"Not a readable mammogram DICOM: {exc}") from exc

    if str(ds.get("PatientIdentityRemoved", "")).upper() == "YES":
        # Already our stored form (the pipeline re-reads evidence from disk).
        return ProcessedFile(
            data=raw,
            content_hash=sha256(raw),
            mime_type="application/dicom",
            source_format="mammogram",
            deidentified=True,
            clinical_tags=_mammogram_tags(ds),
        )

    for keyword in _MAMMOGRAM_IDENTIFYING:
        if keyword in ds:
            del ds[keyword]
    ds.remove_private_tags()
    # The server expects a patient to exist; it gets an anonymous one.
    ds.PatientName = "ANONYMOUS"
    ds.PatientID = sha256(raw)[:16]
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "HomelanderAI intake: identifying tags removed, image tags kept"
    warnings: list[str] = []
    if not ds.get("ImageLaterality") or not ds.get("ViewPosition"):
        warnings.append(
            "the DICOM does not say which breast or view it is; Mirai needs all four labelled"
        )

    buffer = BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    data = buffer.getvalue()
    return ProcessedFile(
        data=data,
        content_hash=sha256(data),
        mime_type="application/dicom",
        source_format="mammogram",
        deidentified=True,
        clinical_tags=_mammogram_tags(ds),
        warnings=warnings,
    )


def _mammogram_tags(ds) -> dict[str, str]:
    return {
        name: str(ds.get(name))
        for name in ("Modality", "ImageLaterality", "ViewPosition", "Rows", "Columns")
        if ds.get(name, None) is not None
    }


def dicom_to_png(raw: bytes) -> bytes:
    """A stored mammogram drawn for the screen."""
    png, _, _ = _dicom_to_png(raw)
    return png


# ── DICOM ────────────────────────────────────────────────────────────────────


def _dicom_to_png(raw: bytes) -> tuple[bytes, dict[str, str], list[str]]:
    import pydicom

    try:
        ds = pydicom.dcmread(BytesIO(raw), force=True)
    except Exception as exc:
        raise IntakeError(f"Not a readable DICOM file: {exc}") from exc

    try:
        arr = ds.pixel_array
    except Exception as exc:
        raise IntakeError(f"DICOM has no readable pixel data: {exc}") from exc

    warnings: list[str] = []

    # Pixels themselves can carry burned-in patient details. We cannot strip
    # those without OCR, so flag it for a human instead of pretending otherwise.
    if str(ds.get("BurnedInAnnotation", "")).upper() == "YES":
        warnings.append(
            "DICOM declares burned-in annotation — the image may show identifying "
            "text that header removal does not address"
        )

    arr = _apply_voi_lut(arr, ds)

    # Multi-frame: screening only needs one image.
    if arr.ndim > 2:
        warnings.append(f"Multi-frame DICOM ({arr.shape[0]} frames); using the first")
        arr = arr[0]

    # MONOCHROME1 stores white-on-black inverted relative to MONOCHROME2.
    if str(ds.get("PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        arr = arr.max() - arr

    tags = {name: str(ds.get(name)) for name in _CLINICAL_TAGS if ds.get(name, None) is not None}

    return _array_to_png(arr), tags, warnings


def _apply_voi_lut(arr: np.ndarray, ds) -> np.ndarray:
    """Windowing, when the file specifies it. Without this many X-rays render
    as a nearly black or nearly white rectangle.

    The import moved between pydicom 2 and 3, and it is optional either way.
    """
    try:
        from pydicom.pixels import apply_voi_lut
    except ImportError:
        try:
            from pydicom.pixel_data_handlers.util import apply_voi_lut
        except ImportError:
            return arr

    try:
        return apply_voi_lut(arr, ds)
    except Exception:
        # A malformed LUT should cost us contrast, not the whole upload.
        return arr


def _array_to_png(arr: np.ndarray) -> bytes:
    """Scale arbitrary pixel depth to 8-bit grayscale and encode as PNG."""
    arr = arr.astype(np.float64)
    lo, hi = float(arr.min()), float(arr.max())

    # A uniform image has no range to stretch; emit black rather than divide by zero.
    arr = np.zeros_like(arr) if hi <= lo else (arr - lo) / (hi - lo) * 255.0

    image = Image.fromarray(arr.astype(np.uint8), mode="L")
    return _encode_png(image)


# ── plain images ─────────────────────────────────────────────────────────────


def _image_to_png(raw: bytes, filename: str) -> bytes:
    try:
        image = Image.open(BytesIO(raw))
        image.load()
    except Exception as exc:
        name = filename or "file"
        raise IntakeError(f"{name} is not a readable image: {exc}") from exc

    # Re-encoding is what actually removes EXIF; copying the pixels leaves the
    # metadata behind on some formats.
    if image.mode not in ("L", "RGB"):
        image = image.convert("L" if image.mode in ("1", "I", "I;16", "F") else "RGB")

    return _encode_png(image)


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
