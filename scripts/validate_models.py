"""Does every reader give valid answers? One check per arm, on data it never saw.

    apps/api/.venv/Scripts/python.exe scripts/validate_models.py all
    apps/api/.venv/Scripts/python.exe scripts/validate_models.py tb retina ecg ...

Every file goes through the path an application takes — `intake.process_upload`
then the arm's own `read` — so this measures the product, not a re-implementation.
Each check writes `data/validation/<name>.json` and prints a short table.

What each check uses, and why it is fair:

  tb          Montgomery (USA, 138 films) and TBX11K (Chinese hospitals, TB
              images with boxes vs healthy). The model was trained on Shenzhen
              only; neither set overlaps it.
  retina      IDRiD test split (103) and DeepDRiD (1,600). The only sets the
              FLAIR backbone was not pretrained on with grade labels.
  ecg         CODE-test (827 tracings, labels by two-to-three cardiologists).
              The network's authors held this set out of training.
  mortality   NHANES 2011-2018: the cycles the survival model was not trained
              on. PhenoAge's coefficients come from NHANES III, also unseen.
  readings    Known-answer cases worked by hand from the published equations.
  medication  Hand-written clinical notes with the answer each should give.
  mirai       The authors' published demo exam (must reproduce to 4 d.p.) and
              behaviour checks. No outcome data exists here for accuracy.
  robustness  What every arm does with the wrong kind of file, a blank one,
              noise, and small harmless changes (flip, recompression).

Any accuracy above ~0.97 on these tasks should be treated as a shortcut, not a
triumph (see docs/TB.md on the Kaggle TB set).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.arms import ARMS  # noqa: E402
from app.intake import IntakeError, process_upload  # noqa: E402

DATA = REPO / "data"
OUT = DATA / "validation"


# ── shared measures ──────────────────────────────────────────────────────────


def auc(labels, scores) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(labels, scores))


def auc_ci(labels, scores, rounds: int = 1000) -> tuple[float, float]:
    labels, scores = np.asarray(labels), np.asarray(scores)
    rng = np.random.default_rng(0)
    out = []
    for _ in range(rounds):
        i = rng.integers(0, len(labels), len(labels))
        if 0 < labels[i].sum() < len(i):
            out.append(auc(labels[i], scores[i]))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def at_cut(labels, scores, cut: float) -> dict:
    labels, scores = np.asarray(labels), np.asarray(scores)
    pos, neg = labels == 1, labels == 0
    flagged = scores > cut
    return {
        "cut": cut,
        "sensitivity": round(float(flagged[pos].mean()), 3),
        "specificity": round(float((~flagged[neg]).mean()), 3),
    }


def binary_summary(labels, scores) -> dict:
    lo, hi = auc_ci(labels, scores)
    return {
        "n": len(labels),
        "positives": int(sum(labels)),
        "auc": round(auc(labels, scores), 3),
        "auc_95ci": [round(lo, 3), round(hi, 3)],
        "tier_cuts": [at_cut(labels, scores, 30.0), at_cut(labels, scores, 65.0)],
    }


def read_file(arm_name: str, raw: bytes, name: str, declared: dict | None = None):
    """One file through intake and the arm, exactly as the pipeline does."""
    stored = process_upload(raw, name).data
    return ARMS[arm_name].read(stored, declared or {})


def cached(name: str) -> dict:
    path = OUT / f"{name}_scores.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_cache(name: str, cache: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}_scores.json").write_text(json.dumps(cache))


def set_last_key(path: Path, key: str, value) -> None:
    """Add, or replace, `key` as the last entry of a JSON object file and leave
    every other byte as it was. The model files keep their weight arrays on
    one line each; re-dumping them would spread a two-number change over
    twelve thousand lines of diff."""
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    marker = f',\n  "{key}": '
    if marker in text:
        text = text[: text.index(marker)] + "\n}\n"
    body = text.rstrip()
    assert body.endswith("}"), f"{path.name} is not a JSON object"
    block = json.dumps(value, indent=2).replace("\n", "\n  ")
    path.write_bytes((body[:-1].rstrip() + f',\n  "{key}": {block}\n}}\n').encode("utf-8"))
    json.loads(path.read_text(encoding="utf-8"))  # still valid


def report(name: str, result: dict) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"check": name, "run_at": time.strftime("%Y-%m-%d %H:%M"), **result}
    (OUT / f"{name}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result


def score_files(cache_name: str, arm: str, items: list[tuple[str, Path]]) -> dict:
    """{key: score or None}, cached on disk so a rerun only scores what is new."""
    cache = cached(cache_name)
    todo = [(k, p) for k, p in items if k not in cache]
    for i, (key, path) in enumerate(todo, 1):
        try:
            result = read_file(arm, path.read_bytes(), path.name)
            cache[key] = result.score
        except IntakeError as exc:
            cache[key] = None
            print(f"  {key}: refused at intake: {exc}")
        if i % 25 == 0:
            save_cache(cache_name, cache)
            print(f"  {cache_name}: {i}/{len(todo)}", flush=True)
    save_cache(cache_name, cache)
    return cache


# ── chest X-ray: tuberculosis ────────────────────────────────────────────────


def check_tb() -> dict:
    out = {}
    films = sorted((DATA / "montgomery").glob("*.png"))
    scores = score_files("tb_montgomery", "tb_xray", [(f.name, f) for f in films])
    keys = [f.name for f in films if scores.get(f.name) is not None]
    labels = [int(Path(k).stem.rsplit("_", 1)[1]) for k in keys]
    out["montgomery"] = binary_summary(labels, [scores[k] for k in keys])

    if (DATA / "tbx11k" / "data.csv").exists():
        test, _ = tbx11k_sets()
        images = [DATA / "tbx11k" / "images" / name for name in sorted(test)]
        images = [p for p in images if p.exists()]
        scores = score_files("tb_tbx11k", "tb_xray", [(p.name, p) for p in images])
        keys = [p.name for p in images if scores.get(p.name) is not None]
        labels = [1 if test[k] == "tb" else 0 for k in keys]
        out["tbx11k"] = binary_summary(labels, [scores[k] for k in keys])
        out["tbx11k"]["note"] = "TB images with lesion boxes vs healthy; sick-but-not-TB excluded"
    return report("tb", out)


def tbx11k_sets() -> tuple[dict[str, str], dict[str, str]]:
    """(test, calibration): file name -> image type. Disjoint by construction.

    Test: the TB films with radiologist boxes and the first 80 healthy films.
    Calibration, for the TB score's cut-points only: every seventh healthy and
    sick-but-not-TB film from the seventh on, minus anything in the test set.
    """
    rows = list(csv.DictReader((DATA / "tbx11k" / "data.csv").open()))
    kind = {r["fname"]: r["image_type"] for r in rows}
    tb = sorted(n for n, k in kind.items() if k == "tb")
    healthy = sorted(n for n, k in kind.items() if k == "healthy")
    sick = sorted(n for n, k in kind.items() if k == "sick_but_no_tb")
    test = {n: kind[n] for n in tb[:160] + healthy[:80]}
    calibration = {
        n: kind[n] for n in healthy[7::7][:400] + sick[7::7][:400] if n not in test
    }
    return test, calibration


# ── fundus photograph: diabetic retinopathy ──────────────────────────────────


def check_retina(limit: int) -> dict:
    out = {}
    for dataset, split in (("idrid", "test"), ("deepdrid", None)):
        folder = DATA / "dr" / dataset
        rows = list(csv.DictReader((folder / "labels.csv").open()))
        if split:
            rows = [r for r in rows if r["split"] == split]
        if limit and len(rows) > limit:
            # Keep every grade represented: sample within grade.
            rng = random.Random(0)
            by_grade: dict[str, list] = {}
            for r in rows:
                by_grade.setdefault(r["grade"], []).append(r)
            share = limit / len(rows)
            rows = [
                r for g in by_grade.values() for r in rng.sample(g, max(1, round(len(g) * share)))
            ]
        items = [(r["image"], folder / "images" / r["image"]) for r in rows]
        cache = cached(f"retina_{dataset}")
        todo = [(k, p) for k, p in items if k not in cache]
        for i, (key, path) in enumerate(todo, 1):
            result = read_file("dr_fundus", path.read_bytes(), path.name)
            cache[key] = (
                {"score": result.score, "grade": result.details.get("icdr_grade")}
                if result.score is not None
                else {"score": None, "error": result.error}
            )
            if i % 25 == 0:
                save_cache(f"retina_{dataset}", cache)
                print(f"  retina {dataset}: {i}/{len(todo)}", flush=True)
        save_cache(f"retina_{dataset}", cache)

        truth = {r["image"]: int(r["grade"]) for r in rows}
        scored = [k for k, _ in items if cache[k]["score"] is not None]
        refused = [k for k, _ in items if cache[k]["score"] is None]
        labels = [int(truth[k] >= 2) for k in scored]
        summary = binary_summary(labels, [cache[k]["score"] for k in scored])
        from sklearn.metrics import cohen_kappa_score

        summary["grade_quadratic_kappa"] = round(
            float(
                cohen_kappa_score(
                    [truth[k] for k in scored],
                    [cache[k]["grade"] for k in scored],
                    weights="quadratic",
                )
            ),
            3,
        )
        summary["refused_as_ungradable"] = len(refused)
        summary["refused_true_grades"] = sorted(truth[k] for k in refused)
        out[dataset] = summary
    return report("retina", out)


# ── 12-lead ECG ──────────────────────────────────────────────────────────────


def check_ecg() -> dict:
    from app import ecg
    from app.arms import ecg_12lead

    folder = DATA / "ecg" / "raw" / "test"
    tracings = np.load(folder / "tracings_model_units.npy", mmap_mode="r")
    gold = list(csv.DictReader((folder / "gold_standard.csv").open()))
    ages = [int(r["age"]) for r in csv.DictReader((folder / "attributes.csv").open())]

    cache = cached("ecg_codetest")
    for i in range(len(tracings)):
        if str(i) in cache:
            continue
        stored = ecg.to_bytes(np.asarray(tracings[i], dtype=np.float32) / ecg.MV_TO_MODEL)
        result = read_file("ecg_12lead", stored, f"codetest_{i}.npy")
        cache[str(i)] = {
            "score": result.score,
            "reported": result.details.get("reported", []),
            "ecg_age": result.details.get("ecg_age"),
        }
        if (i + 1) % 100 == 0:
            save_cache("ecg_codetest", cache)
            print(f"  ecg: {i + 1}/{len(tracings)}", flush=True)
    save_cache("ecg_codetest", cache)

    per_class = {}
    for name in ecg_12lead.CLASSES:
        truth = np.array([int(g[name]) for g in gold])
        said = np.array([name in cache[str(i)]["reported"] for i in range(len(gold))])
        tp = int((said & (truth == 1)).sum())
        fp = int((said & (truth == 0)).sum())
        fn = int((~said & (truth == 1)).sum())
        tn = int((~said & (truth == 0)).sum())
        per_class[name] = {
            "positives": int(truth.sum()),
            "sensitivity": round(tp / (tp + fn), 3),
            "specificity": round(tn / (tn + fp), 3),
            "ppv": round(tp / (tp + fp), 3) if tp + fp else None,
            "f1": round(2 * tp / (2 * tp + fp + fn), 3),
        }
    normal = [i for i, g in enumerate(gold) if not any(int(v) for v in g.values())]
    abnormal = [i for i in range(len(gold)) if i not in set(normal)]
    scores = [cache[str(i)]["score"] for i in range(len(gold))]
    labels = [0 if i in set(normal) else 1 for i in range(len(gold))]
    ecg_age = np.array([cache[str(i)]["ecg_age"] for i in range(len(gold))], dtype=float)
    return report(
        "ecg",
        {
            "n": len(gold),
            "per_class_vs_cardiologists": per_class,
            "any_abnormality": binary_summary(labels, scores),
            "normal_tracings_in_low_tier": round(
                float(np.mean([scores[i] <= 30 for i in normal])), 3
            ),
            "abnormal_tracings_above_low_tier": round(
                float(np.mean([scores[i] > 30 for i in abnormal])), 3
            ),
            "ecg_age_mae_years": round(float(np.mean(np.abs(ecg_age - np.array(ages)))), 1),
            "ecg_age_correlation": round(float(np.corrcoef(ecg_age, ages)[0, 1]), 3),
        },
    )


# ── blood panel: phenotypic age and the survival model ───────────────────────


def check_mortality(limit: int) -> dict:
    sys.path.insert(0, str(REPO / "scripts"))
    import survival_experiment as se
    from app.arms import mortality, survival_forest

    alcohol = {v: k for k, v in survival_forest.ALCOHOL.items()}
    activity = {v: k for k, v in survival_forest.ACTIVITY.items()}
    df = se.load()
    test = df[df.cycle.isin(se.TEST_CYCLES)]
    if limit and len(test) > limit:
        test = test.sample(limit, random_state=0)

    rows = []
    for r in test.itertuples():
        declared = {
            k: getattr(r, k)
            for k in (*mortality.INPUTS, *mortality.OPTIONAL_INPUTS)
            if getattr(r, k) == getattr(r, k)  # not NaN
        }
        if r.smoker == r.smoker:
            declared["smoker"] = bool(r.smoker)
        if r.alcohol == r.alcohol:
            declared["alcohol"] = alcohol[float(r.alcohol)]
        if r.activity == r.activity:
            declared["activity"] = activity[float(r.activity)]
        result = mortality.run_form(declared, int(r.age), "Male" if r.male else "Female")
        if result.score is None:
            continue
        rows.append(
            (result.score, r.age, r.died, r.months, r.male, r.cycle, result.details["governing"])
        )
    cols = list(zip(*rows, strict=True))
    score, age, died, months, male, cycle = (np.array(c, dtype=float) for c in cols[:6])
    governing = np.array(cols[6])

    def within_band_c(risk) -> float:
        """Concordance counted only between people of the same sex and
        five-year age band: the score is relative to exactly that peer, so
        this is the question it answers. Plain C-index is dominated by age."""
        band = np.floor((np.clip(age, 18, 84) - 18) / 5)
        concordant = comparable = 0.0
        for sex in (0.0, 1.0):
            for b in np.unique(band):
                m = (male == sex) & (band == b)
                rk, mo, de = risk[m], months[m], died[m]
                for i in np.flatnonzero(de == 1):
                    later = mo > mo[i]
                    comparable += later.sum()
                    concordant += (rk[later] < rk[i]).sum() + 0.5 * (rk[later] == rk[i]).sum()
        return float(concordant / comparable)

    # Five-year outcomes only where five years of follow-up exist (the
    # 2011-2014 cycles; linkage ends in 2019).
    full_follow_up = cycle <= 9
    dead5 = (months <= 60) & (died == 1)
    tiers = {
        "low": score <= 30,
        "moderate": (score > 30) & (score <= 65),
        "elevated": score > 65,
    }
    return report(
        "mortality",
        {
            "data": "NHANES 2011-2018 (not used to train the survival model)",
            "scored": len(rows),
            "governing_reading": {g: int((governing == g).sum()) for g in np.unique(governing)},
            "c_index_within_sex_and_age_band": round(within_band_c(score), 3),
            "c_index_plain_score": round(se.harrell_c(score, months, died), 3),
            "c_index_plain_age": round(se.harrell_c(age, months, died), 3),
            "tier_share": {k: round(float(m.mean()), 3) for k, m in tiers.items()},
            "five_year_death_rate_by_tier_2011_2014": {
                k: {
                    "n": int((m & full_follow_up).sum()),
                    "died_within_5y": round(float(dead5[m & full_follow_up].mean()), 3),
                    "mean_age": round(float(age[m & full_follow_up].mean()), 1),
                }
                for k, m in tiers.items()
            },
        },
    )


# ── standard readings: known answers ────────────────────────────────────────


def check_readings() -> dict:
    """Each expected value worked by hand from the published equation."""
    import math

    from app.arms import panel_readings as pr

    def ckd_epi_2021(scr, age, female):
        k, a = (0.7, -0.241) if female else (0.9, -0.302)
        return (
            142
            * min(scr / k, 1) ** a
            * max(scr / k, 1) ** -1.200
            * 0.9938**age
            * (1.012 if female else 1)
        )

    cases = []

    def case(name, got, want, tol):
        ok = abs(got - want) <= tol if isinstance(want, float) else got == want
        cases.append({"case": name, "got": got, "want": want, "ok": bool(ok)})

    for scr, age, sex in (
        (0.8, 40, "F"),
        (1.0, 50, "M"),
        (1.6, 70, "M"),
        (0.5, 30, "F"),
        (3.2, 62, "F"),
    ):
        case(
            f"eGFR CKD-EPI 2021 Scr {scr} age {age} {sex}",
            round(pr.egfr(scr, age, sex), 1),
            round(ckd_epi_2021(scr, age, sex == "F"), 1),
            0.15,
        )
    # Published worked example: 60 y, AST 30, ALT 25, platelets 200 -> 1.80
    case(
        "FIB-4 60y AST30 ALT25 plt200",
        round(pr.fib4(60, 30, 25, 200), 2),
        round(60 * 30 / (200 * math.sqrt(25)), 2),
        0.005,
    )
    case("FIB-4 45y AST80 ALT64 plt120", round(pr.fib4(45, 80, 64, 120), 2), 3.75, 0.005)
    case("BMI 170 cm 72 kg", round(pr.bmi(170, 72), 1), 24.9, 0.05)
    for value, want in (
        (17.0, "Underweight"),
        (22.9, "Normal"),
        (23.0, "Overweight"),
        (27.4, "Overweight"),
        (27.5, "Obese"),
    ):
        got = pr.bmi_category_asian(value)
        case(f"WHO Asian BMI {value}", got.split(" ")[0].capitalize(), want, 0)
    for value, want in (
        (95.0, "Normal"),
        (100.0, "Prediabetes"),
        (125.0, "Prediabetes"),
        (126.0, "Diabetes"),
    ):
        got = pr.glucose_category(value)
        case(
            f"ADA fasting glucose {value}",
            next(
                (w for w in ("Normal", "Prediabetes", "Diabetes") if w.lower() in got.lower()), got
            ),
            want,
            0,
        )
    return report(
        "readings", {"passed": sum(c["ok"] for c in cases), "total": len(cases), "cases": cases}
    )


# ── clinical notes against the form ─────────────────────────────────────────

NOTES = [
    # (note, declared, conditions that must be flagged, conditions that must NOT be)
    (
        (
            "Discharge summary. Known case of type 2 diabetes on metformin 500 mg twice daily "
            "and gliclazide 80 mg. Admitted with cellulitis, treated with flucloxacillin."
        ),
        {},
        {"diabetes"},
        set(),
    ),
    (
        "Discharge summary. Known case of type 2 diabetes on metformin 500 mg twice daily.",
        {"history": {"diabetes": True}},
        set(),
        {"diabetes"},
    ),
    (
        "Patient takes amlodipine 5 mg daily and atorvastatin 20 mg at night. BP 138/86.",
        {},
        {"hypertension", "high_cholesterol"},
        set(),
    ),
    (
        "No history of diabetes or hypertension. Denies tuberculosis. Mother had breast cancer.",
        {},
        set(),
        {"diabetes", "hypertension", "tuberculosis", "cancer"},
    ),
    (
        (
            "Completed six months of anti-TB treatment (rifampicin, isoniazid, pyrazinamide, "
            "ethambutol) in 2021. Sputum negative since."
        ),
        {},
        {"tuberculosis"},
        set(),
    ),
    (
        "Rx: Tab. Napa 500 mg PRN for fever. Tab. Seclo 20 mg before breakfast.",
        {},
        set(),
        {"diabetes", "hypertension"},
    ),
    (
        "On levothyroxine 50 mcg for hypothyroidism. Escitalopram 10 mg for anxiety since 2022.",
        {},
        {"thyroid", "depression_anxiety"},
        set(),
    ),
    (
        "Consider starting metformin if HbA1c rises above 6.5% at the next visit.",
        {},
        set(),
        {"diabetes"},
    ),
    (
        "Warfarin stopped last month after six months for a deep vein thrombosis.",
        {},
        {"venous_thromboembolism"},
        set(),
    ),
    (
        "Tenofovir 300 mg daily for chronic hepatitis B, viral load suppressed.",
        {},
        {"hepatitis_b"},
        set(),
    ),
    (
        "Insulin glargine 20 units at bedtime. Patient is a known diabetic.",
        {"diabetes_duration": "5-10 years"},
        set(),
        {"diabetes"},
    ),
    (
        "Salbutamol inhaler as needed and budesonide-formoterol twice daily for asthma.",
        {},
        {"asthma_copd"},
        set(),
    ),
]


def check_medication() -> dict:
    from app.arms import medication_check

    rows = []
    for note, declared, must, must_not in NOTES:
        result = medication_check.run_with_form(note.encode(), declared)
        flagged = {f["condition"] for f in result.details.get("undisclosed", [])}
        ok = must <= flagged and not (must_not & flagged)
        rows.append(
            {
                "note": note[:70] + ("..." if len(note) > 70 else ""),
                "flagged": sorted(flagged),
                "expected": sorted(must),
                "must_not": sorted(must_not),
                "score": result.score,
                "error": result.error,
                "ok": ok,
            }
        )
    return report(
        "medication", {"passed": sum(r["ok"] for r in rows), "total": len(rows), "cases": rows}
    )


# ── mammogram: Mirai ─────────────────────────────────────────────────────────


def check_mirai() -> dict:
    from app.arms import mirai

    demo = [p.read_bytes() for p in sorted((DATA / "mirai" / "demo").glob("*.dcm"))]
    published = [0.0298, 0.0483, 0.0684, 0.09, 0.1016]
    out = {}

    def stored(files):
        return [process_upload(f, "view.dcm").data for f in files]

    t = time.time()
    first = mirai.run_set(stored(demo))
    out["demo_reproduces_published"] = {
        "got": first.details.get("risk_by_year"),
        "published": published,
        "ok": first.details.get("risk_by_year") == published,
        "seconds": round(time.time() - t, 1),
        "error": first.error,
    }
    shuffled = stored(demo)[::-1]
    again = mirai.run_set(shuffled)
    out["order_of_files_does_not_matter"] = again.details.get("risk_by_year") == published
    three = mirai.run_set(stored(demo)[:3])
    out["three_views_refused"] = {"refused": three.score is None, "reason": three.error}
    dup = mirai.run_set(stored(demo)[:3] + stored(demo)[:1])
    out["duplicate_view_refused"] = {"refused": dup.score is None, "reason": dup.error}
    test_films = sorted((REPO / "Mirai" / "Test").glob("*.dcm"))
    if len(test_films) == 4:
        r = mirai.run_set(stored([p.read_bytes() for p in test_films]))
        out["second_exam"] = {"risk_by_year": r.details.get("risk_by_year"), "score": r.score}
    out["accuracy"] = (
        "not measurable here: no mammograms with follow-up outcomes are available. "
        "Published 5-year C-index 0.76-0.81 on three external sites."
    )
    return report("mirai", out)


# ── robustness: the wrong file, a blank one, noise, harmless changes ─────────


def _png(array: np.ndarray) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def _variant(raw: bytes, how: str) -> bytes:
    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(raw))
    image = image.convert("RGB") if image.mode not in ("L", "RGB") else image
    if how == "flip":
        image = ImageOps.mirror(image)
    buffer = io.BytesIO()
    if how == "jpeg":
        image.save(buffer, format="JPEG", quality=70)
    else:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def check_robustness() -> dict:
    from app import ecg

    rng = np.random.default_rng(0)
    cxr = sorted((DATA / "montgomery").glob("*.png"))
    fundus = sorted((DATA / "dr" / "idrid" / "images").glob("test_*"))
    tracings = np.load(DATA / "ecg" / "raw" / "test" / "tracings_model_units.npy", mmap_mode="r")
    blank = _png(np.zeros((512, 512, 3), np.uint8))
    grey = _png(np.full((512, 512, 3), 128, np.uint8))
    noise = _png(rng.integers(0, 255, (512, 512, 3), dtype=np.uint8))

    def attempt(arm, raw, name):
        try:
            r = read_file(arm, raw, name)
            return {"score": r.score, "error": (r.error or "")[:120] or None}
        except IntakeError as exc:
            return {"score": None, "error": f"intake: {exc}"[:120]}

    wrong = {
        "tb_xray <- fundus photo": attempt("tb_xray", fundus[0].read_bytes(), fundus[0].name),
        "dr_fundus <- chest X-ray": attempt("dr_fundus", cxr[0].read_bytes(), cxr[0].name),
    }
    junk = {}
    for arm in ("tb_xray", "dr_fundus"):
        for label, raw in (("black", blank), ("grey", grey), ("noise", noise)):
            junk[f"{arm} <- {label}"] = attempt(arm, raw, f"{label}.png")
    flat = ecg.to_bytes(np.zeros((12, ecg.LENGTH), np.float32))
    noisy = ecg.to_bytes(rng.normal(0, 0.05, (12, ecg.LENGTH)).astype(np.float32))
    junk["ecg_12lead <- flat line"] = attempt("ecg_12lead", flat, "flat.npy")
    junk["ecg_12lead <- noise 0.05 mV"] = attempt("ecg_12lead", noisy, "noise.npy")

    # Harmless changes should move a score little. Twenty files each.
    stability = {}
    for arm, files in (("tb_xray", cxr[:20]), ("dr_fundus", fundus[:20])):
        for how in ("same file twice", "flip", "jpeg"):
            deltas = []
            for f in files:
                raw = f.read_bytes()
                a = read_file(arm, raw, f.name).score
                b_raw = raw if how == "same file twice" else _variant(raw, how)
                b = read_file(
                    arm, b_raw, f.name.rsplit(".", 1)[0] + (".jpg" if how == "jpeg" else ".png")
                ).score
                if a is not None and b is not None:
                    deltas.append(abs(a - b))
            stability[f"{arm}: {how}"] = {
                "median_change": round(float(np.median(deltas)), 2),
                "max_change": round(float(np.max(deltas)), 2),
                "n": len(deltas),
            }
    deltas_amp, deltas_noise = [], []
    for i in range(0, 200, 10):
        x = np.asarray(tracings[i], dtype=np.float32) / ecg.MV_TO_MODEL
        a = read_file("ecg_12lead", ecg.to_bytes(x), "a.npy").score
        b = read_file("ecg_12lead", ecg.to_bytes(x * 1.1), "b.npy").score
        c = read_file(
            "ecg_12lead",
            ecg.to_bytes(
                x + rng.normal(0, 0.01, x.shape).astype(np.float32) * (np.abs(x).sum(0) > 0)
            ),
            "c.npy",
        ).score
        deltas_amp.append(abs(a - b))
        deltas_noise.append(abs(a - c))
    stability["ecg_12lead: amplitude +10%"] = {
        "median_change": round(float(np.median(deltas_amp)), 2),
        "max_change": round(float(np.max(deltas_amp)), 2),
        "n": len(deltas_amp),
    }
    stability["ecg_12lead: noise 0.01 mV"] = {
        "median_change": round(float(np.median(deltas_noise)), 2),
        "max_change": round(float(np.max(deltas_noise)), 2),
        "n": len(deltas_noise),
    }

    from app.triage import classify

    routed = {
        "chest X-ray": [classify(f.read_bytes(), f.name).kind for f in cxr[:10]],
        "fundus": [classify(f.read_bytes(), f.name).kind for f in fundus[:10]],
    }
    return report(
        "robustness",
        {
            "wrong_kind_of_file": wrong,
            "junk_input": junk,
            "stability": stability,
            "triage_routes": {k: sorted(set(map(str, v))) for k, v in routed.items()},
        },
    )


CHECKS = {
    "tb": lambda a: check_tb(),
    "retina": lambda a: check_retina(a.limit),
    "ecg": lambda a: check_ecg(),
    "mortality": lambda a: check_mortality(a.limit_people),
    "readings": lambda a: check_readings(),
    "medication": lambda a: check_medication(),
    "mirai": lambda a: check_mirai(),
    "robustness": lambda a: check_robustness(),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("checks", nargs="+", choices=(*CHECKS, "all"))
    parser.add_argument("--limit", type=int, default=600, help="retina images per set (0 = all)")
    parser.add_argument("--limit-people", type=int, default=0, help="NHANES adults (0 = all)")
    parser.add_argument(
        "--with-maps", action="store_true", help="draw heatmaps too (slow; never changes a score)"
    )
    args = parser.parse_args()
    if not args.with_maps:
        # A map is drawn after the score and never feeds it; the retina's alone
        # costs ~20 s a photograph. docs/HEATMAPS.md tests the maps separately.
        from app.arms import dr_fundus, ecg_12lead, tb_xray

        dr_fundus._heatmap = lambda *a, **k: None
        tb_xray._heatmap = lambda *a, **k: None
        ecg_12lead.lead_importance = lambda *a, **k: {}
    names = list(CHECKS) if "all" in args.checks else args.checks
    for name in names:
        print(f"\n== {name}", flush=True)
        CHECKS[name](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
