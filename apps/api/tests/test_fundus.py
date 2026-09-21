"""Framing a fundus photograph.

Two properties matter. The disc must come out round, because a stretched image
turns every lesion into a shape the model never saw. And anything that is not a
colour fundus photograph must be refused rather than framed, because a grading
model handed something else does not decline — it answers.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.arms.fundus import NotAFundusPhoto, frame

SAMPLES = Path(__file__).resolve().parents[3] / "samples" / "retina"


def disc_on_black(width: int, height: int, box: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    ImageDraw.Draw(image).ellipse(box, fill=(185, 75, 25))
    return image


def lit_extent(image: Image.Image) -> tuple[int, int]:
    """Width and height of the lit region, in pixels."""
    lit = np.asarray(image.convert("L")) > 20
    rows = np.where(lit.any(axis=1))[0]
    cols = np.where(lit.any(axis=0))[0]
    return int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


# ── the disc stays round ─────────────────────────────────────────────────────


def test_a_full_disc_fills_the_frame():
    """A small disc in a wide black frame is cropped to the disc."""
    framed = frame(disc_on_black(1200, 800, (400, 200, 800, 600)), 256)

    assert framed.image.size == (256, 256)
    width, height = lit_extent(framed.image)
    assert width > 240 and height > 240


def test_a_clipped_disc_is_padded_not_stretched():
    """Many cameras cut off the top and bottom of the disc. Its bounding box is
    then wider than tall, and resizing that box to a square would squash the
    whole retina. The missing part has to stay missing."""
    # A disc 1000 wide, of which only the middle 700 rows fit in the frame.
    clipped = disc_on_black(1200, 700, (100, -150, 1100, 850))
    framed = frame(clipped, 256)

    width, height = lit_extent(framed.image)
    assert width > 240, "the disc should still span the full width"
    assert height == pytest.approx(width * 0.7, abs=8), "the disc was stretched to fit"


def test_the_measurements_describe_the_photograph():
    framed = frame(disc_on_black(800, 800, (50, 50, 750, 750)), 128)

    assert 0.5 < framed.lit_fraction < 0.75
    assert framed.colour_spread > 100, "an orange disc is strongly coloured"
    assert framed.brightness > 50


# ── refusing what is not a fundus photograph ─────────────────────────────────


def test_a_black_frame_is_refused():
    with pytest.raises(NotAFundusPhoto, match="black"):
        frame(Image.new("RGB", (400, 400), (0, 0, 0)), 128)


def test_a_greyscale_image_is_refused():
    """A chest X-ray reaching this arm is exactly the routing failure that once
    scored a lung at 98.8. Triage should stop it first; this is the backstop."""
    grey = Image.new("L", (400, 400), 0)
    ImageDraw.Draw(grey).ellipse((20, 20, 380, 380), fill=160)

    with pytest.raises(NotAFundusPhoto, match="greyscale"):
        frame(grey, 128)


def test_a_photograph_too_dark_to_read_is_refused():
    with pytest.raises(NotAFundusPhoto):
        frame(disc_on_black(400, 400, (20, 20, 380, 380)).point(lambda v: v // 25), 128)


# ── real photographs ─────────────────────────────────────────────────────────


@pytest.mark.skipif(not SAMPLES.exists(), reason="sample photographs not present")
def test_real_photographs_are_all_accepted_and_come_out_square():
    """Ten EyePACS photographs from four different cameras, including two with a
    clipped disc. None may be refused: a gate that turns away real evidence is
    worse than no gate."""
    photographs = sorted(SAMPLES.glob("*.jpeg"))
    assert photographs

    for path in photographs:
        with Image.open(path) as image:
            framed = frame(image, 224)
        assert framed.image.size == (224, 224), path.name
        assert framed.image.mode == "RGB"
