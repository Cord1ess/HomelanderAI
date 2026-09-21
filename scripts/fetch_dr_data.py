"""Download the diabetic-retinopathy datasets and the backbone weights.

    python scripts/fetch_dr_data.py                 # everything (about 13 GB)
    python scripts/fetch_dr_data.py ddr idrid       # just these
    python scripts/fetch_dr_data.py models          # just the backbone weights

No account is needed for any of it. Everything lands in `data/dr/`, which is
gitignored. Never commit these images.

Each dataset is unpacked into the same shape, so nothing downstream has to know
where it came from:

    data/dr/<name>/images/<file>
    data/dr/<name>/labels.csv          image,grade,split

`grade` is the ICDR scale: 0 none, 1 mild, 2 moderate, 3 severe, 4 proliferative.

Why these and not the obvious ones:

  ddr        The training set. 12,522 gradable photographs from 147 hospitals
             and 42 camera types across China (Li et al., Information Sciences
             2019). Multi-site is the point: with one hospital per class a model
             learns the camera, which is exactly what went wrong with the Kaggle
             TB set. The official train/valid/test split is restored.
  aptos      External test only. Aravind Eye Hospital, India. 8.6 GB.
             NEVER TRAIN ON IT. Image resolution alone predicts the label (about
             91% on DR vs no DR, measured on 500 images), because different
             clinics used different cameras and saw different patients.
  idrid      External test. Nanded, India; one clinic, one camera. CC BY 4.0,
             the only one here with a fully clean licence. 516 images.
  deepdrid   External test. Shanghai screening programme. CC BY-SA 4.0.

Deliberately not here:

  EyePACS / Kaggle DR 2015   Single-grader labels, about a quarter ungradable,
                             and FLAIR was pretrained on all of it.
  Messidor-2                 The standard benchmark, and the one to add next.
                             ADCIS prohibits redistribution, so the mirrors that
                             exist are not legitimate. Request it properly from
                             https://www.adcis.net/en/third-party/messidor2/ ;
                             the adjudicated grades are public (Krause 2018).

The mirrors used for DDR and APTOS are community re-uploads. Their class counts
were checked against the official figures before use; that is the only reason to
trust them, and `unpack` re-checks on every run.
"""

import csv
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data" / "dr"
RAW = DATA / "raw"
MODELS = DATA / "models"

HEADERS = {"User-Agent": "Mozilla/5.0"}

ARCHIVES = {
    "ddr": "https://huggingface.co/datasets/MahsaTorki/DDR_dataset/resolve/main/DDR%20dataset.zip",
    "aptos": "https://www.kaggle.com/api/v1/datasets/download/mariaherrerot/aptos2019",
    "idrid": "https://huggingface.co/datasets/MahsaTorki/IDRiD_Dataset/resolve/main/B.Disease_Grading.zip",
    "deepdrid": "https://github.com/deepdrdoc/DeepDRiD/archive/refs/heads/master.zip",
}

# The official DDR split. The 3 GB mirror ships one flat CSV; these restore which
# image belongs to train, valid and test, so a number here is comparable with
# the paper's.
DDR_SPLITS = "https://huggingface.co/datasets/ctmedtech/DDR-dataset/resolve/main/DR_grading/{}.txt"

WEIGHTS = {
    # Apache-2.0. Silva-Rodriguez et al., "A Foundation LAnguage-Image model of
    # the Retina", Medical Image Analysis 2025.
    "flair.safetensors": "https://huggingface.co/jusiro2/FLAIR/resolve/main/model.safetensors",
    # Non-commercial research licence. Engelmann & Bernabeu 2024.
    "retfoundgreen_statedict.pth": (
        "https://github.com/justinengelmann/RETFound_Green/releases/download/"
        "v0.1/retfoundgreen_statedict.pth"
    ),
}

# Grade counts published for each dataset. A mirror that does not match these is
# not the dataset it claims to be.
EXPECTED = {
    "ddr": {0: 6266, 1: 630, 2: 4477, 3: 236, 4: 913},
    "aptos": {0: 1805, 1: 370, 2: 999, 3: 193, 4: 295},
    "idrid": {0: 168, 1: 25, 2: 168, 3: 93, 4: 62},
}


def download(url: str, target: Path) -> None:
    """Fetch to `target`, resuming a partial file rather than starting again.

    These are multi-gigabyte files on a home connection. A download that has to
    restart from zero after a dropped connection may never finish.
    """
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    have = partial.stat().st_size if partial.exists() else 0

    request = urllib.request.Request(url, headers={**HEADERS, "Range": f"bytes={have}-"})
    with urllib.request.urlopen(request, timeout=120) as response:
        # 206 means the server honoured the range. 200 means it sent the whole
        # file, so whatever is on disk has to be discarded.
        resumed = response.status == 206
        total = have + int(response.headers.get("Content-Length", 0)) if resumed else None
        with open(partial, "ab" if resumed else "wb") as handle:
            done = have if resumed else 0
            while chunk := response.read(1 << 20):
                handle.write(chunk)
                done += len(chunk)
                if done % (200 << 20) < (1 << 20):
                    size = f" of {total / 1e9:.1f} GB" if total else ""
                    print(f"    {done / 1e9:.2f} GB{size}", flush=True)
    partial.replace(target)


def write_labels(name: str, rows: list[tuple[str, int, str]]) -> int:
    folder = DATA / name
    with open(folder / "labels.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["image", "grade", "split"])
        writer.writerows(rows)

    counts = dict(sorted(Counter(grade for _, grade, _ in rows).items()))
    print(f"  {len(rows)} images, grades {counts}")
    expected = EXPECTED.get(name)
    if expected and counts != expected:
        print(f"  WARNING: published counts are {expected}. Do not trust this mirror.")
    return len(rows)


# ── one unpacker per dataset ─────────────────────────────────────────────────


def unpack_idrid(archive: Path) -> int:
    """The original release. Train and test reuse the same filenames
    (IDRiD_001 exists in both), so each is prefixed with its split."""
    images = DATA / "idrid" / "images"
    images.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, int, str]] = []

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        for split, folder, labels in (
            ("train", "a. Training Set", "a. IDRiD_Disease Grading_Training Labels.csv"),
            ("test", "b. Testing Set", "b. IDRiD_Disease Grading_Testing Labels.csv"),
        ):
            label_file = next(n for n in names if n.endswith(labels))
            text = zf.read(label_file).decode("utf-8-sig").splitlines()
            for record in csv.reader(text[1:]):
                if not record or not record[0].strip():
                    continue
                stem, grade = record[0].strip(), int(record[1])
                source = next(n for n in names if f"{folder}/{stem}." in n)
                target = f"{split}_{stem}{Path(source).suffix.lower()}"
                if not (images / target).exists():
                    (images / target).write_bytes(zf.read(source))
                rows.append((target, grade, split))

    return write_labels("idrid", rows)


def unpack_ddr(archive: Path) -> int:
    """One flat folder and one CSV, with the official split put back.

    Checked when this was written: all 12,522 images in the mirror appear in the
    official split files, and not one grade differs between the two. The split
    files also list 1,151 ungradable images (grade 5) that the mirror leaves
    out, which is why they name more files than the archive holds.
    """
    images = DATA / "ddr" / "images"
    images.mkdir(parents=True, exist_ok=True)

    split_of: dict[str, str] = {}
    for split in ("train", "valid", "test"):
        listing = RAW / "ddr_splits" / f"{split}.txt"
        download(DDR_SPLITS.format(split), listing)
        for line in listing.read_text().splitlines():
            if line.strip():
                split_of[line.split()[0]] = split

    rows: list[tuple[str, int, str]] = []
    with zipfile.ZipFile(archive) as zf:
        inside = {Path(n).name: n for n in zf.namelist() if n.lower().endswith(".jpg")}
        for record in csv.reader(zf.read("DR_grading.csv").decode().splitlines()[1:]):
            name, grade = record[0], int(record[1])
            if name not in split_of:
                print(f"  {name} is in no official split; left out")
                continue
            if not (images / name).exists():
                (images / name).write_bytes(zf.read(inside[name]))
            rows.append((name, grade, split_of[name]))

    return write_labels("ddr", rows)


def unpack_deepdrid(archive: Path) -> int:
    """The regular (non-widefield) photographs from the training and validation
    folders. The challenge's test labels ship as a spreadsheet and are left out
    rather than pulling in a spreadsheet reader for 400 images.

    Each row grades one eye, in whichever of the two eye columns is filled. A
    grade of 5 means the graders could not read the image, so there is no truth
    to score against and the row is dropped.
    """
    images = DATA / "deepdrid" / "images"
    images.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, int, str]] = []
    # DeepDRiD's graders also marked whether each photograph was good enough to
    # read, and called about half of them poor. Kept beside the labels, because
    # "how much worse is the model on a bad photograph" is a question an
    # underwriter looking at a blurry upload actually has.
    quality: list[tuple[str, str]] = []

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        for split, part in (("train", "training"), ("valid", "validation")):
            label_file = next(n for n in names if n.endswith(f"regular-fundus-{part}.csv"))
            text = zf.read(label_file).decode("utf-8-sig").splitlines()
            for record in csv.DictReader(text):
                grade = record["left_eye_DR_Level"] or record["right_eye_DR_Level"]
                if not grade or int(float(grade)) > 4:
                    continue
                stem = record["image_id"].strip()
                source = next((n for n in names if n.endswith(f"/{stem}.jpg")), None)
                if source is None:
                    print(f"  {stem} is labelled but has no image; left out")
                    continue
                target = f"{stem}.jpg"
                if not (images / target).exists():
                    (images / target).write_bytes(zf.read(source))
                rows.append((target, int(float(grade)), split))
                quality.append((target, record["Overall quality"].strip()))

    with open(DATA / "deepdrid" / "quality.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["image", "good"])
        writer.writerows(quality)

    return write_labels("deepdrid", rows)


def unpack_aptos(archive: Path) -> int:
    """The 3,662 labelled photographs, whatever folder the mirror put them in.

    The mirror re-split the competition's training set three ways and its CSVs
    do not line up with its folders, so labels are joined to images by id across
    all of them. The split is irrelevant here anyway: APTOS is only ever a test
    set, so every image is marked `test`. `write_labels` then checks the grade
    counts against the competition's own, which is what shows nothing was lost.
    """
    images = DATA / "aptos" / "images"
    images.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        inside = {Path(n).stem: n for n in names if n.lower().endswith((".png", ".jpg"))}

        grades: dict[str, int] = {}
        for label_file in (n for n in names if n.lower().endswith(".csv")):
            for record in csv.reader(zf.read(label_file).decode("utf-8-sig").splitlines()[1:]):
                if len(record) < 2 or record[0] not in inside:
                    continue
                if grades.setdefault(record[0], int(record[1])) != int(record[1]):
                    print(f"  {record[0]} is graded two ways by the mirror's own files")

        rows: list[tuple[str, int, str]] = []
        for stem, grade in sorted(grades.items()):
            target = f"{stem}{Path(inside[stem]).suffix.lower()}"
            if not (images / target).exists():
                (images / target).write_bytes(zf.read(inside[stem]))
            rows.append((target, grade, "test"))

    return write_labels("aptos", rows)


UNPACKERS = {
    "idrid": unpack_idrid,
    "ddr": unpack_ddr,
    "deepdrid": unpack_deepdrid,
    "aptos": unpack_aptos,
}


def main() -> int:
    requested = sys.argv[1:] or [*ARCHIVES, "models"]
    unknown = [r for r in requested if r not in ARCHIVES and r != "models"]
    if unknown:
        print(f"unknown: {', '.join(unknown)}\navailable: {', '.join(ARCHIVES)}, models")
        return 1

    print(f"data directory: {DATA}\n")
    problems = []

    for name in requested:
        print(f"{name}:")
        try:
            if name == "models":
                for filename, url in WEIGHTS.items():
                    download(url, MODELS / filename)
                    print(f"  {filename}  {(MODELS / filename).stat().st_size / 1e6:.0f} MB")
            else:
                archive = RAW / f"{name}.zip"
                download(ARCHIVES[name], archive)
                UNPACKERS[name](archive)
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            problems.append(name)
        print()

    if problems:
        print(f"failed: {', '.join(problems)} — re-run to resume")
        return 1
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
