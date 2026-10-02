"""Download the Mirai authors' own demo exam, the reference for the real-model tests.

    python scripts/fetch_mirai_demo.py

Four "For Presentation" views (GE Senographe Essential) released with
reginabarzilaygroup/Mirai v0.14.1, about 21 MB. Public, no account. The
authors' documentation publishes what Mirai returns for this exam —

    Year 1 0.0298   Year 2 0.0483   Year 3 0.0684   Year 4 0.09   Year 5 0.1016

— so running it is a correctness check of the whole path, not just a sign that
the container answers. `tests/test_mirai.py` does exactly that.

Lands in data/mirai/demo, which is gitignored (medical images are never
committed — docs/SPEC.md §9).
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://github.com/reginabarzilaygroup/Mirai/releases/download/v0.14.1/mirai_demo_data.zip"
OUT = Path(__file__).resolve().parents[1] / "data" / "mirai" / "demo"
EXPECTED = {"ccl1.dcm", "ccr1.dcm", "mlol2.dcm", "mlor2.dcm"}


def main() -> int:
    if OUT.is_dir() and {f.name for f in OUT.glob("*.dcm")} >= EXPECTED:
        print(f"already present: {OUT}")
        return 0

    print(f"downloading {URL}")
    with urllib.request.urlopen(URL, timeout=300) as response:
        archive = response.read()
    print(f"  {len(archive) / 1048576:.1f} MB")

    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = {Path(n).name for n in z.namelist() if n.endswith(".dcm")}
        if names != EXPECTED:
            print(f"unexpected contents: {sorted(names)}")
            return 1
        for member in z.namelist():
            if member.endswith(".dcm"):
                (OUT / Path(member).name).write_bytes(z.read(member))

    print(f"wrote {len(EXPECTED)} views to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
