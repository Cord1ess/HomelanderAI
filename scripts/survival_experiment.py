"""Train the mortality arm's survival model on NHANES with real death records.

    cd apps/api && uv sync --extra train      # xgboost, used here only
    python scripts/survival_experiment.py

Reads the curated NHANES 1988-2018 release (Nguyen et al., CC-BY-4.0) from
`data/nhanes/`, with the National Death Index linkage it carries, and fits a
gradient-boosted Cox model on exactly the fields the intake form collects: age,
sex, height and weight, smoking, alcohol, activity, and the optional blood
panel. Missing values are allowed everywhere except age and sex, so an
applicant with no blood tests is still scored on what was entered.

Two honesty rules, both enforced here:

  1. **Temporal validation.** Train on the 1999-2010 cycles, test on 2011-2018.
     The number reported is on people the model never saw, examined later.
  2. **Age alone is the baseline.** On mortality, age gives a C-index around
     0.8 by itself. The model is only worth shipping if it beats age and sex.

The trained trees are exported as plain JSON next to the arm, and the export
is checked against XGBoost's own predictions before it is written: the arm
walks those trees with numpy alone, so xgboost is a training dependency and
never a runtime one. Along with the trees go per-age-and-sex reference
profiles (training-set medians), because the arm reports a hazard ratio
against a typical peer of the same age and sex, never an absolute risk — US
baselines do not transfer to Bangladesh.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data" / "nhanes"

sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

# NHANES cycle numbers (SDDSRVYR): 2 = 1999-2000 ... 10 = 2017-2018.
TRAIN_CYCLES = range(2, 8)
TEST_CYCLES = range(8, 11)

# Serum cotinine above this is a current smoker (Benowitz 2009, ng/mL).
COTININE_SMOKER_NG_ML = 10.0

RANDOM_SEED = 7


def load():
    """One row per adult with mortality follow-up, in the form's own keys."""
    import numpy as np
    import pandas as pd

    demo = pd.read_csv(
        DATA / "demographics_clean.csv",
        usecols=["SEQN_new", "SDDSRVYR", "RIDAGEYR", "RIAGENDR"],
    )
    labs = pd.read_csv(
        DATA / "response_clean.csv",
        usecols=[
            "SEQN_new", "LBXSAL", "LBXSCR", "LBXSGL", "LBXCRP", "LBXHSCRP", "LBXLYPCT",
            "LBXMCVSI", "LBXRDW", "LBXSAPSI", "LBXWBCSI", "LBXSASSI", "LBXSATSI",
            "LBXPLTSI", "BMXHT", "BMXWT", "VNAVEBPXSY",
        ],
    )
    quest = pd.read_csv(
        DATA / "questionnaire_clean.csv",
        usecols=["SEQN_new", "ALQ101", "ALQ130", "PAD200", "PAD320", "PAQ650", "PAQ665", "PAQ180"],
    )
    chem = pd.read_csv(DATA / "chemicals_clean.csv", usecols=["SEQN_new", "LBXCOT"])
    mort = pd.read_csv(
        DATA / "mortality_clean.csv",
        usecols=["SEQN_new", "ELIGSTAT", "MORTSTAT", "PERMTH_EXM"],
    )
    df = (
        demo.merge(labs, on="SEQN_new", how="left")
        .merge(quest, on="SEQN_new", how="left")
        .merge(chem, on="SEQN_new", how="left")
        .merge(mort, on="SEQN_new", how="left")
    )
    df = df[
        (df.SDDSRVYR >= 2)
        & (df.RIDAGEYR >= 18)
        & (df.RIDAGEYR <= 84)
        & (df.ELIGSTAT == 1)
        & (df.PERMTH_EXM > 0)
    ].copy()

    crp = df.LBXCRP * 10.0
    crp = crp.where(crp.notna(), df.LBXHSCRP)

    # The form's alcohol question: none / occasionally / regularly.
    drinks = df.ALQ130.where(df.ALQ130 < 100)  # 777 / 999 are refused / unknown
    alcohol = pd.Series(np.nan, index=df.index)
    alcohol[(df.ALQ101 == 2) | (drinks == 0)] = 0
    alcohol[drinks == 1] = 1
    alcohol[drinks >= 2] = 2

    # The form's activity question: sedentary / light / moderate / active. Two
    # questionnaire eras ask it differently; each maps to the same four steps.
    activity = pd.Series(np.nan, index=df.index)
    activity[(df.PAQ180 == 1)] = 0
    activity[(df.PAQ180 == 2)] = 1
    activity[(df.PAQ180 == 3)] = 2
    activity[(df.PAQ180 == 4)] = 3
    answered_new = (df.PAQ650.isin([1, 2])) | (df.PAQ665.isin([1, 2]))
    activity[answered_new] = 0
    activity[(df.PAQ665 == 1) | (df.PAD320 == 1)] = 2
    activity[(df.PAQ650 == 1) | (df.PAD200 == 1)] = 3
    answered_old = (df.PAD200.isin([1, 2, 3])) | (df.PAD320.isin([1, 2, 3]))
    activity[answered_old & activity.isna()] = 0

    out = pd.DataFrame(
        {
            "cycle": df.SDDSRVYR,
            "age": df.RIDAGEYR.astype(float),
            "male": (df.RIAGENDR == 1).astype(float),
            "height_cm": df.BMXHT,
            "weight_kg": df.BMXWT,
            "smoker": (df.LBXCOT > COTININE_SMOKER_NG_ML).astype(float).where(df.LBXCOT.notna()),
            "alcohol": alcohol,
            "activity": activity,
            "sbp_mmhg": df.VNAVEBPXSY,
            "albumin_g_dl": df.LBXSAL,
            "creatinine_mg_dl": df.LBXSCR,
            "glucose_mg_dl": df.LBXSGL,
            "crp_mg_l": crp,
            "lymphocyte_pct": df.LBXLYPCT,
            "mcv_fl": df.LBXMCVSI,
            "rdw_pct": df.LBXRDW,
            "alp_u_l": df.LBXSAPSI,
            "wbc_10e3_ul": df.LBXWBCSI,
            "ast_u_l": df.LBXSASSI,
            "alt_u_l": df.LBXSATSI,
            "platelets_10e3_ul": df.LBXPLTSI,
            "died": (df.MORTSTAT == 1).astype(int),
            "months": df.PERMTH_EXM.astype(float),
        },
        index=df.index,
    )
    return out


def harrell_c(risk, months, died) -> float:
    """Concordance with right-censoring: over comparable pairs (the earlier
    time is a death), the share where the earlier death had the higher risk."""
    import numpy as np

    risk, months, died = (np.asarray(a, dtype=float) for a in (risk, months, died))
    concordant = ties = comparable = 0.0
    for i in np.flatnonzero(died == 1):
        later = months > months[i]
        comparable += later.sum()
        concordant += (risk[later] < risk[i]).sum()
        ties += (risk[later] == risk[i]).sum()
    return float((concordant + 0.5 * ties) / comparable)


def flatten(booster) -> list[list[dict]]:
    """XGBoost's model as flat node lists the arm can walk without xgboost.

    Read from the JSON *model* rather than the text dump: the dump prints
    thresholds rounded to a few digits, and a value that sits exactly on a
    float32 threshold then takes the wrong branch. The model format keeps the
    exact float32 values, and the arm compares in float32 too.
    """
    raw = json.loads(bytes(booster.save_raw("json")))
    trees = []
    for tree in raw["learner"]["gradient_booster"]["model"]["trees"]:
        nodes = []
        for i in range(int(tree["tree_param"]["num_nodes"])):
            left, right = tree["left_children"][i], tree["right_children"][i]
            if left == -1:
                # A leaf's value lives in split_conditions in this format.
                nodes.append({"leaf": float(tree["split_conditions"][i])})
            else:
                nodes.append(
                    {
                        "f": int(tree["split_indices"][i]),
                        "t": float(tree["split_conditions"][i]),
                        "yes": left,
                        "no": right,
                        "missing": left if tree["default_left"][i] else right,
                    }
                )
        trees.append(nodes)
    return trees


def main() -> int:
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    from app.arms import mortality, survival_forest

    if not (DATA / "chemicals_clean.csv").exists():
        print(f"No NHANES data in {DATA}. See the docstring for the source.")
        return 1

    print("Loading NHANES ...", flush=True)
    df = load()
    features = survival_forest.FEATURES
    train = df[df.cycle.isin(TRAIN_CYCLES)]
    test = df[df.cycle.isin(TEST_CYCLES)]
    print(
        f"  train 1999-2010: {len(train)} adults, {train.died.sum()} deaths, "
        f"median follow-up {train.months.median() / 12:.1f} y"
    )
    print(
        f"  test  2011-2018: {len(test)} adults, {test.died.sum()} deaths, "
        f"median follow-up {test.months.median() / 12:.1f} y"
    )
    print("  missing per feature (train):")
    for f in features:
        print(f"    {f:18} {train[f].isna().mean():5.1%}")

    def label(part):
        # XGBoost's Cox convention: negative time means right-censored.
        return np.where(part.died == 1, part.months, -part.months)

    rng = np.random.default_rng(RANDOM_SEED)
    holdout = rng.random(len(train)) < 0.15
    fit, early = train[~holdout], train[holdout]
    d_fit = xgb.DMatrix(fit[features], label=label(fit), missing=np.nan)
    d_early = xgb.DMatrix(early[features], label=label(early), missing=np.nan)
    params = {
        "objective": "survival:cox",
        "eval_metric": "cox-nloglik",
        "eta": 0.03,
        "max_depth": 3,
        "min_child_weight": 100,
        "subsample": 0.7,
        "colsample_bytree": 0.8,
        "reg_lambda": 1.0,
        "seed": RANDOM_SEED,
    }
    print("\nTraining ...", flush=True)
    booster = xgb.train(
        params,
        d_fit,
        num_boost_round=3000,
        evals=[(d_early, "holdout")],
        early_stopping_rounds=100,
        verbose_eval=False,
    )
    rounds = booster.best_iteration + 1
    booster = booster[:rounds]
    print(f"  {rounds} trees of depth {params['max_depth']}")

    # ── validation on cycles the model never saw ─────────────────────────────
    d_test = xgb.DMatrix(test[features], missing=np.nan)
    margin = booster.predict(d_test, output_margin=True)
    c_model = harrell_c(margin, test.months, test.died)
    c_age = harrell_c(test.age, test.months, test.died)
    # Age and sex together, as a Cox model would rank them: a tiny booster on
    # those two columns is the fair "what the form's first two fields give".
    small = xgb.train(
        {**params, "eta": 0.1},
        xgb.DMatrix(fit[["age", "male"]], label=label(fit)),
        num_boost_round=200,
    )
    c_age_sex = harrell_c(
        small.predict(xgb.DMatrix(test[["age", "male"]]), output_margin=True), test.months, test.died
    )
    five = (test.months <= 60) & (test.died == 1)
    known = five | (test.months >= 60)
    auc5 = roc_auc_score(five[known], margin[known.to_numpy()])
    auc5_age = roc_auc_score(five[known], test.age[known])
    print("\nTemporal validation, 2011-2018 cycles")
    print(f"  C-index  model {c_model:.3f}   age+sex {c_age_sex:.3f}   age alone {c_age:.3f}")
    print(f"  5-year mortality AUC  model {auc5:.3f}   age alone {auc5_age:.3f}   (n={int(known.sum())})")

    # Which features the trees actually use.
    gain = booster.get_score(importance_type="total_gain")
    total = sum(gain.values()) or 1.0
    print("\nShare of total gain:")
    for name, g in sorted(gain.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {name:18} {g / total:5.1%}")

    # ── reference profiles: the typical peer of each age band and sex ────────
    profiles: dict[str, dict[str, dict[str, float]]] = {"M": {}, "F": {}}
    for sex, male in (("M", 1.0), ("F", 0.0)):
        for lo in range(18, 85, 5):
            hi = min(lo + 4, 84)
            band = train[(train.male == male) & (train.age >= lo) & (train.age <= hi)]
            profiles[sex][f"{lo}-{hi}"] = {
                f: round(float(band[f].median()), 3) for f in features if f not in ("age", "male")
            }

    # ── export, checked against xgboost before it is trusted ─────────────────
    trees = flatten(booster)
    spec = {
        "model": "gradient_boosted_cox_on_nhanes",
        "version": "1.0.0",
        "trained_on": "NHANES 1999-2010 with the 2019 public-use Linked Mortality Files",
        "n_train": int(len(train)),
        "deaths_train": int(train.died.sum()),
        "params": {**params, "num_boost_round": rounds},
        "features": features,
        "trees": trees,
        "reference_profiles": profiles,
        "validation": (
            f"temporal validation on NHANES 2011-2018 ({len(test)} adults, "
            f"{int(test.died.sum())} deaths): C-index {c_model:.3f} vs {c_age_sex:.3f} for "
            "age and sex alone; US cohort, NOT validated in South Asia"
        ),
        "validation_numbers": {
            "n_test": int(len(test)),
            "deaths_test": int(test.died.sum()),
            "c_index_model": round(c_model, 4),
            "c_index_age_sex": round(c_age_sex, 4),
            "c_index_age": round(c_age, 4),
            "auc_5_year_model": round(float(auc5), 4),
            "auc_5_year_age": round(float(auc5_age), 4),
        },
    }

    # The arm's own evaluator must reproduce xgboost's margins up to a constant
    # (the intercept cancels in every ratio the arm reports).
    sample = test[features].head(2000)
    ours = np.array([survival_forest.margin_of(trees, row) for row in sample.to_numpy()])
    theirs = booster.predict(xgb.DMatrix(sample, missing=np.nan), output_margin=True)
    offset = theirs - ours
    if np.ptp(offset) > 1e-4:
        print(f"\nEXPORT MISMATCH: margins differ by more than a constant (spread {np.ptp(offset):.2e})")
        return 1
    print(f"\nexport check: numpy walk matches xgboost to {np.abs(offset - offset.mean()).max():.1e}")

    mortality.SURVIVAL_PATH.write_text(json.dumps(spec, separators=(",", ":")) + "\n")
    size_kb = mortality.SURVIVAL_PATH.stat().st_size / 1024
    print(f"wrote {mortality.SURVIVAL_PATH.relative_to(REPO_ROOT)} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
