"""The mortality arm's survival model: boosted Cox trees walked without xgboost.

Two properties matter. The exported trees must be evaluated exactly as XGBoost
would — the experiment checks that against xgboost before writing the file,
and here the walk itself is pinned with a hand-built tree. And the ratio the
arm reports must be about the values entered, never about what was left out:
a peer measured on the same things, nothing else.
"""

import json
import math

import pytest

from app.arms import mortality as m
from app.arms import survival_forest as sf
from tests.test_mortality import HEALTHY

needs_model = pytest.mark.skipif(
    not sf.MODEL_PATH.exists(), reason="run scripts/survival_experiment.py"
)

LIFESTYLE = {
    "height_cm": 170.0,
    "weight_kg": 68.0,
    "smoker": False,
    "alcohol": "None",
    "activity": "Moderate",
    "sbp_mmhg": 118.0,
}

# One tree, drawn by hand: split on age at 50 (missing goes right), then on
# smoker at 0.5 for the old branch.
#   node0: age < 50 -> node1 (leaf 0.1) else node2
#   node2: smoker < 0.5 -> node3 (leaf 0.5) else node4 (leaf 0.9); missing -> node4
HAND_TREE = [
    {"f": sf.FEATURES.index("age"), "t": 50.0, "yes": 1, "no": 2, "missing": 2},
    {"leaf": 0.1},
    {"f": sf.FEATURES.index("smoker"), "t": 0.5, "yes": 3, "no": 4, "missing": 4},
    {"leaf": 0.5},
    {"leaf": 0.9},
]


def test_the_walk_follows_splits_and_default_directions():
    young = sf.row_from({"age": 30, "smoker": 0.0})
    old_nonsmoker = sf.row_from({"age": 60, "smoker": 0.0})
    old_smoker = sf.row_from({"age": 60, "smoker": 1.0})
    old_unknown = sf.row_from({"age": 60})
    no_age = sf.row_from({"smoker": 0.0})
    assert sf.margin_of([HAND_TREE], young) == 0.1
    assert sf.margin_of([HAND_TREE], old_nonsmoker) == 0.5
    assert sf.margin_of([HAND_TREE], old_smoker) == 0.9
    assert sf.margin_of([HAND_TREE], old_unknown) == 0.9
    # No age: the root's default is right, then the smoker split decides.
    assert sf.margin_of([HAND_TREE], no_age) == 0.5
    # Two trees add.
    assert sf.margin_of([HAND_TREE, HAND_TREE], young) == pytest.approx(0.2)


def test_a_value_equal_to_the_threshold_goes_right_in_float32():
    """XGBoost compares in float32; 50.0 is not below 50.0, and neither is a
    float64 value that rounds to the threshold in float32."""
    on_threshold = sf.row_from({"age": 50.0, "smoker": 0.0})
    assert sf.margin_of([HAND_TREE], on_threshold) == 0.5
    split = {"f": 0, "t": 1.2000000476837158, "yes": 1, "no": 2, "missing": 2}
    tree = [split, {"leaf": -1.0}, {"leaf": 1.0}]
    assert sf.margin_of([tree], [1.2]) == 1.0


def test_age_bands_cover_18_to_84():
    assert sf.band_for(18) == "18-22"
    assert sf.band_for(22) == "18-22"
    assert sf.band_for(23) == "23-27"
    assert sf.band_for(45) == "43-47"
    assert sf.band_for(83) == "83-84"
    assert sf.band_for(84) == "83-84"
    assert sf.band_for(100) == "83-84"


@needs_model
def test_the_export_carries_its_validation_and_beats_age_and_sex():
    spec = json.loads(sf.MODEL_PATH.read_text())
    numbers = spec["validation_numbers"]
    assert numbers["c_index_model"] > numbers["c_index_age_sex"] > 0.5
    assert numbers["auc_5_year_model"] > numbers["auc_5_year_age"]
    assert "NOT validated in South Asia" in spec["validation"]
    assert spec["features"] == sf.FEATURES
    assert len(spec["trees"]) == spec["params"]["num_boost_round"]
    for sex in ("M", "F"):
        assert sf.band_for(45) in spec["reference_profiles"][sex]


@needs_model
def test_the_peer_is_measured_on_the_same_things():
    """An applicant with no blood tests must not be charged for the tests a
    typical peer had. Missing is not neutral in these trees."""
    spec = sf.load()
    peer_full = sf.peer_profile(spec, 45, "M", {**HEALTHY, "sbp_mmhg": 118})
    peer_bare = sf.peer_profile(spec, 45, "M", {"sbp_mmhg": 118})
    assert "rdw_pct" in peer_full and "rdw_pct" not in peer_bare
    assert "sbp_mmhg" in peer_bare
    assert peer_bare["age"] == 45 and peer_bare["male"] == 1.0
    # Entering nothing beyond age and sex leaves applicant and peer identical.
    assert sf.hazard_ratio_vs_peer(spec, {}, 45, "M") == pytest.approx(1.0)


@needs_model
def test_the_model_reads_what_the_form_says():
    baseline = m.run_form(LIFESTYLE, 45, "Male")
    assert baseline.usable
    assert baseline.details["governing"] == "survival_model"
    assert baseline.details["phenotypic"] is None
    assert baseline.details["survival"]["inputs_used"] == sorted(
        ["height_cm", "weight_kg", "smoker", "alcohol", "activity", "sbp_mmhg"]
    )

    smoker = m.run_form({**LIFESTYLE, "smoker": True}, 45, "Male")
    sedentary = m.run_form({**LIFESTYLE, "activity": "Sedentary"}, 45, "Male")
    hypertensive = m.run_form({**LIFESTYLE, "sbp_mmhg": 165}, 45, "Male")
    for worse in (smoker, sedentary, hypertensive):
        assert worse.details["mortality_ratio"] > baseline.details["mortality_ratio"]
    assert smoker.details["survival"]["factors"]["smoker"] > 1.3


@needs_model
def test_both_readings_are_given_and_the_higher_governs():
    result = m.run_form({**HEALTHY, **LIFESTYLE}, 45, "Female")
    ratios = result.details["ratios"]
    assert set(ratios) == {"phenotypic_age", "survival_model"}
    assert result.details["mortality_ratio"] == max(ratios.values())
    assert result.details["governing"] == max(ratios, key=lambda k: ratios[k])
    assert result.raw_score == pytest.approx(max(ratios.values()), abs=0.001)


@needs_model
def test_a_wrong_unit_withholds_both_readings():
    result = m.run_form({**HEALTHY, **LIFESTYLE, "creatinine_mg_dl": 80.0}, 45, "M")
    assert not result.usable
    assert "check the unit" in result.error


@needs_model
def test_the_survival_reading_needs_a_sex():
    result = m.run_form(LIFESTYLE, 45, "Prefer not to say")
    assert not result.usable
    assert "sex" in result.error
    # With the full panel the published formula still scores, sex or no sex.
    assert m.run_form({**HEALTHY, **LIFESTYLE}, 45, "Prefer not to say").usable


@needs_model
def test_factors_are_hazard_ratios_against_the_peers_value():
    spec = sf.load()
    values = {**LIFESTYLE, "smoker": 1.0, "alcohol": 0.0, "activity": 2.0}
    factors = sf.contributions(spec, values, 45, "M")
    assert set(factors) <= set(sf.FEATURES) - {"age", "male"}
    assert all(f > 0 for f in factors.values())
    # Swapping the smoker flag to the peer's value must reproduce the factor.
    peer = sf.peer_profile(spec, 45, "M", values)
    own = sf.margin_of(spec["trees"], sf.row_from({**values, "age": 45, "male": 1.0}))
    as_peer = {**values, "smoker": peer["smoker"], "age": 45, "male": 1.0}
    swapped = sf.margin_of(spec["trees"], sf.row_from(as_peer))
    assert factors["smoker"] == pytest.approx(math.exp(own - swapped), abs=0.001)
