"""12-lead ECG signals: reading an export, storing it, drawing it.

An ECG arrives as the file an ECG machine or app exports — a CSV with one
column per lead, in millivolts, at whatever sampling rate the device used.
What the models need is fixed: twelve leads in a fixed order, 4096 samples at
400 Hz, in units of 0.1 mV. This module gets from one to the other, and refuses
what it cannot read rather than guessing:

- **Leads** are matched by name (I / DI, aVR / AVR, V1 ...). Fewer than twelve
  is an error, because the models were trained on all twelve.
- **The sampling rate** must be stated — a `time` column, or a line such as
  `fs=500` — because a wrong rate stretches every QRS complex and the models
  cannot tell. Nothing is assumed.
- **Units** are millivolts. A file whose values run into the hundreds is in
  microvolts, and is converted with a note; anything else is refused.

**Paper printouts and photographs are not accepted.** Digitising a scanned
3x4 strip recovers about 2.5 seconds per lead at poor fidelity, and the models
want ten seconds of every lead. Saying so is more useful than a wrong reading.

The stored form is a plain `.npy` array of shape (12, 4096) in millivolts at
400 Hz. It carries no header, no name, no date: a signal export can hold a
patient's name in a comment line, and the canonical file cannot.
"""

import csv
import io
import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

# The order both models were trained on (Ribeiro 2020 / Lima 2021 data README).
LEADS: tuple[str, ...] = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")

# What exports call each lead, lower-cased and stripped of spaces/underscores.
_ALIASES: dict[str, str] = {
    "i": "I",
    "di": "I",
    "leadi": "I",
    "l1": "I",
    "mli": "I",
    "ii": "II",
    "dii": "II",
    "leadii": "II",
    "l2": "II",
    "mlii": "II",
    "iii": "III",
    "diii": "III",
    "leadiii": "III",
    "l3": "III",
    "mliii": "III",
    "avr": "aVR",
    "avl": "aVL",
    "avf": "aVF",
    "v1": "V1",
    "v2": "V2",
    "v3": "V3",
    "v4": "V4",
    "v5": "V5",
    "v6": "V6",
}
_TIME_COLUMNS = {"time", "t", "seconds", "sec", "s", "ms", "millis", "milliseconds", "timestamp"}

SAMPLE_RATE = 400
LENGTH = 4096
# The models' unit is 1e-4 V, so millivolts are multiplied by this.
MV_TO_MODEL = 10.0
MIN_SECONDS = 5.0
# Values above this cannot be millivolts on a surface ECG; they are microvolts.
_MAX_PLAUSIBLE_MV = 50.0


class NotAnEcg(ValueError):
    """The bytes are not a 12-lead ECG export we can read. The message says why.

    `looked_like_ecg` is set once lead columns were found: the file was meant
    to be an ECG and the reason is worth showing the operator, as opposed to a
    lab table or a note that merely shares the extension.
    """

    def __init__(self, message: str, looked_like_ecg: bool = False) -> None:
        super().__init__(message)
        self.looked_like_ecg = looked_like_ecg


@dataclass
class Signal:
    """A 12-lead tracing in millivolts, leads in `LEADS` order."""

    leads: np.ndarray  # (12, N) float32, mV
    sample_rate: float
    notes: list[str] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        return self.leads.shape[1] / self.sample_rate


def _normalise_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name.strip().strip('"').lower())


def _sample_rate_from_comments(text: str) -> float | None:
    """`fs=500`, `# sampling rate: 500 Hz`, `sample_rate,500` — anything that
    names a rate in a leading line before the data starts."""
    head = "\n".join(text.splitlines()[:20])
    match = re.search(
        r"(?:fs|sampling[\s_]*rate|sample[\s_]*rate|frequency)\D{0,10}(\d{2,5})", head, re.I
    )
    return float(match.group(1)) if match else None


def parse_csv(raw: bytes) -> Signal:
    """Read an ECG export. Raises `NotAnEcg` with a reason for anything else."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NotAnEcg("not a text file") from exc

    lines = [ln for ln in text.splitlines() if ln.strip()]
    data_lines = [ln for ln in lines if not ln.lstrip().startswith(("#", "//", ";"))]
    if len(data_lines) < 2:
        raise NotAnEcg("no data rows")

    dialect_sample = "\n".join(data_lines[:5])
    try:
        dialect = csv.Sniffer().sniff(dialect_sample, delimiters=",;\t ")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(data_lines, dialect))
    header = [_normalise_name(c) for c in rows[0]]

    columns: dict[str, int] = {}
    time_col: int | None = None
    for index, name in enumerate(header):
        if name in _ALIASES and _ALIASES[name] not in columns:
            columns[_ALIASES[name]] = index
        elif name in _TIME_COLUMNS and time_col is None:
            time_col = index
    missing = [lead for lead in LEADS if lead not in columns]
    if len(columns) < 12:
        if not columns:
            raise NotAnEcg(
                "no lead columns found (expected a header naming I, II, III, aVR ... V6)"
            )
        raise NotAnEcg(
            f"only {len(columns)} of 12 leads found; missing {', '.join(missing)}",
            looked_like_ecg=True,
        )

    try:
        table = np.array(
            [[float(cell) for cell in row] for row in rows[1:] if len(row) == len(header)],
            dtype=np.float64,
        )
    except ValueError as exc:
        raise NotAnEcg(f"a data cell is not a number: {exc}", looked_like_ecg=True) from exc
    if table.ndim != 2 or table.shape[0] < 2:
        raise NotAnEcg("no numeric rows", looked_like_ecg=True)

    notes: list[str] = []
    rate = None
    if time_col is not None:
        steps = np.diff(table[:, time_col])
        step = float(np.median(steps))
        if step <= 0:
            raise NotAnEcg("the time column does not increase", looked_like_ecg=True)
        # Seconds, unless the values are far too large to be seconds.
        if step > 0.5:
            step /= 1000.0
            notes.append("time column read as milliseconds")
        rate = 1.0 / step
    if rate is None:
        rate = _sample_rate_from_comments(text)
    if rate is None:
        raise NotAnEcg(
            "sampling rate unknown: add a time column or a line such as fs=500",
            looked_like_ecg=True,
        )
    if not 100 <= rate <= 5000:
        raise NotAnEcg(
            f"sampling rate {rate:g} Hz is not plausible for an ECG", looked_like_ecg=True
        )

    leads = np.stack([table[:, columns[lead]] for lead in LEADS]).astype(np.float32)
    if not np.all(np.isfinite(leads)):
        raise NotAnEcg("the signal contains NaN or infinite values", looked_like_ecg=True)

    peak = float(np.percentile(np.abs(leads), 99.9))
    if peak > _MAX_PLAUSIBLE_MV:
        # Microvolts. A 1 mV R wave is 1000 here.
        leads = leads / 1000.0
        notes.append("values read as microvolts and converted to millivolts")
        peak /= 1000.0
    if peak > _MAX_PLAUSIBLE_MV or peak < 0.05:
        raise NotAnEcg(
            f"amplitudes ({peak:.2f} mV at the 99.9th percentile) are not an ECG in millivolts",
            looked_like_ecg=True,
        )

    signal = Signal(leads=leads, sample_rate=rate, notes=notes)
    if signal.seconds < MIN_SECONDS:
        raise NotAnEcg(
            f"only {signal.seconds:.1f} s of signal; at least {MIN_SECONDS:g} s is needed",
            looked_like_ecg=True,
        )
    return signal


def canonical(signal: Signal) -> np.ndarray:
    """(12, 4096) at 400 Hz in millivolts: resampled, then cut or zero-padded
    at the end, exactly as the training data was prepared."""
    n = signal.leads.shape[1]
    src_t = np.arange(n) / signal.sample_rate
    dst_t = np.arange(int(round(signal.seconds * SAMPLE_RATE))) / SAMPLE_RATE
    resampled = np.stack([np.interp(dst_t, src_t, lead) for lead in signal.leads]).astype(
        np.float32
    )
    out = np.zeros((12, LENGTH), dtype=np.float32)
    take = min(LENGTH, resampled.shape[1])
    out[:, :take] = resampled[:, :take]
    return out


def to_bytes(array: np.ndarray) -> bytes:
    """The stored form: a `.npy` of the canonical array. Deterministic bytes,
    so the same tracing always hashes the same."""
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(array, dtype=np.float32))
    return buffer.getvalue()


def is_canonical(raw: bytes) -> bool:
    return raw[:6] == b"\x93NUMPY"


def from_bytes(raw: bytes) -> np.ndarray:
    array = np.load(io.BytesIO(raw), allow_pickle=False)
    if array.shape != (12, LENGTH) or array.dtype != np.float32:
        raise NotAnEcg(
            f"stored ECG has shape {array.shape} {array.dtype}, expected (12, {LENGTH}) float32"
        )
    return array


def to_model_units(array: np.ndarray) -> np.ndarray:
    return array * MV_TO_MODEL


def render(
    array: np.ndarray,
    saliency: np.ndarray | None = None,
    width: int = 1600,
    row_height: int = 90,
) -> bytes:
    """The twelve leads as a PNG, one under the other at a common scale.

    `saliency` is an optional per-sample weight in [0, 1] that shades the
    background where the classifier looked — the ECG's equivalent of the
    chest arm's heatmap. Drawn with Pillow only.
    """
    n = array.shape[1]
    margin_left, top_pad = 56, 16
    height = top_pad * 2 + row_height * 12
    image = Image.new("RGB", (width, height), (13, 14, 9))
    draw = ImageDraw.Draw(image)
    plot_w = width - margin_left - 16
    xs = margin_left + np.arange(n) * (plot_w / (n - 1))

    if saliency is not None and saliency.size == n:
        heat = np.clip(saliency, 0.0, 1.0)
        # One vertical band per column of pixels, intensity from the samples in it.
        for px in range(margin_left, margin_left + plot_w):
            lo = int((px - margin_left) / plot_w * n)
            hi = max(lo + 1, int((px + 1 - margin_left) / plot_w * n))
            h = float(heat[lo:hi].max())
            if h > 0.05:
                draw.line(
                    [(px, top_pad), (px, height - top_pad)],
                    fill=(int(80 + 150 * h), int(30 * (1 - h)), int(30 * (1 - h))),
                )

    # Grid: one second per major line at 400 Hz.
    for sec in range(0, n // SAMPLE_RATE + 1):
        x = margin_left + sec * SAMPLE_RATE * (plot_w / (n - 1))
        draw.line([(x, top_pad), (x, height - top_pad)], fill=(40, 43, 30))

    scale = row_height * 0.32  # pixels per millivolt
    for row, lead in enumerate(LEADS):
        base = top_pad + row * row_height + row_height * 0.6
        draw.line([(margin_left, base), (width - 16, base)], fill=(30, 32, 22))
        draw.text((10, base - 8), lead, fill=(176, 179, 154))
        ys = base - array[row] * scale
        draw.line(list(zip(xs.tolist(), ys.tolist(), strict=True)), fill=(206, 217, 140), width=1)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
