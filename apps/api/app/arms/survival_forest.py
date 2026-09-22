"""Walk the mortality arm's gradient-boosted Cox trees without xgboost.

`scripts/survival_experiment.py` trains the model and exports every tree as a
flat list of nodes, checked against XGBoost's own predictions before it is
written. This module is the other half: it reads that JSON and evaluates it
with plain Python, so scoring an applicant needs no machine-learning library —
the same rule the chest arm follows with its logistic regression.

A boosted Cox model's output is a log-hazard up to a constant. Only differences
are meaningful, and the arm only ever reports differences: the applicant
against a typical peer of the same age and sex (the training-set median
profile for that band), and each entered value against the peer's value. The
constant cancels out of both.
"""

import json
import math
from pathlib import Path

import numpy as np

# The intake form's keys, in the column order the trees were trained on. Age
# and sex are always present; everything else may be missing, and a missing
# value follows each split's learned default direction.
FEATURES: list[str] = [
    "age",
    "male",
    "height_cm",
    "weight_kg",
    "smoker",
    "alcohol",
    "activity",
    "sbp_mmhg",
    "albumin_g_dl",
    "creatinine_mg_dl",
    "glucose_mg_dl",
    "crp_mg_l",
    "lymphocyte_pct",
    "mcv_fl",
    "rdw_pct",
    "alp_u_l",
    "wbc_10e3_ul",
    "ast_u_l",
    "alt_u_l",
    "platelets_10e3_ul",
]

# How the form's words map onto the ordinal features the model was trained on.
ALCOHOL = {"none": 0.0, "occasionally": 1.0, "regularly": 2.0}
ACTIVITY = {"sedentary": 0.0, "light": 1.0, "moderate": 2.0, "active": 3.0}

MODEL_PATH = Path(__file__).with_name("survival_model.json")


def load() -> dict | None:
    """The exported model, or None until the experiment has been run."""
    if not MODEL_PATH.exists():
        return None
    return json.loads(MODEL_PATH.read_text())


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def margin_of(trees: list[list[dict]], row) -> float:
    """Sum of leaf values over every tree, for one row in FEATURES order.

    Each split sends the row left ("yes") when the value is below the
    threshold, right otherwise, and down the learned default branch when the
    value is missing — the same rule XGBoost applies. The comparison is made
    in float32, because that is the precision the thresholds were learned at:
    a value that equals a threshold in float32 must not be "below" it here.
    """
    total = 0.0
    for nodes in trees:
        node = nodes[0]
        while "leaf" not in node:
            value = row[node["f"]]
            if _is_missing(value):
                node = nodes[node["missing"]]
            elif np.float32(value) < np.float32(node["t"]):
                node = nodes[node["yes"]]
            else:
                node = nodes[node["no"]]
        total += node["leaf"]
    return total


def row_from(values: dict) -> list:
    """FEATURES-ordered list from a dict of form keys; absent keys are missing."""
    return [values.get(name) for name in FEATURES]


def band_for(age: float) -> str:
    lo = 18 + 5 * int((min(max(age, 18), 84) - 18) // 5)
    return f"{lo}-{min(lo + 4, 84)}"


def peer_profile(spec: dict, age: float, sex: str, measured: dict) -> dict:
    """The typical person of this age and sex, measured on the same things.

    Medians over the five-year band, but only for the values the applicant
    actually entered; everything else is missing for the peer too. Missing is
    not neutral in these trees — in NHANES the people who skipped the blood
    draw died sooner, and the model learned that — so a peer with a full
    panel beside an applicant with none would charge the applicant for what
    was never measured. Matching the pattern makes the ratio about the values.
    """
    medians = spec["reference_profiles"][sex][band_for(age)]
    peer = {name: medians[name] for name in medians if not _is_missing(measured.get(name))}
    return {**peer, "age": age, "male": 1.0 if sex == "M" else 0.0}


def hazard_ratio_vs_peer(spec: dict, values: dict, age: float, sex: str) -> float:
    trees = spec["trees"]
    own = margin_of(trees, row_from({**values, "age": age, "male": 1.0 if sex == "M" else 0.0}))
    peer = margin_of(trees, row_from(peer_profile(spec, age, sex, values)))
    return math.exp(own - peer)


def contributions(spec: dict, values: dict, age: float, sex: str) -> dict[str, float]:
    """For each value the applicant entered, the hazard factor it carries:
    the model's output with that value, over its output with the peer's value
    in its place. Above 1 raises the hazard; below 1 lowers it.

    One value at a time, holding the rest as entered. Trees interact, so the
    factors do not multiply to the total exactly; they are honest about what
    changing one number would do.
    """
    trees = spec["trees"]
    peer = peer_profile(spec, age, sex, values)
    own = {**values, "age": age, "male": peer["male"]}
    base = margin_of(trees, row_from(own))
    out: dict[str, float] = {}
    for name in FEATURES:
        if name in ("age", "male") or _is_missing(own.get(name)):
            continue
        swapped = margin_of(trees, row_from({**own, name: peer.get(name)}))
        out[name] = round(math.exp(base - swapped), 3)
    return out
