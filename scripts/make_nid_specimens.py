"""Draw a SPECIMEN national ID card for each demo test client.

Not a real card and not a copy of one: a plain layout with the same English
fields a Bangladeshi NID prints (Name, Date of Birth, ID NO), stamped SPECIMEN
across it, so the intake's NID reader can be demonstrated and tested without
anyone's real identity document.

    uv run --directory apps/api python ../../scripts/make_nid_specimens.py

Writes `nid-card.png` into every folder under demo/test that has a client.json.
The ID number is derived from the client's name, so it is the same each run.
"""

import hashlib
import json
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "demo" / "test"


def font(size: int, bold: bool = False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def specimen(name: str, born: date, number: str, father: str = "", mother: str = "") -> Image.Image:
    card = Image.new("RGB", (1000, 630), (236, 244, 236))
    d = ImageDraw.Draw(card)
    d.rectangle((0, 0, 999, 110), fill=(0, 106, 78))
    d.text(
        (40, 22),
        "Government of the People's Republic of Bangladesh",
        font=font(30, True),
        fill="white",
    )
    d.text((40, 66), "National ID Card", font=font(28), fill=(255, 220, 220))
    d.rectangle((40, 150, 260, 420), outline=(120, 120, 120), width=3)
    d.text((88, 270), "PHOTO", font=font(30), fill=(150, 150, 150))
    y = 150
    for label, value in (("Name", name.upper()), ("Father", father), ("Mother", mother)):
        if not value:
            continue
        d.text((300, y), label, font=font(24), fill=(80, 80, 80))
        d.text((300, y + 30), value, font=font(34, True), fill=(20, 20, 20))
        y += 92
    d.text(
        (300, y), f"Date of Birth  {born.strftime('%d %b %Y')}", font=font(30), fill=(20, 20, 20)
    )
    d.text((300, y + 60), f"ID NO  {number}", font=font(38, True), fill=(160, 0, 0))
    stamp = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(stamp).text(
        (180, 470), "SPECIMEN - NOT A REAL CARD", font=font(46, True), fill=(200, 0, 0, 110)
    )
    card = Image.alpha_composite(card.convert("RGBA"), stamp).convert("RGB")
    return card


def number_for(name: str) -> str:
    digest = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    return str(digest % 9_000_000_000 + 1_000_000_000)


def main() -> None:
    made = 0
    for folder in sorted(TESTS.iterdir()):
        client = folder / "client.json"
        if not client.exists():
            continue
        data = json.loads(client.read_text(encoding="utf-8"))
        born = date.fromisoformat(data["dateOfBirth"])
        card = specimen(data["name"], born, number_for(data["name"]))
        card.save(folder / "nid-card.png")
        made += 1
        print(f"{folder.name}: {data['name']}, {born}, {number_for(data['name'])}")
    print(f"{made} specimen cards written")


if __name__ == "__main__":
    main()
