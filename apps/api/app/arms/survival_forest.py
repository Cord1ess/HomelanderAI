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


def peer_margin(spec: dict, values: dict, age: float, sex: str) -> float:
    """The typical peer's log-hazard: the median over real people of this sex
    and five-year band, held at the applicant's age, each measured on the same
    things the applicant entered (the rest hidden, as `peer_profile` explains).

    Not the log-hazard of a person who is median on every value. That person
    is far healthier than the median person — risk climbs faster above the
    median than it falls below it — and comparing against them put the median
    NHANES adult at 2.2 times "their peer" (scripts/survival_peers.py).
    """
    stored = spec.get("peer_samples")
    male = 1.0 if sex == "M" else 0.0
    if not stored:
        return margin_of(spec["trees"], row_from(peer_profile(spec, age, sex, values)))
    names = stored["features"]
    rows = np.array(stored["rows"][sex][band_for(age)], dtype=np.float64)  # None -> nan
    peers = np.full((len(rows), len(FEATURES)), np.nan)
    for j, name in enumerate(FEATURES):
        if name == "age":
            peers[:, j] = age
        elif name == "male":
            peers[:, j] = male
        elif not _is_missing(values.get(name)):
            peers[:, j] = rows[:, names.index(name)]
    return float(np.median(margins_of(spec, peers)))


def _tree_arrays(spec: dict) -> dict:
    """The trees as padded arrays, built once per loaded spec, so many rows
    can walk every tree together."""
    cached = spec.get("_arrays")
    if cached is not None:
        return cached
    trees = spec["trees"]
    width = max(len(t) for t in trees)
    shape = (len(trees), width)
    out = {
        "f": np.zeros(shape, np.int64),
        "t": np.zeros(shape, np.float32),
        "yes": np.zeros(shape, np.int64),
        "no": np.zeros(shape, np.int64),
        "missing": np.zeros(shape, np.int64),
        "leaf": np.ones(shape, bool),
        "value": np.zeros(shape, np.float64),
        "depth": 0,
    }
    for i, nodes in enumerate(trees):
        for k, node in enumerate(nodes):
            if "leaf" in node:
                out["value"][i, k] = node["leaf"]
            else:
                out["leaf"][i, k] = False
                out["f"][i, k], out["t"][i, k] = node["f"], node["t"]
                out["yes"][i, k], out["no"][i, k] = node["yes"], node["no"]
                out["missing"][i, k] = node["missing"]
    out["depth"] = int(spec.get("params", {}).get("max_depth", 6)) + 1
    spec["_arrays"] = out
    return out


def margins_of(spec: dict, matrix: np.ndarray) -> np.ndarray:
    """`margin_of` for many rows at once (rows x FEATURES, nan = missing):
    the same rule — below the float32 threshold goes left, missing takes the
    learned default — walked through every tree together."""
    a = _tree_arrays(spec)
    n_trees = a["f"].shape[0]
    tree = np.arange(n_trees)[:, None]
    node = np.zeros((n_trees, len(matrix)), np.int64)
    for _ in range(a["depth"]):
        leaf = a["leaf"][tree, node]
        if leaf.all():
            break
        value = matrix[np.arange(len(matrix))[None, :], a["f"][tree, node]]
        missing = np.isnan(value)
        with np.errstate(invalid="ignore"):
            below = value.astype(np.float32) < a["t"][tree, node]
        branch = np.where(below, a["yes"][tree, node], a["no"][tree, node])
        step = np.where(missing, a["missing"][tree, node], branch)
        node = np.where(leaf, node, step)
    return a["value"][tree, node].sum(axis=0)


def hazard_ratio_vs_peer(spec: dict, values: dict, age: float, sex: str) -> float:
    male = 1.0 if sex == "M" else 0.0
    own = margin_of(spec["trees"], row_from({**values, "age": age, "male": male}))
    return math.exp(own - peer_margin(spec, values, age, sex))


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
