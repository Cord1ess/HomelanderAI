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
    """Normalise one uploaded file into a stored-ready PNG.

    Raises IntakeError for anything unreadable — the caller turns that into an
    `insufficient_evidence` outcome rather than a 500.
    """
    if not raw:
        raise IntakeError("File is empty")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise IntakeError(
            f"File is {len(raw) / 1_048_576:.1f} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB"
        )

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

    tags = {
        name: str(ds.get(name))
        for name in _CLINICAL_TAGS
        if ds.get(name, None) is not None
    }

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
