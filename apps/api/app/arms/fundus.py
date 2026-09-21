"""Getting a fundus photograph into the one framing every retina model expects.

Separate from the arm that uses it because the training script needs exactly the
same code: a model scored on images framed one way and served images framed
another reports numbers that describe neither. `scripts/dr_experiment.py`
imports this module, so there is only one framing to get wrong.

Pure functions over PIL images. No torch, so it is importable and testable
without the vision extra.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

# A fundus camera photographs a disc of retina onto a black rectangle. How much
# of the frame that disc fills varies by camera from about 45% to over 90%, and
# nothing clinical is in the black. Thresholds are relative to the brightest
# pixel so a dim photograph is not mistaken for an empty one.
_BLACK_ABSOLUTE = 10.0
_BLACK_RELATIVE = 0.06

# Below this the frame is essentially empty: a lens cap, a failed export, or a
# scan of something else entirely.
MIN_LIT_FRACTION = 0.10

# Colour fundus photographs are strongly red-dominant. A greyscale image here is
# a radiograph or a red-free/angiography frame, which no colour-trained model
# should be asked to grade. Measured the same way as `triage._GREY_MAX_SPREAD`.
MIN_COLOUR_SPREAD = 6.0

# Mean brightness of the lit region on a 0-255 scale. The darkest gradable
# photograph across the datasets this was measured on sits well above this.
MIN_BRIGHTNESS = 12.0


@dataclass(frozen=True)
class Framed:
    """A fundus photograph cropped to its field of view and squared."""

    image: Image.Image
    lit_fraction: float
    colour_spread: float
    brightness: float


class NotAFundusPhoto(ValueError):
    """The image cannot be framed as a colour fundus photograph.

    Raised rather than guessed at. A grading model handed something else does
    not decline, it answers, and the answer looks exactly like a real one.
    """


def frame(image: Image.Image, size: int) -> Framed:
    """Crop to the lit disc, pad to a square, resize to `size`.

    Padded, never stretched. Many cameras clip the top and bottom of the disc,
    so its bounding box is wider than tall; resizing that box straight to a
    square would turn every circle into an ellipse and every round
    microaneurysm into an oval.
    """
    rgb = image.convert("RGB")

    # The mask only has to find a bounding box, and a 4752x3168 photograph is
    # fifteen million pixels of mostly nothing.
    small = rgb.copy()
    small.thumbnail((256, 256))
    pixels = np.asarray(small, dtype=np.float32)
    grey = pixels.mean(axis=2)

    lit = grey > max(_BLACK_ABSOLUTE, float(grey.max()) * _BLACK_RELATIVE)
    lit_fraction = float(lit.mean())
    if lit_fraction < MIN_LIT_FRACTION:
        raise NotAFundusPhoto("the image is almost entirely black")

    inside = pixels[lit]
    colour_spread = float((inside.max(axis=1) - inside.min(axis=1)).mean())
    brightness = float(inside.mean())
    if colour_spread < MIN_COLOUR_SPREAD:
        raise NotAFundusPhoto("the image is greyscale, not a colour fundus photograph")
    if brightness < MIN_BRIGHTNESS:
        raise NotAFundusPhoto("the photograph is too dark to grade")

    # Rows and columns that are at least 2% lit. A plain any() would let a
    # single hot pixel or a camera's date stamp stretch the box to the frame.
    rows = np.where(lit.mean(axis=1) > 0.02)[0]
    cols = np.where(lit.mean(axis=0) > 0.02)[0]
    scale_x = rgb.width / small.width
    scale_y = rgb.height / small.height
    crop = rgb.crop(
        (
            int(cols[0] * scale_x),
            int(rows[0] * scale_y),
            int((cols[-1] + 1) * scale_x),
            int((rows[-1] + 1) * scale_y),
        )
    )

    side = max(crop.size)
    canvas = Image.new("RGB", (side, side), (0, 0, 0))
    canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))

    return Framed(
        image=canvas.resize((size, size), Image.Resampling.BICUBIC),
        lit_fraction=round(lit_fraction, 4),
        colour_spread=round(colour_spread, 2),
        brightness=round(brightness, 2),
    )
