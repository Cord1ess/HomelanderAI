"""Standard clinical readings from the blood panel.

Each is a published formula with fixed constants, so each is checked against a
value worked by hand from the source equation, and its category boundaries are
checked exactly. They inform the underwriter and never move the score.
"""

import pytest

from app.arms import mortality as m
from app.arms import panel_readings as pr
from tests.test_mortality import HEALTHY

# ── eGFR, CKD-EPI 2021 ───────────────────────────────────────────────────────


def test_egfr_matches_the_equation_worked_by_hand():
    """Creatinine 1.0 mg/dL at 50: men 142 x (1/0.9)^-1.2 x 0.9938^50 = 91.7;
    women 142 x (1/0.7)^-1.2 x 0.9938^50 x 1.012 = 68.6."""
    assert pr.egfr(1.0, 50, "M") == pytest.approx(91.7, abs=0.1)
    assert pr.egfr(1.0, 50, "F") == pytest.approx(68.6, abs=0.1)


def test_egfr_uses_the_low_creatinine_exponent_below_kappa():
    """Below kappa the ratio is raised to alpha, not to -1.2; the two branches
    must meet at the kink with no jump."""
    just_below = pr.egfr(0.9 - 1e-9, 40, "M")
    just_above = pr.egfr(0.9 + 1e-9, 40, "M")
    assert just_below == pytest.approx(just_above, rel=1e-6)
    assert pr.egfr(0.6, 40, "M") > pr.egfr(0.9, 40, "M")


def test_gfr_stages_are_kdigo():
    assert pr.gfr_stage(95)[0] == "G1"
    assert pr.gfr_stage(90)[0] == "G1"
    assert pr.gfr_stage(89.9)[0] == "G2"
    assert pr.gfr_stage(60)[0] == "G2"
    assert pr.gfr_stage(59.9)[0] == "G3a"
    assert pr.gfr_stage(45)[0] == "G3a"
    assert pr.gfr_stage(44.9)[0] == "G3b"
    assert pr.gfr_stage(30)[0] == "G3b"
    assert pr.gfr_stage(29.9)[0] == "G4"
    assert pr.gfr_stage(14.9)[0] == "G5"


# ── FIB-4 ────────────────────────────────────────────────────────────────────


def test_fib4_matches_the_formula():
    """60 x 40 / (150 x sqrt(30)) = 2.92."""
    assert pr.fib4(60, 40, 30, 150) == pytest.approx(2.921, abs=0.001)


def test_fib4_categories_and_the_over_65_cut_off():
    def category(age, value_target):
        # Choose AST so that the index lands on the requested value.
        ast = value_target * 200 * 25**0.5 / age
        values = {"ast_u_l": ast, "alt_u_l": 25, "platelets_10e3_ul": 200}
        return next(r for r in pr.readings(age, "M", values))

    assert category(50, 1.0)["category"] == "advanced fibrosis unlikely"
    assert category(50, 2.0)["category"] == "indeterminate"
    assert category(50, 3.0)["category"] == "advanced fibrosis likely"
    # Over 65 the lower cut-off rises to 2.0, so 1.8 is no longer indeterminate.
    assert category(70, 1.8)["category"] == "advanced fibrosis unlikely"
    assert category(70, 2.3)["category"] == "indeterminate"


# ── BMI and glucose ──────────────────────────────────────────────────────────


def test_bmi_uses_the_asian_cut_offs():
    assert pr.bmi(170, 68) == pytest.approx(23.53, abs=0.01)
    assert pr.bmi_category_asian(18.4) == "underweight"
    assert pr.bmi_category_asian(18.5) == "normal"
    assert pr.bmi_category_asian(22.9) == "normal"
    assert pr.bmi_category_asian(23.0) == "overweight"
    assert pr.bmi_category_asian(27.4) == "overweight"
    assert pr.bmi_category_asian(27.5) == "obese"


def test_glucose_categories_are_ada():
    assert pr.glucose_category(99.9) == "normal"
    assert pr.glucose_category(100) == "prediabetes range"
    assert pr.glucose_category(125.9) == "prediabetes range"
    assert pr.glucose_category(126) == "diabetes range"


# ── through the arm ──────────────────────────────────────────────────────────


def test_readings_ride_with_the_phenotypic_age_and_do_not_move_the_score():
    with_extras = dict(
        HEALTHY, ast_u_l=40, alt_u_l=30, platelets_10e3_ul=150, height_cm=170, weight_kg=68
    )
    plain = m.run_form(HEALTHY, 50, "Male")
    full = m.run_form(with_extras, 50, "Male")

    assert full.score == plain.score
    assert full.details["phenotypic_age"] == plain.details["phenotypic_age"]

    keys = [r["key"] for r in full.details["readings"]]
    assert keys == ["egfr", "fib4", "bmi", "glucose"]
    # Without the optional values only what the nine markers allow is read.
    assert [r["key"] for r in plain.details["readings"]] == ["egfr", "glucose"]


def test_a_reading_is_never_guessed():
    """No sex means no eGFR, since the equation has no third option; a missing
    platelet count means no FIB-4."""
    unsexed = m.run_form(HEALTHY, 50, "Prefer not to say").details["readings"]
    assert "egfr" not in [r["key"] for r in unsexed]
    partial = m.run_form(dict(HEALTHY, ast_u_l=40, alt_u_l=30), 50, "F").details["readings"]
    assert "fib4" not in [r["key"] for r in partial]


def test_sex_is_read_from_the_forms_wording():
    assert m.sex_code("Female") == "F"
    assert m.sex_code("male") == "M"
    assert m.sex_code(" M ") == "M"
    assert m.sex_code("Other") is None
    assert m.sex_code("Prefer not to say") is None
    assert m.sex_code(None) is None


def test_every_reading_explains_itself():
    full = dict(HEALTHY, ast_u_l=40, alt_u_l=30, platelets_10e3_ul=150, height_cm=170, weight_kg=68)
    for reading in m.run_form(full, 50, "F").details["readings"]:
        assert reading["note"].strip()
        assert reading["label"].strip()
        assert isinstance(reading["flag"], bool)
