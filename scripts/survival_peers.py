"""Real peers for the survival model's comparison, written into its JSON.

    apps/api/.venv/Scripts/python.exe scripts/survival_peers.py

The arm reports a hazard ratio against a typical person of the same age and
sex. It used to build that person from the median of each value separately —
and a person who is median on seventeen things at once is far healthier than
the median person, because risk rises faster above the median than it falls
below it. Measured on NHANES 2011-2018, the people the model was never
trained on, the median ratio came out at 2.2 instead of 1, and 56% of
ordinary adults were sent to senior review.

The fix compares against real people. For each sex and five-year band this
stores 150 training-set adults (NHANES 1999-2010, public-use data); the arm
holds the applicant's age and sex, hides whatever the applicant did not enter,
and takes the median risk of those 150 as the peer's. The trees are not
touched. The script prints the ratio's median on the held-out cycles before
and after, so the fix is measured, not assumed.
"""

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO / "scripts"))

import survival_experiment as se  # noqa: E402

from app.arms import survival_forest  # noqa: E402

PER_BAND = 150
SEED = 7


def main() -> int:
    df = se.load()
    train = df[df.cycle.isin(se.TRAIN_CYCLES)]
    test = df[df.cycle.isin(se.TEST_CYCLES)]
    measured = [f for f in survival_forest.FEATURES if f not in ("age", "male")]

    samples: dict[str, dict[str, list]] = {"M": {}, "F": {}}
    for sex, male in (("M", 1.0), ("F", 0.0)):
        for lo in range(18, 85, 5):
            hi = min(lo + 4, 84)
            band = train[(train.male == male) & (train.age >= lo) & (train.age <= hi)]
            pick = band.sample(min(PER_BAND, len(band)), random_state=SEED)
            samples[sex][f"{lo}-{hi}"] = [
                [None if v != v else round(float(v), 3) for v in row]
                for row in pick[measured].itertuples(index=False)
            ]

    spec = json.loads(survival_forest.MODEL_PATH.read_text())

    def ratios(spec_now, people) -> np.ndarray:
        out = []
        for r in people.itertuples():
            values = {f: getattr(r, f) for f in measured if getattr(r, f) == getattr(r, f)}
            sex = "M" if r.male else "F"
            out.append(survival_forest.hazard_ratio_vs_peer(spec_now, values, r.age, sex))
        return np.array(out)

    check = test.sample(800, random_state=SEED)
    before = ratios({k: v for k, v in spec.items() if k != "peer_samples"}, check)
    spec["peer_samples"] = {"features": measured, "per_band": PER_BAND, "rows": samples}
    after = ratios(spec, check)
    for name, r in (("before (median-of-each-value peer)", before), ("after (real peers)", after)):
        print(
            f"{name:36} median ratio {np.median(r):.2f}   share <= 1.25 {np.mean(r <= 1.25):.2f}"
            f"   share >= 2.0 {np.mean(r >= 2.0):.2f}"
        )
    # Leave out what the arm caches on a loaded spec (the trees as arrays).
    public = {k: v for k, v in spec.items() if not k.startswith("_")}
    # Bytes, not text: on Windows write_text would end the file in CRLF.
    text = json.dumps(public, separators=(",", ":")) + "\n"
    survival_forest.MODEL_PATH.write_bytes(text.encode("utf-8"))
    print(f"wrote {sum(len(b) for s in samples.values() for b in s.values())} peers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
