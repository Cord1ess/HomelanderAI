# Mortality arm — how it works

Nine values from a routine blood panel, the lifestyle answers on the intake
form, the applicant's age and sex go in. Out comes one number: how the
applicant's mortality compares with a typical person of the same age and sex,
expressed as a ratio, and placed on the same 0–100 scale as every other arm.

Every other arm screens for a disease. This one answers the question an
insurer is actually asking. It never produces an absolute probability of death,
and it never decides anything: an underwriter reads it beside the rest.

---

## Two readings, the higher governs

### 1. Phenotypic Age — a published formula

**File:** `apps/api/app/arms/mortality.py`, constants in `mortality_model.json`

Levine et al. (2018, *Aging*) fitted a mortality model on NHANES III, a US
survey with real death records, and found nine ordinary blood values that,
together with age, predict death better than age alone:

| Value | Unit the form takes | Typical adult |
|---|---|---|
| Serum albumin | g/dL | 4.2 |
| Serum creatinine | mg/dL | 0.9 |
| Glucose | mg/dL | 101 |
| C-reactive protein | mg/L | 4.5 |
| Lymphocytes | % of white cells | 30 |
| Mean cell volume | fL | 89 |
| Red cell distribution width (RDW-CV) | % | 13.2 |
| Alkaline phosphatase | U/L | 72 |
| White blood cell count | ×10³/µL | 7.3 |

The output is an **age**: the chronological age at which an average person
would carry the same 10-year mortality risk. A 45-year-old with a phenotypic
age of 53 has the blood panel of a typical 53-year-old.

The gap between the two ages becomes a mortality ratio through the formula's
own slope — about 1.09 per year, which is the hazard ratio the paper reports.
Each value's share of the gap is shown in years, against the typical adult
above, so the underwriter sees which value is doing the work. RDW carries the
largest weight by far; that is the formula, not a bug.

**Measured on this code**, by `scripts/phenoage_experiment.py`, on NHANES
1999–2018 (21,959 adults aged 20–84 with ten years of follow-up, 3,458
deaths): 10-year mortality AUC **0.887**, against **0.861** for chronological
age alone. The paper reports 0.88 and 0.86. The constants are the full-precision
values from the reference implementation, including the 0.090165 denominator
of the 2019 correction.

### 2. The survival model — trained here

**Files:** `apps/api/app/arms/survival_forest.py`, trees in `survival_model.json`

Gradient-boosted Cox trees, trained by `scripts/survival_experiment.py` on
NHANES 1999–2010 with the National Death Index linkage (33,646 adults, 5,600
deaths), on exactly the fields the form collects: age, sex, height, weight,
smoking, alcohol, physical activity, systolic blood pressure, and the blood
panel above with AST, ALT and platelets. Missing values are allowed, so an
applicant with no blood tests is scored on what was entered.

**Validated on cycles the model never saw** (2011–2018, 17,126 adults, 820
deaths): C-index **0.876**, against **0.833** for age and sex alone and 0.828
for age alone; 5-year mortality AUC 0.895 against 0.850 for age.

The trees are exported as plain JSON and walked with numpy — the export is
checked against XGBoost's own predictions before it is written — so `xgboost`
is a training dependency only (`uv sync --extra train`).

The reading is a hazard ratio against a **peer measured on the same values**:
the training-set median profile for the applicant's sex and five-year age
band, restricted to the values the applicant entered. That restriction
matters. In NHANES the people who skipped the blood draw died sooner, and the
trees learned it; a peer with a full panel beside an applicant with none would
charge the applicant for what was never measured.

Each entered value is shown as the hazard factor it carries against the
peer's value (×1.82 for smoking, ×1.46 for a sedentary life, and so on).

---

## The score

The ratio is placed on the tier scale the way insurers already rate:

| Mortality ratio | Meaning | Tier |
|---|---|---|
| up to 1.25× | standard class | low (score ≤ 30) |
| 1.25× – 2.0× | table rating, adjusted premium | moderate |
| above 2.0× | senior review | elevated (score > 65) |

125% is the conventional ceiling of a standard life-insurance class; 200% is
where an underwriter stops pricing and a senior one looks. The two anchors sit
exactly on the tier cut-points, so the tiers keep their meaning.

---

## Standard readings from the same panel

**File:** `apps/api/app/arms/panel_readings.py`

Beside the two readings, four things an underwriter reaches for first. Each is
a published formula with fixed constants; none moves the score.

| Reading | Formula | Flag |
|---|---|---|
| Kidney function (eGFR) | CKD-EPI 2021, creatinine, race-free; KDIGO stage | below 60 |
| Liver fibrosis index (FIB-4) | age × AST / (platelets × √ALT) | above 1.30 (2.0 over 65) |
| Body mass index | WHO cut-offs for Asian populations: 23 / 27.5 | outside normal |
| Fasting glucose | ADA thresholds: 100 / 126 mg/dL | outside normal |

---

## Limits to state honestly

**1. No South Asian validation.** Both readings were derived and validated on
US adults. That is why the arm reports a ratio against a peer, never an
absolute probability: the baseline does not transfer, the ordering may.

**2. The published formula is a 1988–94 calibration.** The average adult in
NHANES 1999–2018 reads 3.7 years younger than their age under it. The arm
compares with the formula's own baseline, as published.

**3. Units.** A value typed in the wrong unit is refused, not scored: albumin
of 40 is g/L, and scored as g/dL it would put an applicant decades older.
CRP must be mg/L; RDW must be RDW-CV, not RDW-SD.

**4. Smoking and alcohol.** The survival model learned "current smoker" from
serum cotinine, so the form's "current or former" box is scored as current —
the conservative direction. Alcohol shows the usual J-curve of survey data:
non-drinkers carry slightly higher hazard than occasional drinkers, largely
because people who stopped for health reasons are counted as non-drinkers.

**5. Age does most of the work.** On mortality, age alone scores 0.83–0.86.
The numbers above are only meaningful next to that baseline, which is why the
experiments print both.

---

## Reproducing the numbers

```bash
# the curated NHANES 1988-2018 release (Nguyen et al., CC-BY-4.0), ~1.5 GB
#   https://huggingface.co/datasets/nguyenvy/cleaned_nhanes_1988_2018
# into data/nhanes/: demographics_clean, response_clean, questionnaire_clean,
# chemicals_clean, mortality_clean, dictionary_nhanes

cd apps/api && uv sync --extra vision --extra nlp --extra train
python scripts/phenoage_experiment.py     # validates the formula, writes reference values
python scripts/survival_experiment.py     # trains, validates, exports the trees (~2 min)
uv run pytest tests/test_mortality.py tests/test_survival_forest.py tests/test_panel_readings.py
```
