"""Generate calibrated sample retinal fundus images for manual intake testing."""

import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples", "retina")
os.makedirs(SAMPLES_DIR, exist_ok=True)


def create_fundus(severity: str = "normal", size=(512, 512)) -> Image.Image:
    """Generate a synthetic fundus-like image with a red/orange retina on black background."""
    img = Image.new("RGB", size, color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(size[0] * 0.08)
    # Circular retina (warm orange-red typical of fundus photography)
    draw.ellipse([pad, pad, size[0] - pad, size[1] - pad], fill=(185, 75, 25))

    # Optic disc (yellowish-cream oval on nasal side, physiological size ~3-4% of area)
    disc_x = int(size[0] * 0.72)
    disc_y = int(size[1] * 0.50)
    disc_r = int(size[0] * 0.06)
    draw.ellipse([disc_x - disc_r, disc_y - disc_r, disc_x + disc_r, disc_y + disc_r], fill=(235, 210, 145))

    # Macula (darker circular area on temporal side)
    macula_x = int(size[0] * 0.38)
    macula_y = int(size[1] * 0.50)
    macula_r = int(size[0] * 0.05)
    draw.ellipse([macula_x - macula_r, macula_y - macula_r, macula_x + macula_r, macula_y + macula_r], fill=(145, 50, 18))

    # Retinal blood vessels radiating from optic disc
    for angle in [-140, -105, 105, 140]:
        draw.arc([disc_x - int(size[0]*0.45), disc_y - int(size[1]*0.3), disc_x + int(size[0]*0.1), disc_y + int(size[1]*0.3)],
                 start=angle, end=angle+50, fill=(120, 30, 15), width=3)

    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    draw = ImageDraw.Draw(img)

    if severity == "mild":
        # A few microaneurysms (pinpoint red/black dots)
        for x, y in [(170, 180), (200, 260), (230, 210), (250, 310), (280, 200)]:
            draw.ellipse([x, y, x + 5, y + 5], fill=(42, 12, 10))

    elif severity == "severe":
        # Multiple microaneurysms, flame/blot hemorrhages, and hard lipid exudates
        # Microaneurysms & blot hemorrhages
        for x, y, r in [
            (160, 170, 5), (190, 240, 7), (220, 200, 6), (250, 290, 8),
            (270, 190, 5), (290, 250, 7), (320, 220, 6), (210, 330, 9),
            (180, 290, 8), (240, 160, 6), (270, 320, 7), (310, 290, 8)
        ]:
            draw.ellipse([x, y, x + r, y + r], fill=(45, 12, 10))

        # Hard exudates (bright yellowish lipid deposits near macula)
        for x, y, r in [
            (190, 150, 7), (230, 340, 8), (280, 320, 9), (210, 270, 7),
            (250, 170, 6), (290, 180, 8), (170, 230, 7), (200, 210, 6)
        ]:
            draw.ellipse([x, y, x + r, y + r], fill=(255, 242, 165))

    return img


def main():
    normal = create_fundus("normal")
    normal_path = os.path.join(SAMPLES_DIR, "01_normal_fundus.png")
    normal.save(normal_path, format="PNG")
    print(f"Saved: {normal_path}")

    mild = create_fundus("mild")
    mild_path = os.path.join(SAMPLES_DIR, "02_diabetic_retinopathy_mild.png")
    mild.save(mild_path, format="PNG")
    print(f"Saved: {mild_path}")

    severe = create_fundus("severe")
    severe_path = os.path.join(SAMPLES_DIR, "03_diabetic_retinopathy_severe.png")
    severe.save(severe_path, format="PNG")
    print(f"Saved: {severe_path}")


if __name__ == "__main__":
    main()
