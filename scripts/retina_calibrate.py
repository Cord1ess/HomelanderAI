"""Where the retina score's tier boundaries sit, set on eyes without referable DR.

    apps/api/.venv/Scripts/python.exe scripts/retina_calibrate.py

The retina model ranks well on the two sets its backbone never saw (AUC 0.946
IDRiD test, 0.950 DeepDRiD), but its probability is a poor score: the head was
fitted on DDR, and on other cameras an ordinary eye reads higher. Measured
before this script, 41-49% of eyes without referable retinopathy sat above the
low tier and 23-31% reached senior review.

As for the chest reader (scripts/tb_calibrate.py), the boundaries are placed
by what they should mean for an applicant without referable disease:

    score 30 (top of the low tier)  the 90th percentile of non-referable eyes
    score 65 (senior review)        the 98th percentile of non-referable eyes

linear in the logit, clamped. Set on the DeepDRiD photographs that
`validate_models.py retina` did not sample (disjoint from its 600), checked on
those 600 and on the IDRiD test split — another country and camera. The model
is unchanged. Writes `score_anchors` into `dr_fundus_model.json`.
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO / "scripts"))

from app.arms import dr_fundus  # noqa: E402
from app.arms.fundus import NotAFundusPhoto, frame  # noqa: E402
from app.intake import process_upload  # noqa: E402
from validate_models import DATA, OUT, set_last_key  # noqa: E402

CACHE = OUT / "retina_calibration_logits.json"


def logit_of(path: Path) -> float | None:
    from io import BytesIO

    from PIL import Image

    stored = process_upload(path.read_bytes(), path.name).data
    try:
        with Image.open(BytesIO(stored)) as image:
            framed = frame(image, dr_fundus.INPUT_SIZE)
    except NotAFundusPhoto:
        return None
    found, _ = dr_fundus._forward(dr_fundus._get_model(), dr_fundus.to_tensor(framed.image))
    p, _ = dr_fundus.predict(found)
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def main() -> int:
    rows = list(csv.DictReader((DATA / "dr" / "deepdrid" / "labels.csv").open()))
    tested = json.loads((OUT / "retina_deepdrid_scores.json").read_text())
    calibration = [r for r in rows if r["image"] not in tested and int(r["grade"]) < 2]
    print(f"calibration: {len(calibration)} non-referable DeepDRiD photos not in the test sample")

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for i, r in enumerate(calibration, 1):
        if r["image"] not in cache:
            cache[r["image"]] = logit_of(DATA / "dr" / "deepdrid" / "images" / r["image"])
        if i % 50 == 0:
            CACHE.write_text(json.dumps(cache))
            print(f"  {i}/{len(calibration)}", flush=True)
    CACHE.write_text(json.dumps(cache))

    values = np.array([cache[r["image"]] for r in calibration if cache[r["image"]] is not None])
    low, senior = float(np.percentile(values, 90)), float(np.percentile(values, 98))
    print(f"anchors: logit {low:.3f} -> 30, logit {senior:.3f} -> 65")

    def check(name: str, labels_csv: Path, scores_json: Path, split: str | None) -> dict:
        truth = {
            r["image"]: int(r["grade"]) >= 2
            for r in csv.DictReader(labels_csv.open())
            if split is None or r["split"] == split
        }
        scored = json.loads(scores_json.read_text())
        keys = [k for k in scored if k in truth and scored[k]["score"] is not None]
        p = np.array([scored[k]["score"] / 100.0 for k in keys])
        y = np.array([truth[k] for k in keys])
        out = {}
        for label, old_cut, logit in (("30", 0.30, low), ("65", 0.65, senior)):
            new_cut = 1 / (1 + math.exp(-logit))
            out[f">{label}"] = {
                "before": {
                    "sensitivity": round(float((p > old_cut)[y].mean()), 3),
                    "specificity": round(float((p <= old_cut)[~y].mean()), 3),
                },
                "after": {
                    "sensitivity": round(float((p > new_cut)[y].mean()), 3),
                    "specificity": round(float((p <= new_cut)[~y].mean()), 3),
                },
            }
        print(name, json.dumps(out))
        return out

    checked = {
        "deepdrid_test_600": check(
            "DeepDRiD test 600",
            DATA / "dr" / "deepdrid" / "labels.csv",
            OUT / "retina_deepdrid_scores.json",
            None,
        ),
        "idrid_test": check(
            "IDRiD test",
            DATA / "dr" / "idrid" / "labels.csv",
            OUT / "retina_idrid_scores.json",
            "test",
        ),
    }
    anchors = {
        "logit_low_tier_top": round(low, 4),
        "logit_senior_review": round(senior, 4),
        "set_on": (
            f"DeepDRiD, {len(values)} non-referable photographs not in the test sample: "
            "90th and 98th percentiles"
        ),
        "checked_on": checked,
    }
    set_last_key(dr_fundus.MODEL_PATH, "score_anchors", anchors)
    print(f"wrote score_anchors to {dr_fundus.MODEL_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
