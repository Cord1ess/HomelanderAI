"""Does Levine's Phenotypic Age hold up on NHANES, and what does an average adult look like?

    python scripts/phenoage_experiment.py

Reads the curated NHANES 1988-2018 release (Nguyen et al., CC-BY-4.0, with the
National Death Index linkage built in) from `data/nhanes/` and:

  1. Computes Phenotypic Age for every adult with the nine markers, using the
     published coefficients in `app/arms/mortality.py` — the same code the arm
     runs, so this measures what the product does, not a reimplementation.
  2. Measures how well it predicts 10-year all-cause mortality, against
     chronological age alone. Levine 2018 / Liu 2018 report AUC 0.88 vs 0.86 on
     NHANES IV; if we cannot get near that, the formula is wrong.
  3. Writes the marker means of that adult cohort into the arm's JSON, so the
     per-marker explanation on the review screen is "years relative to a
     typical adult", measured rather than asserted.

Why AUC and not a hazard ratio: no survival library is installed, and a Cox fit
is not needed to know whether the number discriminates. An age-adjusted logistic
odds ratio per year of acceleration is reported alongside as the nearest thing
to the paper's HR 1.09 that plain scikit-learn gives.

Data: https://huggingface.co/datasets/nguyenvy/cleaned_nhanes_1988_2018
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data" / "nhanes"

sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

# NHANES column -> the arm's input name and the arm's unit. NHANES stores CRP in
# mg/dL for 1999-2010 and hs-CRP in mg/L from 2015; the arm takes mg/L, the unit
# Bangladeshi labs report, so the older column is multiplied by 10.
MARKERS = {
    "LBXSAL": ("albumin_g_dl", 1.0),
    "LBXSCR": ("creatinine_mg_dl", 1.0),
    "LBXSGL": ("glucose_mg_dl", 1.0),
    "LBXLYPCT": ("lymphocyte_pct", 1.0),
    "LBXMCVSI": ("mcv_fl", 1.0),
    "LBXRDW": ("rdw_pct", 1.0),
    "LBXSAPSI": ("alp_u_l", 1.0),
    "LBXWBCSI": ("wbc_10e3_ul", 1.0),
}


def load():
    import pandas as pd

    demo = pd.read_csv(
        DATA / "demographics_clean.csv",
        usecols=["SEQN_new", "SDDSRVYR", "RIDAGEYR", "RIAGENDR"],
    )
    labs = pd.read_csv(
        DATA / "response_clean.csv",
        usecols=["SEQN_new", *MARKERS, "LBXCRP", "LBXHSCRP"],
    )
    mort = pd.read_csv(
        DATA / "mortality_clean.csv",
        usecols=["SEQN_new", "ELIGSTAT", "MORTSTAT", "PERMTH_EXM"],
    )
    df = demo.merge(labs, on="SEQN_new").merge(mort, on="SEQN_new")

    # Continuous NHANES only (cycle 1 is NHANES III, Levine's training set —
    # testing on it would be testing on the training data), adults 20-84 as in
    # the paper, and only people the mortality linkage actually followed.
    df = df[(df.SDDSRVYR >= 2) & (df.RIDAGEYR >= 20) & (df.RIDAGEYR <= 84) & (df.ELIGSTAT == 1)]

    crp_mg_l = df.LBXCRP * 10.0
    crp_mg_l = crp_mg_l.where(crp_mg_l.notna(), df.LBXHSCRP)
    out = pd.DataFrame({"age": df.RIDAGEYR, "sex": df.RIAGENDR, "crp_mg_l": crp_mg_l})
    for col, (name, factor) in MARKERS.items():
        out[name] = df[col] * factor
    out["died"] = df.MORTSTAT
    out["months"] = df.PERMTH_EXM
    return out.dropna()


def main() -> int:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    from app.arms import mortality

    if not (DATA / "response_clean.csv").exists():
        print(f"No NHANES data in {DATA}. See the docstring for the source.")
        return 1

    print("Loading NHANES ...", flush=True)
    df = load()
    print(f"  {len(df)} adults aged 20-84 with all nine markers and mortality follow-up")

    pheno = np.array(
        [
            mortality.phenotypic_age(row.age, {k: getattr(row, k) for k in mortality.INPUTS})
            for row in df.itertuples()
        ]
    )
    accel = pheno - df.age.to_numpy()
    print(f"  Phenotypic age vs chronological age: r = {np.corrcoef(df.age, pheno)[0, 1]:.3f}")
    print(f"  acceleration mean {accel.mean():+.2f} y, sd {accel.std():.2f} y")

    # 10-year mortality: died within 120 months, or known alive at 120 months.
    died10 = (df.died == 1) & (df.months <= 120)
    known = died10 | (df.months >= 120)
    y = died10[known].to_numpy().astype(int)
    print(f"\n10-year all-cause mortality, n = {known.sum()}, deaths = {y.sum()}")
    auc_age = roc_auc_score(y, df.age[known])
    auc_pheno = roc_auc_score(y, pheno[known.to_numpy()])
    print(f"  AUC chronological age  {auc_age:.3f}")
    print(f"  AUC phenotypic age     {auc_pheno:.3f}   (paper: 0.86 vs 0.88)")

    x = np.column_stack([df.age[known], accel[known.to_numpy()]])
    fit = LogisticRegression(penalty=None, max_iter=1000).fit(x, y)
    odds_per_year = float(np.exp(fit.coef_[0][1]))
    print(f"  age-adjusted odds ratio per year of acceleration: {odds_per_year:.3f}")
    print("  (paper: HR 1.09 per year)")

    reference = {k: round(float(df[k].mean()), 3) for k in mortality.INPUTS}
    print("\nReference (mean) values written to the arm:")
    for k, v in reference.items():
        print(f"  {k:18} {v}")

    spec = json.loads(mortality.MODEL_PATH.read_text())
    spec["reference"] = reference
    spec["validation"] = (
        f"our replication on NHANES 1999-2018, {known.sum()} adults aged 20-84: "
        f"10-year mortality AUC {auc_pheno:.3f} vs {auc_age:.3f} for chronological age; "
        "US cohort, NOT validated in South Asia"
    )
    spec["validation_numbers"] = {
        "n_adults": int(len(df)),
        "n_ten_year": int(known.sum()),
        "deaths_ten_year": int(y.sum()),
        "auc_chronological_age": round(auc_age, 4),
        "auc_phenotypic_age": round(auc_pheno, 4),
        "odds_ratio_per_year_age_adjusted": round(odds_per_year, 4),
        "acceleration_mean_years": round(float(accel.mean()), 3),
        "acceleration_sd_years": round(float(accel.std()), 3),
    }
    mortality.MODEL_PATH.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"\nwrote {mortality.MODEL_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
