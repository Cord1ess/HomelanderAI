"""The mortality arm: Phenotypic Age from a routine blood panel.

Three things matter. The published formula must be reproduced exactly, so the
constants are asserted against the paper. A value typed in the wrong unit must
be refused, not scored — albumin in g/L instead of g/dL would put an applicant
decades older with no error. And the arm must slot into the pipeline as a form
arm: it runs with no file at all, and never touches one.
"""

import json
import math

import pytest

from app.arms import ARMS, Arm, arm_for_intake, arms_for, form_arms
from app.arms import mortality as m
from app.evidence import EvidenceKind
from app.pipeline import STATUS_INSUFFICIENT, STATUS_SCORED, evaluate
from app.scoring import Thresholds

# A healthy adult's panel, in the units the form collects.
HEALTHY = {
    "albumin_g_dl": 4.4,
    "creatinine_mg_dl": 0.9,
    "glucose_mg_dl": 88.0,
    "crp_mg_l": 0.8,
    "lymphocyte_pct": 32.0,
    "mcv_fl": 89.0,
    "rdw_pct": 12.6,
    "alp_u_l": 65.0,
    "wbc_10e3_ul": 6.0,
}


# ── the published formula ────────────────────────────────────────────────────


def test_the_constants_are_levines():
    """Full-precision values from the BioAge reference implementation of the
    2019 correction. The denominator is 0.090165, not the 0.09165 that appears
    in one rendering of the correction — the two differ by 1-2 years."""
    spec = json.loads(m.MODEL_PATH.read_text())
    c = spec["coefficients"]
    assert c["intercept"] == -19.90667
    assert c["albumin_g_l"] == -0.03359355
    assert c["rdw_pct"] == 0.3306156
    assert c["age_years"] == 0.08035356
    assert spec["gompertz"]["age_slope"] == 0.090165
    assert spec["gompertz"]["age_intercept"] == 141.50225


def test_closed_form_equals_the_two_gompertz_steps():
    """The arm computes the affine closed form; the paper writes it as two
    fits back to back. They must agree wherever the two-step form is finite."""
    g = json.loads(m.MODEL_PATH.read_text())["gompertz"]
    for age in (25, 45, 70):
        xb = m.linear_predictor(age, HEALTHY)
        ten_year = m.ten_year_mortality(xb)
        inner = -g["age_scale"] * math.log(1 - ten_year)
        two_step = g["age_intercept"] + math.log(inner) / g["age_slope"]
        assert m.phenotypic_age(age, HEALTHY) == pytest.approx(two_step, abs=1e-6)


def test_units_are_converted_from_what_the_form_collects():
    """The paper's inputs are SI. The form collects what Bangladeshi labs print,
    so albumin g/dL, creatinine mg/dL, glucose mg/dL and CRP mg/L must each be
    converted; getting one wrong shifts the age by years, silently."""
    c = json.loads(m.MODEL_PATH.read_text())["coefficients"]
    base = m.linear_predictor(40, HEALTHY)
    # One more g/dL of albumin is ten g/L.
    assert m.linear_predictor(40, dict(HEALTHY, albumin_g_dl=5.4)) - base == pytest.approx(
        c["albumin_g_l"] * 10
    )
    # One more mg/dL of creatinine is 88.42 umol/L.
    assert m.linear_predictor(40, dict(HEALTHY, creatinine_mg_dl=1.9)) - base == pytest.approx(
        c["creatinine_umol_l"] * 88.42
    )
    # 18 more mg/dL of glucose is one mmol/L.
    assert m.linear_predictor(40, dict(HEALTHY, glucose_mg_dl=88.0 + 18.016)) - base == (
        pytest.approx(c["glucose_mmol_l"])
    )
    # CRP is logged in mg/dL: ten times the mg/L value adds ln(10) times the weight.
    assert m.linear_predictor(40, dict(HEALTHY, crp_mg_l=8.0)) - base == pytest.approx(
        c["ln_crp_mg_dl"] * math.log(10)
    )


def test_crp_below_detection_is_floored_not_logged_to_minus_infinity():
    assert math.isfinite(m.phenotypic_age(40, dict(HEALTHY, crp_mg_l=0.0)))
    assert m.phenotypic_age(40, dict(HEALTHY, crp_mg_l=0.0)) == m.phenotypic_age(
        40, dict(HEALTHY, crp_mg_l=0.1)
    )


def test_an_extreme_panel_does_not_crash_the_formula():
    """The two-step form takes log(0) here; the closed form does not."""
    extreme = dict(HEALTHY, crp_mg_l=400.0, wbc_10e3_ul=100.0, rdw_pct=35.0, glucose_mg_dl=700.0)
    assert math.isfinite(m.phenotypic_age(84, extreme))


def test_worse_markers_read_older():
    base = m.phenotypic_age(45, HEALTHY)
    assert m.phenotypic_age(45, dict(HEALTHY, rdw_pct=16.0)) > base
    assert m.phenotypic_age(45, dict(HEALTHY, crp_mg_l=20.0)) > base
    assert m.phenotypic_age(45, dict(HEALTHY, glucose_mg_dl=180.0)) > base
    assert m.phenotypic_age(45, dict(HEALTHY, albumin_g_dl=3.2)) > base
    assert m.phenotypic_age(45, dict(HEALTHY, lymphocyte_pct=15.0)) > base


def test_phenotypic_age_tracks_chronological_age():
    """The same panel at 30 and at 60 must read thirty years apart, up to the
    formula's own slope: the age term is 0.08035/0.090165 = 0.89 per year."""
    delta = m.phenotypic_age(60, HEALTHY) - m.phenotypic_age(30, HEALTHY)
    assert delta == pytest.approx(30 * 0.08035356 / 0.090165, abs=1e-6)


def test_contributions_explain_the_gap_exactly():
    """Each marker's years are its deviation from the reference; the closed
    form is affine, so swapping every marker to reference must land on the
    reference panel's own phenotypic age."""
    ref = json.loads(m.MODEL_PATH.read_text())["reference"]
    assert set(ref) == set(m.INPUTS), "run scripts/phenoage_experiment.py"
    panel = dict(HEALTHY, rdw_pct=15.5, glucose_mg_dl=140.0)
    parts = m.contributions(45, panel)
    assert set(parts) == set(m.INPUTS)
    assert sum(parts.values()) == pytest.approx(
        m.phenotypic_age(45, panel) - m.phenotypic_age(45, ref), abs=0.05
    )
    assert parts["rdw_pct"] > 5, "RDW carries the largest weight in the paper"


# ── the score ────────────────────────────────────────────────────────────────


def test_mortality_ratio_is_the_papers_hazard_per_year():
    assert m.mortality_ratio(0.0) == 1.0
    assert m.mortality_ratio(1.0) == pytest.approx(1.094, abs=0.001)
    assert m.mortality_ratio(-1.0) == pytest.approx(1 / 1.094, abs=0.001)


def test_the_score_anchors_the_tier_boundaries_to_insurance_ratios():
    """125% is the top of a standard class, 200% is senior review. They must
    sit exactly on the low/moderate and moderate/elevated cut-points."""
    t = Thresholds()
    assert m.score_from_ratio(m.STANDARD_MAX_RATIO) == t.low_max
    assert m.score_from_ratio(m.SENIOR_MIN_RATIO) == t.moderate_max
    assert m.score_from_ratio(1.0) < t.low_max
    assert m.score_from_ratio(1.5) > t.low_max
    assert m.score_from_ratio(0.1) == 0.0
    assert m.score_from_ratio(50.0) == 100.0
    # Monotone throughout.
    ratios = [0.5, 0.8, 1.0, 1.25, 1.6, 2.0, 3.0]
    scores = [m.score_from_ratio(r) for r in ratios]
    assert scores == sorted(scores)


def test_the_validation_travels_with_the_score():
    """The numbers were measured on NHANES by scripts/phenoage_experiment.py
    and the caveat has to reach the screen, not live in a document."""
    spec = json.loads(m.MODEL_PATH.read_text())
    numbers = spec["validation_numbers"]
    assert numbers["auc_phenotypic_age"] > numbers["auc_chronological_age"]
    assert numbers["auc_phenotypic_age"] > 0.85
    assert "NOT validated in South Asia" in m.VALIDATION
    assert m.run_form(HEALTHY, 45, "M").details["validation"] == m.VALIDATION


# ── the arm ──────────────────────────────────────────────────────────────────


def test_run_form_scores_a_healthy_panel_as_standard():
    result = m.run_form(HEALTHY, 45, "F")
    assert result.usable
    assert result.error is None
    assert result.score <= Thresholds().low_max
    d = result.details
    assert d["chronological_age"] == 45
    assert d["phenotypic_age"] < 45
    assert d["mortality_ratio"] < 1.0
    assert set(d["contributions"]) == set(m.INPUTS)
    assert len(d["input_hash"]) == 64


def test_an_abnormal_panel_escalates():
    result = m.run_form(
        dict(HEALTHY, rdw_pct=17.0, crp_mg_l=15.0, glucose_mg_dl=170.0, albumin_g_dl=3.4), 45, "M"
    )
    assert result.score > Thresholds().moderate_max
    assert result.details["mortality_ratio"] > m.SENIOR_MIN_RATIO


def test_the_same_input_hashes_the_same_and_a_changed_one_does_not():
    a = m.run_form(HEALTHY, 45, "M").details["input_hash"]
    b = m.run_form(dict(HEALTHY), 45, "M").details["input_hash"]
    c = m.run_form(dict(HEALTHY, rdw_pct=12.7), 45, "M").details["input_hash"]
    assert a == b != c


def test_a_wrong_unit_is_refused_not_scored():
    """Albumin 42 is g/L. Scored as g/dL it would add well over a century."""
    result = m.run_form(dict(HEALTHY, albumin_g_dl=42.0), 45, "M")
    assert not result.usable
    assert "albumin" in result.error and "unit" in result.error


def test_missing_values_are_named():
    partial = {k: v for k, v in HEALTHY.items() if k != "rdw_pct"}
    result = m.run_form(partial, 45, "M")
    assert not result.usable
    assert "red cell distribution width" in result.error
    assert not m.run_form({}, 45, "M").usable


def test_age_is_required_and_bounded():
    assert "date of birth" in m.run_form(HEALTHY, None, "M").error
    assert not m.run_form(HEALTHY, 12, "M").usable
    assert m.run_form(HEALTHY, 18, "M").usable
    assert m.run_form(HEALTHY, 100, "M").usable


# ── the registry seam ────────────────────────────────────────────────────────


def test_the_arm_is_a_form_arm_fed_by_the_blood_panel():
    arm = ARMS["mortality"]
    assert arm.arm_type == "tabular"
    assert arm.run is None and arm.run_form is m.run_form
    assert arm.accepts == frozenset()
    assert arm_for_intake("xgboost") is arm
    assert [a.name for a in form_arms()] == ["mortality"]
    # No evidence kind routes a file to it.
    for kind in EvidenceKind:
        assert arm not in arms_for(kind)


def test_an_arm_must_read_exactly_one_of_file_or_form():
    common = dict(
        name="x", version="1", arm_type="tabular", intake_id="x", accepts=frozenset(),
        preprocessing_version="v", weight_hash="h", validation="v", available=lambda: True,
    )
    with pytest.raises(ValueError):
        Arm(**common)
    with pytest.raises(ValueError):
        Arm(**common, run=lambda b: None, run_form=lambda d, a, s: None)
    with pytest.raises(ValueError):
        Arm(**dict(common, accepts=frozenset({EvidenceKind.FUNDUS})), run_form=lambda d, a, s: None)


# ── through the pipeline ─────────────────────────────────────────────────────


def test_the_pipeline_scores_a_blood_panel_with_no_file():
    result = evaluate([], HEALTHY, age=45, models_requested=["xgboost"])
    assert result.status == STATUS_SCORED
    assert [r.arm_name for r in result.runs] == ["mortality"]
    assert result.runs[0].evidence_hash == result.runs[0].result.details["input_hash"]
    assert result.tier == "low"


def test_the_form_arm_runs_only_when_its_panel_was_chosen():
    """A chest X-ray alone must not be told that nine blood values are missing."""
    result = evaluate([], HEALTHY, age=45)
    assert result.status == STATUS_INSUFFICIENT
    assert result.runs == []
    assert any("No readable evidence" in e for e in result.errors)


def test_a_form_arm_error_is_recorded_not_raised():
    result = evaluate([], {"albumin_g_dl": 4.4}, age=45, models_requested=["xgboost"])
    assert result.status == STATUS_INSUFFICIENT
    assert len(result.runs) == 1 and result.runs[0].failed
    assert any(e.startswith("mortality:") for e in result.errors)


def test_the_highest_reading_governs_across_arms():
    """An abnormal panel must not be averaged away by a clean film. The test
    fakes the chest arm so it runs without torch and with a known score."""
    from app.arms import tb_xray
    from app.intake import process_upload
    from tests.test_tb_xray import png

    class Fake:
        pass

    image = png()
    kinds = {process_upload(image, "chest.png").content_hash: EvidenceKind.CHEST_XRAY}
    abnormal = dict(HEALTHY, rdw_pct=17.0, crp_mg_l=15.0, glucose_mg_dl=170.0, albumin_g_dl=3.4)

    chest = ARMS["tb_xray"]
    calm = Arm(
        **{
            **{f: getattr(chest, f) for f in chest.__dataclass_fields__},
            "run": lambda b: m.ArmResult(score=5.0, raw_score=0.05),
            "available": lambda: True,
        }
    )
    original = ARMS["tb_xray"]
    ARMS["tb_xray"] = calm
    try:
        result = evaluate(
            [(image, "chest.png")], abnormal, age=45, kinds=kinds, models_requested=["xgboost"]
        )
    finally:
        ARMS["tb_xray"] = original
        assert tb_xray.NAME == "tb_xray"

    assert result.status == STATUS_SCORED
    assert {r.arm_name for r in result.runs} == {"tb_xray", "mortality"}
    assert result.crs >= m.run_form(abnormal, 45, "M").score
    assert result.tier == "elevated"


# ── end to end, against the database ─────────────────────────────────────────


def test_an_application_with_only_a_blood_panel_is_scored(carrier):
    """No file at all: the operator typed nine values and picked the panel.
    That used to be filed as insufficient evidence before scoring ever ran."""
    import asyncio
    import json as _json

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import needs_database
    from tests.test_applications import intake_payload, sign_in

    if needs_database.args[0]:
        pytest.skip(needs_database.kwargs["reason"])

    body = _json.loads(intake_payload())
    body["modelsRequested"] = ["xgboost"]
    body["declaredHistory"] = {"xgboost": {**HEALTHY, "height_cm": 170, "weight_kg": 68}}
    account = asyncio.run(carrier())

    with TestClient(app) as client:
        sign_in(client, account)
        response = client.post("/api/applications", data={"payload": _json.dumps(body)})
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["status"] == "submitted"

        detail = client.get(f"/api/applications/{created['id']}").json()

    assert detail["status"] == "scored", detail["errors"]
    assert detail["score"]["tier"] == "low"
    # The arm's own report reaches the review screen, and the vision-only
    # fields stay empty rather than being filled from the wrong arm.
    (run,) = detail["arms"]
    assert run["arm"] == "mortality" and run["armType"] == "tabular"
    assert run["details"]["chronological_age"] == 68  # born 1958-04-11
    assert run["details"]["phenotypic_age"] < 68
    assert detail["findings"] == [] and detail["modelInfo"] is None
    assert detail["score"]["visionScore"] is None
