"""Mortality arm: how an applicant's routine blood panel compares with their age.

Every other arm screens for a disease. This one answers the question the
insurer is actually asking — is this person likely to die sooner than someone
their age — and it does so with a published formula rather than a model we
trained: **Phenotypic Age** (Levine et al. 2018). Nine markers from an ordinary
blood panel plus chronological age go into a Gompertz mortality model fitted on
NHANES III with real death records, and the output is expressed as an age: the
chronological age at which an average person would carry the same 10-year
mortality risk. Someone aged 45 with a phenotypic age of 53 has the blood
panel of a typical 53-year-old.

**What the score is.** The gap between phenotypic and chronological age turns
into a mortality ratio through the fitted Gompertz slope (`exp(0.090165 x gap)`,
about 1.09 per year — the hazard ratio the paper reports), and the ratio is
placed on the tier scale the way insurers already rate: a standard policy covers
up to roughly 125% of average mortality, table ratings run above that, and past
200% a senior underwriter looks. So 125% sits exactly on the low/moderate
boundary and 200% on the moderate/elevated one. The arm's score is relative to
a same-age peer; it is never an absolute probability of death, because US
baselines do not transfer to Bangladesh.

**What it is not.** Phenotypic Age was derived on US adults in 1988-94 and has
no South Asian validation. `scripts/phenoage_experiment.py` measures it on
NHANES 1999-2018 with this exact code and writes the numbers into
`mortality_model.json`; that string travels with every score. The population
caveat travels with it.

Pure arithmetic over a dict. No file, no torch: the arm reads the applicant's
declared answers, which is why it registers with `run_form` rather than `run`.
"""

import hashlib
import json
import math
from pathlib import Path

from app.arms import ArmResult, panel_readings
from app.audit import canonical
from app.scoring import Thresholds

NAME = "mortality"
VERSION = "1.0.0-phenoage"

MODEL_PATH = Path(__file__).with_name("mortality_model.json")
_SPEC: dict = json.loads(MODEL_PATH.read_text())

# The arm's inputs, in the units Bangladeshi laboratories print. Converted to
# the paper's SI units inside `phenotypic_age`, so the form never asks an
# operator to do arithmetic.
INPUTS: tuple[str, ...] = tuple(_SPEC["inputs"])
LABELS: dict[str, str] = dict(_SPEC["inputs"])

PREPROCESSING_VERSION = "phenoage-units-v1"
WEIGHT_HASH = (
    "levine2018+phenoage:sha256:" + hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:32]
)
VALIDATION: str = _SPEC["validation"]

_COEF = _SPEC["coefficients"]
_GOMPERTZ = _SPEC["gompertz"]
_PLAUSIBLE = _SPEC["plausible"]

# Where the mortality ratio lands on the tier scale. 125% is the conventional
# ceiling of a standard life-insurance class (substandard tables begin above
# it, each a further 25%); 200% is where an underwriter stops pricing and a
# senior one reviews. They are anchored to the default tier cut-points so the
# three tiers keep their meaning: standard, adjusted, senior review.
STANDARD_MAX_RATIO = 1.25
SENIOR_MIN_RATIO = 2.0

# CRP below the assay's detection limit is reported as "<0.1 mg/L" or 0. The log
# of zero is not a number, so the floor is the limit itself.
_CRP_FLOOR_MG_L = 0.1

# Optional values the same panel usually carries. They feed the standard
# readings (eGFR, FIB-4, BMI) beside the phenotypic age, never the score, so a
# missing one costs a line on the screen and nothing else.
OPTIONAL_INPUTS: tuple[str, ...] = (
    "ast_u_l",
    "alt_u_l",
    "platelets_10e3_ul",
    "height_cm",
    "weight_kg",
)


def available() -> bool:
    return True


def sex_code(sex: str | None) -> str | None:
    """The form's free-text sex ("Female", "male", "Prefer not to say") as
    F / M / None. The formulas that need it are sex-specific and have no
    third option, so anything else is honestly None."""
    first = (sex or "").strip().lower()[:1]
    return {"f": "F", "m": "M"}.get(first)


# ── the published formula ────────────────────────────────────────────────────


def linear_predictor(age: float, values: dict[str, float]) -> float:
    """Levine's `xb`, with unit conversion from what the form collects."""
    crp_mg_dl = max(values["crp_mg_l"], _CRP_FLOOR_MG_L) / 10.0
    return (
        _COEF["intercept"]
        + _COEF["albumin_g_l"] * values["albumin_g_dl"] * 10.0
        + _COEF["creatinine_umol_l"] * values["creatinine_mg_dl"] * 88.42
        + _COEF["glucose_mmol_l"] * values["glucose_mg_dl"] / 18.016
        + _COEF["ln_crp_mg_dl"] * math.log(crp_mg_dl)
        + _COEF["lymphocyte_pct"] * values["lymphocyte_pct"]
        + _COEF["mcv_fl"] * values["mcv_fl"]
        + _COEF["rdw_pct"] * values["rdw_pct"]
        + _COEF["alp_u_l"] * values["alp_u_l"]
        + _COEF["wbc_10e3_ul"] * values["wbc_10e3_ul"]
        + _COEF["age_years"] * age
    )


def ten_year_mortality(xb: float) -> float:
    """The paper's first Gompertz fit: linear predictor to 10-year mortality."""
    g = _GOMPERTZ
    return 1.0 - math.exp(-g["ten_year_scale"] * math.exp(xb) / g["ten_year_rate"])


def phenotypic_age(age: float, values: dict[str, float]) -> float:
    """The age at which an average person carries this panel's mortality risk.

    The paper applies two Gompertz fits back to back: the first turns the
    linear predictor into a 10-year mortality probability, the second asks what
    chronological age carries that probability on its own,

        age_intercept + ln(-age_scale * ln(1 - M)) / age_slope.

    Substituting M gives the same thing in closed form, affine in `xb`. That is
    what is computed here: the two-step version rounds M to exactly 1.0 for an
    extreme panel and then takes the log of zero, while this form cannot.
    """
    g = _GOMPERTZ
    xb = linear_predictor(age, values)
    constant = math.log(g["age_scale"] * g["ten_year_scale"] / g["ten_year_rate"])
    return g["age_intercept"] + (xb + constant) / g["age_slope"]


def contributions(age: float, values: dict[str, float]) -> dict[str, float]:
    """Years each marker adds to or takes from the phenotypic age, relative to
    a typical adult (the NHANES reference values measured by the experiment).

    Phenotypic age is affine in the linear predictor, so a marker's share of
    the gap is exact: its coefficient times its deviation from reference, over
    the Gompertz age slope. The shares sum to the gap up to the age term.
    """
    ref = _SPEC["reference"]
    if not ref:
        return {}
    here = linear_predictor(age, values)
    out: dict[str, float] = {}
    for name in INPUTS:
        swapped = dict(values, **{name: ref[name]})
        out[name] = round((here - linear_predictor(age, swapped)) / _GOMPERTZ["age_slope"], 2)
    return out


def mortality_ratio(acceleration_years: float) -> float:
    """Relative 10-year mortality against a person of the same chronological
    age: the Gompertz slope, exp(0.090165) = 1.094 per year of gap."""
    return math.exp(_GOMPERTZ["age_slope"] * acceleration_years)


def score_from_ratio(ratio: float, thresholds: Thresholds | None = None) -> float:
    """Place a mortality ratio on the 0-100 tier scale (see the module docstring)."""
    t = thresholds or Thresholds()
    span = math.log(SENIOR_MIN_RATIO) - math.log(STANDARD_MAX_RATIO)
    position = (math.log(max(ratio, 1e-9)) - math.log(STANDARD_MAX_RATIO)) / span
    score = t.low_max + (t.moderate_max - t.low_max) * position
    return round(max(0.0, min(100.0, score)), 2)


# ── the arm ──────────────────────────────────────────────────────────────────


def read_inputs(declared: dict) -> tuple[dict[str, float], list[str]]:
    """Pull the nine markers out of the declared-history dict.

    Returns the values and a list of problems. A value outside the plausible
    range for its unit is a problem, not a number: albumin of 40 is g/L, not
    g/dL, and scoring it would put the applicant decades older. Better to
    say so than to be silently wrong.
    """
    values: dict[str, float] = {}
    problems: list[str] = []
    for name in INPUTS:
        raw = declared.get(name)
        if raw is None or raw == "":
            problems.append(f"{LABELS[name]} was not entered")
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            problems.append(f"{LABELS[name]} is not a number: {raw!r}")
            continue
        lo, hi = _PLAUSIBLE[name]
        if not (lo <= value <= hi):
            problems.append(
                f"{LABELS[name]} = {value:g} is outside {lo:g}-{hi:g}; check the unit"
            )
            continue
        values[name] = value
    return values, problems


def read_optional(declared: dict) -> dict[str, float]:
    """The optional values that were entered as positive numbers."""
    out: dict[str, float] = {}
    for name in OPTIONAL_INPUTS:
        try:
            value = float(declared.get(name))
        except (TypeError, ValueError):
            continue
        if value > 0:
            out[name] = value
    return out


def run_form(declared: dict, age: int | None, sex: str | None) -> ArmResult:
    """Score one applicant's blood panel. Never raises."""
    if age is None:
        return ArmResult(score=None, error="date of birth is needed to compare the panel with age")
    if not 18 <= age <= 100:
        return ArmResult(
            score=None, error=f"age {age} is outside the 18-100 range the formula covers"
        )

    values, problems = read_inputs(declared)
    if problems:
        return ArmResult(score=None, error="; ".join(problems))

    try:
        pheno = phenotypic_age(age, values)
    except (ValueError, OverflowError) as exc:
        return ArmResult(score=None, error=f"phenotypic age could not be computed: {exc}")

    acceleration = pheno - age
    ratio = mortality_ratio(acceleration)
    extra = read_optional(declared)

    return ArmResult(
        score=score_from_ratio(ratio),
        raw_score=round(ratio, 4),
        details={
            "phenotypic_age": round(pheno, 1),
            "chronological_age": age,
            "acceleration_years": round(acceleration, 1),
            "mortality_ratio": round(ratio, 2),
            "standard_max_ratio": STANDARD_MAX_RATIO,
            "senior_min_ratio": SENIOR_MIN_RATIO,
            "inputs": values,
            "labels": LABELS,
            "reference": _SPEC["reference"],
            "contributions": contributions(age, values),
            "readings": panel_readings.readings(age, sex_code(sex), {**values, **extra}),
            # The audit trail's input signature for an arm with no file.
            "input_hash": hashlib.sha256(canonical({"age": age, **values}).encode()).hexdigest(),
            "scorer": f"{_SPEC['model']} v{_SPEC['version']} ({_SPEC['trained_on']})",
            "validation": VALIDATION,
        },
    )
