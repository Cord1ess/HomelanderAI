"""Where the TB score's tier boundaries sit, set on films that are not TB.

NOT APPLIED. Run on TBX11K on 2026-10-03, the anchors fixed Montgomery's false
alarms but dropped Shenzhen's TB films above the low tier from 89% to 25%:
TBX11K's healthy films read too high to set boundaries for anyone else. Kept
for calibrating on local films; check any result on a second hospital (the
Shenzhen features in data/features_shenzhen.json are quick to score) before
writing anchors to the model file.

    apps/api/.venv/Scripts/python.exe scripts/tb_calibrate.py

The TB model ranks well on two hospitals it never saw (AUC 0.909 Montgomery,
0.907 TBX11K). Its probability is a poor score, though: it was fitted on
Shenzhen, where half the films are TB, so an ordinary film reads high.
Measured before this script: above the low-tier boundary (30) sat 71% of
Montgomery's normal films and 85% of TBX11K's healthy ones, and half of
TBX11K's healthy films reached senior review (65).

This places the boundaries by what they should mean for an applicant who
does not have TB:

    score 30 (top of the low tier)  the 90th percentile of non-TB films
    score 65 (senior review)        the 98th percentile of non-TB films

linear in the model's logit between and beyond them, clamped to 0-100 — the
same anchoring the mortality and mammogram readers use. The model itself is
unchanged; only where its answer lands on the tier scale.

Set on TBX11K's calibration draw (healthy and sick-but-not-TB films, disjoint
from the TBX11K test films — `validate_models.tbx11k_sets`), and checked on
Montgomery, which plays no part in setting them. Writes `score_anchors` into
`tb_xray_model.json`.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO / "scripts"))

from app.arms import tb_xray  # noqa: E402
from app.intake import process_upload  # noqa: E402
from validate_models import DATA, OUT, set_last_key, tbx11k_sets  # noqa: E402

CACHE = OUT / "tb_calibration_logits.json"


def logit_of(path: Path) -> float:
    """The TB model's logit for one film, through the intake path."""
    stored = process_upload(path.read_bytes(), path.name).data
    probability, _ = tb_xray.predict(tb_xray.findings(stored))
    probability = min(max(probability, 1e-9), 1 - 1e-9)
    return math.log(probability / (1 - probability))


def logits(items: list[tuple[str, Path]]) -> dict[str, float]:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for i, (key, path) in enumerate(items, 1):
        if key in cache:
            continue
        cache[key] = logit_of(path)
        if i % 50 == 0:
            OUT.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache))
            print(f"  {i}/{len(items)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache))
    return cache


def score(logit: float, low: float, senior: float) -> float:
    return max(0.0, min(100.0, 30.0 + 35.0 * (logit - low) / (senior - low)))


def main() -> int:
    _, calibration = tbx11k_sets()
    images = DATA / "tbx11k" / "images"
    present = [(f"tbx11k/{n}", images / n) for n in sorted(calibration) if (images / n).exists()]
    montgomery = [(f"montgomery/{p.name}", p) for p in sorted((DATA / "montgomery").glob("*.png"))]
    print(f"calibration films: {len(present)} of {len(calibration)}; Montgomery: {len(montgomery)}")
    found = logits(present + montgomery)

    non_tb = np.array([found[k] for k, _ in present])
    low, senior = float(np.percentile(non_tb, 90)), float(np.percentile(non_tb, 98))
    print(f"anchors: logit {low:.3f} -> 30, logit {senior:.3f} -> 65")

    labels = np.array([int(Path(k).stem.rsplit("_", 1)[1]) for k, _ in montgomery])
    old = np.array([100 / (1 + math.exp(-found[k])) for k, _ in montgomery])
    new = np.array([score(found[k], low, senior) for k, _ in montgomery])

    def cuts(scores):
        out = {}
        for cut in (30.0, 65.0):
            flagged = scores > cut
            out[f">{cut:g}"] = {
                "sensitivity": round(float(flagged[labels == 1].mean()), 3),
                "specificity": round(float((~flagged[labels == 0]).mean()), 3),
            }
        return out

    before, after = cuts(old), cuts(new)
    print("Montgomery, before:", before)
    print("Montgomery, after: ", after)

    anchors = {
        "logit_low_tier_top": round(low, 4),
        "logit_senior_review": round(senior, 4),
        "set_on": (
            f"TBX11K calibration draw, {len(present)} films without TB "
            f"({sum(calibration[Path(k).name] == 'healthy' for k, _ in present)} healthy, "
            f"{sum(calibration[Path(k).name] == 'sick_but_no_tb' for k, _ in present)} "
            "sick but not TB): 90th and 98th percentiles"
        ),
        "checked_on_montgomery": {"before": before, "after": after},
    }
    set_last_key(tb_xray.MODEL_PATH, "score_anchors", anchors)
    print(f"wrote score_anchors to {tb_xray.MODEL_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
