"""Standard clinical readings from the same blood panel: kidney, liver, weight, glucose.

An underwriter looking at a lab report reaches for four things before anything
else, and each is a published formula with fixed constants, not a model:

- **eGFR** (CKD-EPI 2021, creatinine, race-free) and the KDIGO stage.
- **FIB-4**, the liver-fibrosis index from age, AST, ALT and platelets.
- **BMI**, with the WHO cut-offs for Asian populations, which are lower.
- **Fasting glucose** against the ADA diabetes thresholds.

They are shown beside the phenotypic age and they do not move the score: the
score is the mortality formula, and these are the readings that let a person
see *why* a panel looks the way it does. Each reading carries its own note
saying what it is and what it is not.

Pure functions over floats. Every threshold is named so it can be checked
against its source.
"""

from dataclasses import asdict, dataclass

# ── eGFR: CKD-EPI 2021 (Inker et al., NEJM 2021) ────────────────────────────
# eGFR = 142 x min(Scr/k, 1)^a x max(Scr/k, 1)^-1.200 x 0.9938^age x 1.012 [female]
_CKD_EPI = {"F": (0.7, -0.241, 1.012), "M": (0.9, -0.302, 1.0)}

# KDIGO 2012 GFR categories, mL/min/1.73 m².
_GFR_STAGES = (
    (90, "G1", "normal or high"),
    (60, "G2", "mildly decreased"),
    (45, "G3a", "mildly to moderately decreased"),
    (30, "G3b", "moderately to severely decreased"),
    (15, "G4", "severely decreased"),
    (0, "G5", "kidney failure"),
)

# ── FIB-4 (Sterling et al., Hepatology 2006) ────────────────────────────────
# Cut-offs: <1.30 rules out advanced fibrosis, >2.67 rules it in; for people
# over 65 the lower cut-off is 2.0 (McPherson et al., Am J Gastroenterol 2017).
FIB4_LOW = 1.30
FIB4_LOW_OVER_65 = 2.0
FIB4_HIGH = 2.67

# ── BMI, WHO Asian cut-offs (WHO Expert Consultation, Lancet 2004) ──────────
# Asian populations carry cardiometabolic risk at lower BMI, so the public
# health action points are 23 and 27.5 rather than 25 and 30.
_BMI_ASIAN = (
    (18.5, "underweight"),
    (23.0, "normal"),
    (27.5, "overweight"),
    (float("inf"), "obese"),
)

# ── fasting glucose, ADA Standards of Care (mg/dL) ──────────────────────────
GLUCOSE_PREDIABETES = 100.0
GLUCOSE_DIABETES = 126.0


@dataclass(frozen=True)
class Reading:
    """One line on the review screen: a name, a value, its unit, a category,
    whether that category deserves a look, and the sentence explaining it."""

    key: str
    label: str
    value: float
    unit: str
    category: str
    flag: bool
    note: str


def egfr(creatinine_mg_dl: float, age: float, sex: str) -> float:
    """CKD-EPI 2021 creatinine equation, in mL/min/1.73 m²."""
    kappa, alpha, factor = _CKD_EPI["F" if sex == "F" else "M"]
    ratio = creatinine_mg_dl / kappa
    return 142.0 * min(ratio, 1.0) ** alpha * max(ratio, 1.0) ** -1.200 * 0.9938**age * factor


def gfr_stage(value: float) -> tuple[str, str]:
    for floor, stage, meaning in _GFR_STAGES:
        if value >= floor:
            return stage, meaning
    return _GFR_STAGES[-1][1], _GFR_STAGES[-1][2]


def fib4(age: float, ast_u_l: float, alt_u_l: float, platelets_10e3_ul: float) -> float:
    return (age * ast_u_l) / (platelets_10e3_ul * alt_u_l**0.5)


def bmi(height_cm: float, weight_kg: float) -> float:
    metres = height_cm / 100.0
    return weight_kg / (metres * metres)


def bmi_category_asian(value: float) -> str:
    for ceiling, name in _BMI_ASIAN:
        if value < ceiling:
            return name
    return _BMI_ASIAN[-1][1]


def glucose_category(fasting_mg_dl: float) -> str:
    if fasting_mg_dl >= GLUCOSE_DIABETES:
        return "diabetes range"
    if fasting_mg_dl >= GLUCOSE_PREDIABETES:
        return "prediabetes range"
    return "normal"


def readings(age: float, sex: str | None, values: dict[str, float]) -> list[dict]:
    """Every reading the given values allow, as plain dicts for the report.

    `values` are the form's keys (creatinine_mg_dl, glucose_mg_dl, height_cm,
    weight_kg, ast_u_l, alt_u_l, platelets_10e3_ul). A reading whose inputs are
    absent is simply not produced; nothing is guessed.
    """
    out: list[Reading] = []

    if "creatinine_mg_dl" in values and sex in ("F", "M"):
        value = egfr(values["creatinine_mg_dl"], age, sex)
        stage, meaning = gfr_stage(value)
        out.append(
            Reading(
                key="egfr",
                label="Kidney function (eGFR)",
                value=round(value, 0),
                unit="mL/min/1.73 m²",
                category=f"{stage}, {meaning}",
                flag=value < 60,
                note="CKD-EPI 2021 creatinine equation, race-free. Below 60 for three "
                "months is chronic kidney disease; a single value is a prompt, not a diagnosis.",
            )
        )

    if all(k in values for k in ("ast_u_l", "alt_u_l", "platelets_10e3_ul")):
        value = fib4(age, values["ast_u_l"], values["alt_u_l"], values["platelets_10e3_ul"])
        low = FIB4_LOW_OVER_65 if age > 65 else FIB4_LOW
        if value < low:
            category, flag = "advanced fibrosis unlikely", False
        elif value > FIB4_HIGH:
            category, flag = "advanced fibrosis likely", True
        else:
            category, flag = "indeterminate", True
        out.append(
            Reading(
                key="fib4",
                label="Liver fibrosis index (FIB-4)",
                value=round(value, 2),
                unit="",
                category=category,
                flag=flag,
                note=f"Age x AST / (platelets x sqrt ALT). Below {low:g} rules out advanced "
                f"fibrosis, above {FIB4_HIGH:g} suggests it. Relevant where hepatitis B and "
                "fatty liver disease are common.",
            )
        )

    if "height_cm" in values and "weight_kg" in values and values["height_cm"] > 0:
        value = bmi(values["height_cm"], values["weight_kg"])
        category = bmi_category_asian(value)
        out.append(
            Reading(
                key="bmi",
                label="Body mass index",
                value=round(value, 1),
                unit="kg/m²",
                category=category,
                flag=category != "normal",
                note="WHO cut-offs for Asian populations: overweight from 23, obese from 27.5.",
            )
        )

    if "glucose_mg_dl" in values:
        category = glucose_category(values["glucose_mg_dl"])
        out.append(
            Reading(
                key="glucose",
                label="Fasting glucose",
                value=values["glucose_mg_dl"],
                unit="mg/dL",
                category=category,
                flag=category != "normal",
                note=f"ADA thresholds: {GLUCOSE_PREDIABETES:g} prediabetes, {GLUCOSE_DIABETES:g} "
                "diabetes. Meaningful only if the sample was fasting; confirm with HbA1c.",
            )
        )

    return [asdict(r) for r in out]
