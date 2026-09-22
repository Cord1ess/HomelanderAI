"""Download the two published ECG networks and convert them for the ECG arm.

    python scripts/fetch_ecg_models.py            # weights + port check + demo tracings
    python scripts/fetch_ecg_models.py weights    # just the two networks
    python scripts/fetch_ecg_models.py check      # re-run the port check
    python scripts/fetch_ecg_models.py demo       # just the demo CSVs

Needs the `vision` and `train` extras (torch, safetensors, h5py). Everything
lands in `data/ecg/`, which is gitignored: about 800 MB of downloads, once.

What it produces, and why each step exists:

  data/ecg/models/ecg_dx.safetensors
      Ribeiro et al. 2020, the six-abnormality classifier. Published as a
      Keras HDF5 file; the arm runs PyTorch, so the arrays are read with h5py
      and re-keyed for `app.arms.ecg_nets.EcgDx`. Converted, not retrained.
  data/ecg/models/ecg_age.safetensors + ecg_age_config.json
      Lima et al. 2021, ECG age. Published as a PyTorch pickle. Its hash is
      checked against the pin below before it is unpickled, and the tensors are
      re-saved as safetensors so the arm never unpickles anything at runtime.
  apps/api/app/arms/ecg_12lead_model.json
      The sha256 of each converted file is written back here, and the arm
      refuses to load a file that no longer matches.

The port check downloads the authors' public test set (CODE-test, 827
tracings) and compares the converted classifier's decisions with the ones the
authors published for the same tracings (`annotations/dnn.csv`). Anything
under 99% agreement on any class means the conversion is wrong, and the script
says so and exits non-zero rather than leaving a broken model in place.

The demo step writes a handful of CODE-test tracings out as CSV in the exact
form the intake accepts, one per abnormality plus normals, into
`data/ecg/demo/`. They are what to upload when showing the arm.

Sources (all CC-BY-4.0):
  classifier  https://zenodo.org/records/3765717
  age         https://zenodo.org/records/4892365
  test set    https://zenodo.org/records/3765780
"""

import csv
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

DATA = REPO_ROOT / "data" / "ecg"
RAW = DATA / "raw"
MODELS = DATA / "models"
DEMO = DATA / "demo"
SPEC_PATH = REPO_ROOT / "apps" / "api" / "app" / "arms" / "ecg_12lead_model.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}

ARCHIVES = {
    "dx": (
        "https://zenodo.org/records/3765717/files/model.zip?download=1",
        "fbecab655252a347ff8393205a2c38fb2a3ff212cb75a603b05227db79efe17f",
    ),
    "age": (
        "https://zenodo.org/records/4892365/files/model.zip?download=1",
        "ba28cd59963ab791e3eac1169717b373726eac2ef57e112ee7bbb353265e3ab1",
    ),
    "test": (
        "https://zenodo.org/records/3765780/files/data.zip?download=1",
        "00d32666adbdd9d34e028e84a4a627cdc2c970f3c794a52866f1c149ba58526f",
    ),
}

# Below this agreement with the authors' own decisions on any class, the
# conversion is wrong. Our port sits at 0.996-1.000.
MIN_AGREEMENT = 0.99


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(name: str) -> Path:
    """The archive on disk, verified. A wrong hash is deleted and reported."""
    url, expected = ARCHIVES[name]
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / f"{name}.zip"
    if target.exists() and sha256(target) == expected:
        return target
    print(f"downloading {name} <- {url}")
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    actual = sha256(target)
    if actual != expected:
        target.unlink()
        raise SystemExit(f"{name}.zip: sha256 {actual} does not match the pinned {expected}")
    return target


def extract(archive: Path, member: str) -> Path:
    """One member of the archive, extracted flat next to it."""
    out = RAW / archive.stem / Path(member).name
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zipped, zipped.open(member) as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return out


# ── weights ──────────────────────────────────────────────────────────────────


def convert_dx() -> Path:
    import h5py
    from safetensors.torch import save_file

    from app.arms import ecg_nets

    hdf5 = extract(download("dx"), "model/model.hdf5")
    arrays: dict[str, np.ndarray] = {}
    with h5py.File(hdf5, "r") as handle:
        layers = handle["model_weights"]
        for layer in layers.attrs["layer_names"]:
            layer = layer.decode() if isinstance(layer, bytes) else layer
            group = layers[layer]
            for weight in group.attrs["weight_names"]:
                weight = weight.decode() if isinstance(weight, bytes) else weight
                key = f"{layer}/{weight.split('/')[-1].replace(':0', '')}"
                arrays[key] = np.asarray(group[weight], dtype=np.float32)

    state = ecg_nets.dx_state_from_keras(arrays)
    model = ecg_nets.EcgDx()
    model.load_state_dict(state, strict=True)

    MODELS.mkdir(parents=True, exist_ok=True)
    out = MODELS / "ecg_dx.safetensors"
    save_file({k: v.contiguous() for k, v in model.state_dict().items()}, str(out))
    print(f"classifier -> {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def convert_age() -> Path:
    import torch
    from safetensors.torch import save_file

    from app.arms import ecg_nets

    archive = download("age")
    checkpoint = extract(archive, "model/model.pth")
    config = extract(archive, "model/config.json")

    # The archive's hash was verified in download(); only then is it unpickled.
    try:
        loaded = torch.load(checkpoint, map_location="cpu", weights_only=True)
    except Exception:
        loaded = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model = ecg_nets.age_net(json.loads(config.read_text()))
    model.load_state_dict(loaded["model"], strict=True)

    MODELS.mkdir(parents=True, exist_ok=True)
    out = MODELS / "ecg_age.safetensors"
    save_file({k: v.contiguous() for k, v in model.state_dict().items()}, str(out))
    shutil.copyfile(config, MODELS / "ecg_age_config.json")
    print(f"age model  -> {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def pin_hashes(dx: Path, age: Path) -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    spec["converted_weights"]["dx"]["sha256"] = sha256(dx)
    spec["converted_weights"]["age"]["sha256"] = sha256(age)
    SPEC_PATH.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"pinned both hashes in {SPEC_PATH.relative_to(REPO_ROOT)}")


# ── the port check, on the authors' test set ─────────────────────────────────


def test_set() -> tuple[np.ndarray, list[dict], np.ndarray, np.ndarray]:
    """CODE-test: tracings in the models' units (N, 12, 4096), attributes, the
    authors' decisions (N, 6) and the cardiologists' labels (N, 6)."""
    import h5py

    archive = download("test")
    tracings = extract(archive, "data/ecg_tracings.hdf5")
    attributes = extract(archive, "data/attributes.csv")
    theirs = extract(archive, "data/annotations/dnn.csv")
    gold = extract(archive, "data/annotations/gold_standard.csv")

    with h5py.File(tracings, "r") as handle:
        x = np.asarray(handle["tracings"], dtype=np.float32)  # (N, 4096, 12)
    x = np.ascontiguousarray(x.transpose(0, 2, 1))

    with attributes.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    classes = ("1dAVb", "RBBB", "LBBB", "SB", "AF", "ST")
    with theirs.open(encoding="utf-8") as handle:
        decisions = np.array(
            [[float(r[c]) for c in classes] for r in csv.DictReader(handle)], dtype=np.float32
        )
    with gold.open(encoding="utf-8") as handle:
        labels = np.array(
            [[float(r[c]) for c in classes] for r in csv.DictReader(handle)], dtype=np.float32
        )
    return x, rows, decisions, labels


def check() -> None:
    import torch

    from app.arms import ecg_12lead

    x, _, theirs, gold = test_set()
    models = ecg_12lead._load()
    ours = np.zeros((len(x), len(ecg_12lead.CLASSES)), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(x), 32):
            ours[start : start + 32] = models["dx"](torch.from_numpy(x[start : start + 32])).numpy()

    failed = False
    print(f"port check on CODE-test, n={len(x)}:")
    for j, name in enumerate(ecg_12lead.CLASSES):
        decided = ours[:, j] >= ecg_12lead.THRESHOLDS[name]
        agreement = float(np.mean(decided == (theirs[:, j] == 1)))
        positives = gold[:, j] == 1
        tp = float(np.sum(decided & positives))
        f1 = 2 * tp / max(1.0, decided.sum() + positives.sum())
        flag = "" if agreement >= MIN_AGREEMENT else "   <-- BELOW MINIMUM"
        print(
            f"  {name:6} agreement with the authors {agreement:.4f}"
            f"   F1 vs cardiologists {f1:.3f}{flag}"
        )
        failed = failed or agreement < MIN_AGREEMENT
    if failed:
        raise SystemExit("the converted classifier does not reproduce the authors' decisions")


# ── demo tracings ────────────────────────────────────────────────────────────


def demo() -> None:
    """A few test-set tracings as the CSV an ECG export looks like, one per
    abnormality where the cardiologists and the network agree, plus normals.
    The identifiers are row numbers in a public research set, not people."""
    from app import ecg

    x, rows, theirs, gold = test_set()
    classes = ("1dAVb", "RBBB", "LBBB", "SB", "AF", "ST")
    DEMO.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    def write(index: int, tag: str) -> None:
        mv = x[index] / ecg.MV_TO_MODEL  # back to millivolts
        name = f"{tag}_codetest_{index:03d}.csv"
        with (DEMO / name).open("w", newline="", encoding="utf-8") as handle:
            handle.write(f"# CODE-test tracing {index}, fs={ecg.SAMPLE_RATE}, millivolts\n")
            writer = csv.writer(handle)
            writer.writerow(["time", *ecg.LEADS])
            for t in range(mv.shape[1]):
                writer.writerow([f"{t / ecg.SAMPLE_RATE:.4f}", *(f"{v:.4f}" for v in mv[:, t])])
        manifest.append(
            {
                "file": name,
                "labelled": tag,
                "age": rows[index]["age"],
                "sex": rows[index]["sex"],
                "cardiologists": [c for j, c in enumerate(classes) if gold[index, j] == 1],
            }
        )

    for j, name in enumerate(classes):
        agreed = np.flatnonzero((gold[:, j] == 1) & (theirs[:, j] == 1))
        for index in agreed[:2]:
            write(int(index), name)
    normal = np.flatnonzero((gold.sum(axis=1) == 0) & (theirs.sum(axis=1) == 0))
    for index in normal[:3]:
        write(int(index), "normal")

    (DEMO / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest)} demo tracings to {DEMO.relative_to(REPO_ROOT)}")


def main(argv: list[str]) -> None:
    steps = set(argv) or {"weights", "check", "demo"}
    if "weights" in steps:
        pin_hashes(convert_dx(), convert_age())
    if "check" in steps:
        check()
    if "demo" in steps:
        demo()


if __name__ == "__main__":
    main(sys.argv[1:])
