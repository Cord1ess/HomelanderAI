"""Download the Shenzhen and Montgomery TB chest X-ray datasets.

    python scripts/fetch_tb_data.py                # both
    python scripts/fetch_tb_data.py shenzhen       # just one

Both are public NLM datasets — no account, no licence agreement.

Why these two and not the Kaggle TB database:

  Kaggle's set is stitched from three sources and the classes are split across
  them: 87% of its Normal images come from RSNA while its TB images do not. A
  model can separate the classes on scanner characteristics instead of lungs.
  Shenzhen and Montgomery are each from a single site, so that shortcut does
  not exist.

  Kaggle's "NLM" portion also appears to *be* Shenzhen (both are 336 TB
  images), so training on Shenzhen and testing on Kaggle would be testing on
  the training set.

Where the files come from:

  Shenzhen    Hugging Face mirror, as individual PNGs so they can be fetched in
              parallel. The original NLM host serves at ~0.16 MB/s (a 13-hour
              download); the mirror runs at ~2.5 MB/s per connection.
  Montgomery  Only available from the slow NLM host, but it is 588 MB rather
              than 3.6 GB. Expect roughly an hour; it is the external test set,
              so it is not needed to get a first result.

Labels live in the filename: the digit before `.png` is 0 for normal, 1 for TB.
    CHNCXR_0001_0.png  -> normal        MCUCXR_0001_1.png  -> TB

Everything lands in `data/`, which is gitignored. Never commit these images.
"""

import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
RAW = DATA / "raw"

HF_REPO = "Famatsu123/montgomery-shenzhen-tuberculosis-cxr"
HF_TREE = f"https://huggingface.co/api/datasets/{HF_REPO}/tree/main?recursive=true"
HF_FILE = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/"

MONTGOMERY_ZIP = "https://openi.nlm.nih.gov/imgs/collections/NLM-MontgomeryCXRSet.zip"

HEADERS = {"User-Agent": "Mozilla/5.0"}
PARALLEL = 8


def get(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


# ── Shenzhen: parallel PNGs from the Hugging Face mirror ─────────────────────


def fetch_shenzhen() -> int:
    destination = DATA / "shenzhen"
    destination.mkdir(parents=True, exist_ok=True)

    print("shenzhen:")
    print("  listing mirror ...")
    tree = json.loads(get(HF_TREE, timeout=90))
    wanted = [
        entry["path"]
        for entry in tree
        if entry.get("type") == "file"
        and "/CXR_png/" in entry["path"]
        and entry["path"].endswith(".png")
    ]

    todo = [p for p in wanted if not (destination / Path(p).name).exists()]
    have = len(wanted) - len(todo)
    print(f"  {len(wanted)} images; {have} already present, {len(todo)} to fetch")
    if not todo:
        return len(wanted)

    done = have
    failed: list[str] = []

    def fetch_one(path: str) -> tuple[str, bool]:
        target = destination / Path(path).name
        try:
            # .part then rename, so an interrupted run never leaves a truncated
            # file that the next run would skip as "already present".
            partial = target.with_suffix(".part")
            partial.write_bytes(get(HF_FILE + path))
            partial.replace(target)
            return path, True
        except Exception:
            return path, False

    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = [pool.submit(fetch_one, p) for p in todo]
        for future in as_completed(futures):
            path, ok = future.result()
            done += 1
            if not ok:
                failed.append(path)
            if done % 25 == 0 or done == len(wanted):
                print(f"    {done}/{len(wanted)}")

    if failed:
        print(f"  {len(failed)} failed — re-run to retry them")

    return len(list(destination.glob("*.png")))


# ── Montgomery: single zip from the slow NLM host ────────────────────────────


def _curl_download(url: str, target: Path) -> None:
    """Download via curl, with a check that we actually got a ZIP.

    openi.nlm.nih.gov throttles: after a handful of requests it starts
    returning a 13 KB HTML error page with `200 OK` and `Content-Type:
    text/html` instead of the file. Nothing in the status code reveals this, so
    the magic bytes are checked explicitly — otherwise the failure surfaces
    much later as a confusing "not a zip file" during extraction.

    If this raises, wait a while and re-run. The limit appears to be
    time-based rather than permanent.
    """
    if not shutil.which("curl"):
        raise RuntimeError(
            f"curl not found. Download {url} manually to {target}"
        )

    partial = target.with_suffix(".part")
    result = subprocess.run(  # noqa: S603
        ["curl", "-sL", "--fail", "--max-time", "7200", "-A", "Mozilla/5.0",
         "-o", str(partial), url],
        check=False,
    )
    if result.returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"curl failed with exit code {result.returncode}")

    # Read and close before deciding — Windows refuses to unlink an open file,
    # which turns a clear "server threw us an error page" into an opaque
    # PermissionError.
    with open(partial, "rb") as handle:
        magic = handle.read(2)

    if magic != b"PK":
        size = partial.stat().st_size
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"server returned {size} bytes of HTML, not a ZIP — it is rate-limiting. "
            "Wait a few minutes and re-run: python scripts/fetch_tb_data.py montgomery"
        )

    partial.replace(target)


def fetch_montgomery() -> int:
    destination = DATA / "montgomery"
    destination.mkdir(parents=True, exist_ok=True)

    existing = list(destination.glob("*.png"))
    if existing:
        print(f"montgomery:\n  already extracted ({len(existing)} images)")
        return len(existing)

    print("montgomery:")
    archive = RAW / "NLM-MontgomeryCXRSet.zip"
    if not (archive.exists() and archive.stat().st_size > 1_000_000):
        archive.parent.mkdir(parents=True, exist_ok=True)
        print("  downloading 588 MB from the slow NLM host (expect ~1 hour) ...")
        _curl_download(MONTGOMERY_ZIP, archive)

    count = 0
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if "/CXR_png/" not in name or not name.lower().endswith(".png"):
                continue
            with zf.open(name) as src:
                (destination / Path(name).name).write_bytes(src.read())
            count += 1
    print(f"  extracted {count} images")
    return count


DATASETS = {
    "shenzhen": (fetch_shenzhen, 662),
    "montgomery": (fetch_montgomery, 138),
}


def main() -> int:
    requested = sys.argv[1:] or list(DATASETS)
    unknown = [name for name in requested if name not in DATASETS]
    if unknown:
        print(f"unknown dataset(s): {', '.join(unknown)}")
        print(f"available: {', '.join(DATASETS)}")
        return 1

    print(f"data directory: {DATA}\n")
    problems = []

    for name in requested:
        fetch, expected = DATASETS[name]
        try:
            count = fetch()
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            problems.append(name)
            continue
        if count != expected:
            print(f"  WARNING: expected {expected} images, found {count}")
        print()

    if problems:
        print(f"failed: {', '.join(problems)} — re-run to retry")
        return 1

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
