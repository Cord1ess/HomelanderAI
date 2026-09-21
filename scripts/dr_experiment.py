"""Can a frozen retina backbone plus a small trained head grade diabetic retinopathy?

The retina counterpart of `tb_experiment.py`, and built the same way on purpose:
a published backbone turns the image into features, a logistic regression turns
the features into a score, and the score is judged on a hospital the model has
never seen.

    python scripts/dr_experiment.py features <backbone> <dataset> [--limit N]
    python scripts/dr_experiment.py compare  [--limit N]
    python scripts/dr_experiment.py train    <backbone>

Why frozen features and not fine-tuning: measured on this machine a ResNet-50
trains at 0.9 images a second, so ten epochs over even a small dataset is eleven
hours. Extracting features is a single inference pass per image and is cached,
so everything after the first run is instant.

Why these datasets (see `fetch_dr_data.py` for where they come from):

  ddr        TRAIN. 12,522 gradable photographs from 147 hospitals and 42 camera
             types, so there is no single-site shortcut for a model to find.
  aptos      external test. India. Never train on it: the resolution of an APTOS
             image predicts its label on its own (about 91% on DR vs no DR), the
             same trap as the Kaggle TB set. That cannot help a model that has
             never seen APTOS, which is what makes it a fair test.
  idrid      external test. India, one clinic, one camera. Small (516).
  deepdrid   external test. Shanghai screening programme.

**Contamination decides which numbers are honest.** A backbone that was
pretrained on a dataset has seen its test images, so a score on that dataset
says nothing about new patients:

  retfound_green   saw DDR without labels. Clean on aptos, idrid, deepdrid.
  flair            saw DDR, APTOS and IDRiD-train *with their grades*.
                   Clean only on deepdrid and the 103-image IDRiD test split.
  dinov2           natural images only. Clean everywhere; the baseline that
                   shows whether retina pretraining bought anything.

The headline metric is AUC for **referable DR** (ICDR grade 2 or worse), the
screening decision every regulated system is judged on. Grading agreement is
reported as quadratic-weighted kappa.

`flair` is what the platform ships, and needs nothing beyond the vision extra.
The other two exist only to re-run the comparison that chose it, and need timm,
which is deliberately not a project dependency:

    uv pip install timm
"""

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data" / "dr"
FEATURES = DATA / "features"
MODELS = DATA / "models"

sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

DATASETS = ("ddr", "aptos", "idrid", "deepdrid")
REFERABLE_FROM = 2  # ICDR: 0 none, 1 mild, 2 moderate, 3 severe, 4 proliferative


# ── backbones ────────────────────────────────────────────────────────────────
#
# Each returns (model, input_size, mean, std). Only the one the platform ships
# also exists in `app/arms/`; the others live here so the comparison that chose
# it can be re-run.


def _retfound_green():
    import timm
    import torch

    model = timm.create_model(
        "vit_small_patch14_reg4_dinov2", img_size=(392, 392), num_classes=0
    )
    state = torch.load(MODELS / "retfoundgreen_statedict.pth", map_location="cpu")
    model.load_state_dict(state)
    model.global_pool = "avg"
    return model.eval(), 392, (0.5, 0.5, 0.5), (0.5, 0.5, 0.5)


def _dinov2():
    import timm

    model = timm.create_model(
        "vit_small_patch14_reg4_dinov2.lvd142m",
        pretrained=True,
        img_size=(392, 392),
        num_classes=0,
    )
    return model.eval(), 392, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


def _flair():
    """The backbone the platform ships, loaded by the arm's own code so the
    features trained on are the features served. FLAIR takes raw [0, 1] pixels:
    no mean, no standard deviation."""
    from app.arms import dr_fundus

    return dr_fundus._get_model(), dr_fundus.INPUT_SIZE, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)


BACKBONES = {"retfound_green": _retfound_green, "flair": _flair, "dinov2": _dinov2}


# ── data ─────────────────────────────────────────────────────────────────────


def read_labels(dataset: str) -> list[dict]:
    """Rows of {image, grade, split} written by `fetch_dr_data.py`."""
    path = DATA / dataset / "labels.csv"
    if not path.exists():
        raise SystemExit(f"{path} is missing. Run: python scripts/fetch_dr_data.py {dataset}")
    with open(path, newline="") as handle:
        return [
            {"image": r["image"], "grade": int(r["grade"]), "split": r["split"]}
            for r in csv.DictReader(handle)
        ]


def subsample(rows: list[dict], limit: int | None) -> list[dict]:
    """A fixed, grade-stratified subset, so a quick comparison is repeatable."""
    if not limit or limit >= len(rows):
        return rows
    rng = np.random.default_rng(0)
    keep: list[dict] = []
    for grade in sorted({r["grade"] for r in rows}):
        group = [r for r in rows if r["grade"] == grade]
        take = max(1, round(limit * len(group) / len(rows)))
        keep += [group[i] for i in rng.permutation(len(group))[:take]]
    return keep


def extract(backbone: str, dataset: str, limit: int | None = None) -> dict:
    """Features for one dataset through one backbone, cached on disk."""
    import torch

    from app.arms.fundus import NotAFundusPhoto, frame

    tag = f"{backbone}__{dataset}" + (f"__{limit}" if limit else "")
    cache = FEATURES / f"{tag}.npz"
    if cache.exists():
        loaded = np.load(cache, allow_pickle=False)
        print(f"  {tag}: {len(loaded['grades'])} images (cached)")
        return {k: loaded[k] for k in loaded.files}

    rows = subsample(read_labels(dataset), limit)
    model, size, mean, std = BACKBONES[backbone]()
    mean_t = torch.tensor(mean).view(1, 3, 1, 1)
    std_t = torch.tensor(std).view(1, 3, 1, 1)

    from PIL import Image

    def load(row: dict):
        try:
            with Image.open(DATA / dataset / "images" / row["image"]) as handle:
                framed = frame(handle, size)
            return np.asarray(framed.image, dtype=np.float32) / 255.0
        except (NotAFundusPhoto, OSError) as exc:
            print(f"    skipped {row['image']}: {exc}")
            return None

    features, kept = [], []
    started = time.perf_counter()
    batch_size = 16
    print(f"  {tag}: extracting {len(rows)} images ...", flush=True)

    # Decoding a 12-megapixel JPEG costs about as much as the forward pass, and
    # PIL releases the GIL while it does it, so the two overlap on threads.
    with ThreadPoolExecutor(max_workers=6) as pool:
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            arrays = list(pool.map(load, chunk))
            good = [(r, a) for r, a in zip(chunk, arrays, strict=True) if a is not None]
            if not good:
                continue
            batch = torch.from_numpy(np.stack([a for _, a in good])).permute(0, 3, 1, 2)
            with torch.inference_mode():
                out = model((batch - mean_t) / std_t)
            features.append(out.float().numpy())
            kept += [r for r, _ in good]

            done = start + len(chunk)
            if done % (batch_size * 10) == 0 or done == len(rows):
                rate = done / (time.perf_counter() - started)
                eta = (len(rows) - done) / rate / 60
                print(f"    {done}/{len(rows)}  {rate:.1f} img/s  ~{eta:.0f} min left", flush=True)

    payload = {
        "X": np.concatenate(features),
        "grades": np.array([r["grade"] for r in kept], dtype=np.int64),
        "splits": np.array([r["split"] for r in kept]),
        "names": np.array([r["image"] for r in kept]),
    }
    FEATURES.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **payload)
    return payload


# ── the head ─────────────────────────────────────────────────────────────────


def fit_heads(x: np.ndarray, grades: np.ndarray, c: float = 0.1):
    """Two logistic regressions on standardised features.

    One answers the screening question directly (referable or not) and sets the
    score. The other grades on the five-point ICDR scale, for the underwriter to
    read. Trained separately because a model asked only the binary question
    answers it better than one that has to spread its capacity over five.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    referable = make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=5000))
    referable.fit(x, grades >= REFERABLE_FROM)

    grading = make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=5000))
    grading.fit(x, grades)
    return referable, grading


def choose_c(data: dict) -> float:
    """How hard to regularise, chosen on DDR's validation split.

    Never on the test split, and never on an external set: a setting tuned on
    the data it is then reported on is no longer a test of anything.
    """
    from sklearn.metrics import roc_auc_score

    train = data["splits"] == "train"
    valid = data["splits"] == "valid"
    truth = data["grades"][valid] >= REFERABLE_FROM

    best, best_auc = 0.1, -1.0
    for c in (0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3):
        referable, _ = fit_heads(data["X"][train], data["grades"][train], c)
        auc = roc_auc_score(truth, referable.predict_proba(data["X"][valid])[:, 1])
        print(f"    C={c:<6} validation AUC {auc:.4f}")
        if auc > best_auc:
            best, best_auc = c, auc
    print(f"  chose C={best}")
    return best


def report(name: str, referable, grading, x: np.ndarray, grades: np.ndarray) -> dict:
    from sklearn.metrics import cohen_kappa_score, roc_auc_score

    truth = grades >= REFERABLE_FROM
    probability = referable.predict_proba(x)[:, 1]
    auc = float(roc_auc_score(truth, probability))
    kappa = float(cohen_kappa_score(grades, grading.predict(x), weights="quadratic"))

    # The two cut-points the platform actually acts on (scoring.Thresholds).
    points = {}
    for label, cut in (("moderate_or_above", 0.30), ("elevated", 0.65)):
        flagged = probability > cut
        points[label] = {
            "sensitivity": round(float((flagged & truth).sum() / max(truth.sum(), 1)), 4),
            "specificity": round(float((~flagged & ~truth).sum() / max((~truth).sum(), 1)), 4),
        }

    low, high = bootstrap_auc(truth, probability)
    print(
        f"  {name:<24} n={len(grades):>5}  referable AUC {auc:.3f} [{low:.3f}-{high:.3f}]"
        f"  kappa {kappa:.3f}  "
        f"@30 sens {points['moderate_or_above']['sensitivity']:.2f}"
        f"/spec {points['moderate_or_above']['specificity']:.2f}  "
        f"@65 sens {points['elevated']['sensitivity']:.2f}"
        f"/spec {points['elevated']['specificity']:.2f}"
    )
    return {
        "n": int(len(grades)),
        "referable_prevalence": round(float(truth.mean()), 4),
        "auc_referable": round(auc, 4),
        "auc_ci95": [round(low, 4), round(high, 4)],
        "quadratic_kappa": round(kappa, 4),
        "operating_points": points,
    }


def bootstrap_auc(truth: np.ndarray, score: np.ndarray, rounds: int = 500):
    """A 95% interval, because 0.93 on 103 images and 0.93 on 3,662 are not the
    same claim and a bare number hides which one is being made."""
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(0)
    values = []
    for _ in range(rounds):
        index = rng.integers(0, len(truth), len(truth))
        if truth[index].min() == truth[index].max():
            continue
        values.append(roc_auc_score(truth[index], score[index]))
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


# ── commands ─────────────────────────────────────────────────────────────────

# Which external sets each backbone has never seen. Anything else is printed,
# but marked, and never goes in the model file.
CLEAN = {
    "retfound_green": {"aptos", "idrid", "deepdrid"},
    "dinov2": {"ddr", "aptos", "idrid", "deepdrid"},
    "flair": {"deepdrid", "idrid:test"},
}


def evaluate(backbone: str, limit: int | None, datasets: tuple[str, ...]) -> dict:
    train = extract(backbone, "ddr", limit)
    fit = np.isin(train["splits"], ("train", "valid"))
    held = train["splits"] == "test"

    print(f"\n{backbone}")
    c = choose_c(train)
    # Validation has done its job once C is chosen, so it goes back into the
    # training pool: 2,503 more photographs is worth more than keeping it aside.
    referable, grading = fit_heads(train["X"][fit], train["grades"][fit], c)

    # DDR's test split is held out from our head, but FLAIR's pretraining used
    # those very photographs with their grades. It is printed for completeness
    # and is not evidence of anything.
    internal = "internal" if "ddr" in CLEAN[backbone] else "internal, SEEN IN PRETRAINING"
    results = {
        "ddr_test": report(
            f"ddr test ({internal})", referable, grading, train["X"][held], train["grades"][held]
        )
    }
    results["ddr_test"]["clean"] = "ddr" in CLEAN[backbone]
    for dataset in datasets:
        if not (DATA / dataset / "labels.csv").exists():
            print(f"  {dataset:<24} not downloaded, skipped")
            continue
        data = extract(backbone, dataset, limit)
        clean = dataset in CLEAN[backbone]
        note = "external" if clean else "SEEN IN PRETRAINING"
        results[dataset] = report(
            f"{dataset} ({note})", referable, grading, data["X"], data["grades"]
        )
        results[dataset]["clean"] = clean

        # Where the graders also said whether a photograph was fit to read, say
        # how much a poor one costs. An aggregate hides that, and it is the
        # number that tells an underwriter how far to trust a blurry upload.
        quality_file = DATA / dataset / "quality.csv"
        if quality_file.exists():
            with open(quality_file, newline="") as handle:
                good_names = [r["image"] for r in csv.DictReader(handle) if r["good"] == "1"]
            good = np.isin(data["names"], good_names)
            for label, part in (("good", good), ("poor", ~good)):
                key = f"{dataset}_{label}_quality"
                results[key] = report(
                    f"  of which {label} photographs",
                    referable, grading, data["X"][part], data["grades"][part],
                )
                results[key]["clean"] = clean

        if f"{dataset}:test" in CLEAN[backbone]:
            part = data["splits"] == "test"
            results[f"{dataset}_test"] = report(
                f"{dataset} test split (external)",
                referable, grading, data["X"][part], data["grades"][part],
            )
            results[f"{dataset}_test"]["clean"] = True
    return {
        "results": results,
        "referable": referable,
        "grading": grading,
        "c": c,
        "n_train": int(fit.sum()),
    }


CLASSES = ["No DR", "Mild NPDR", "Moderate NPDR", "Severe NPDR", "Proliferative DR"]

NAMES = {"deepdrid": "DeepDRiD (Shanghai)", "idrid_test": "IDRiD test split (India)"}


def folded(pipeline) -> tuple[np.ndarray, np.ndarray]:
    """The scaler folded into the weights, so serving is one dot product.

    (x - mean) / scale . w + b   ==   x . (w / scale) + (b - mean/scale . w)
    """
    scaler = pipeline.named_steps["standardscaler"]
    logistic = pipeline.named_steps["logisticregression"]
    coef = logistic.coef_ / scaler.scale_
    intercept = logistic.intercept_ - coef @ scaler.mean_
    return coef, intercept


def export(outcome: dict) -> None:
    """Write the fitted heads next to the arm that loads them.

    Plain JSON, not a pickle, for the same reasons as the chest model: it can be
    diffed and reviewed, it does not break across scikit-learn versions, and the
    arm needs only numpy to run it. The metrics are written into the same file
    so the claim and the weights it describes can never drift apart.
    """
    import datetime as dt

    results = outcome["results"]

    # Only results on photographs the backbone never saw count as validation.
    # This sentence is shown on the intake form and beside every score.
    quoted = [k for k in NAMES if results.get(k, {}).get("clean")]
    parts = [
        f"{NAMES[k]} AUC {results[k]['auc_referable']:.3f} (n={results[k]['n']:,})"
        for k in quoted
    ]
    validation = (
        "referable-DR screen; externally tested on hospitals the model never saw: "
        + "; ".join(parts)
        + ". NOT clinically validated"
    )

    binary_coef, binary_intercept = folded(outcome["referable"])
    grading_coef, grading_intercept = folded(outcome["grading"])

    def compact(values) -> str:
        return json.dumps(np.round(values, 6).tolist(), separators=(",", ":"))

    spec = {
        "model": "logistic_regression_on_flair_features",
        "version": "1.0.0",
        "backbone": "flair-resnet50",
        "trained_on": "ddr",
        "trained_at": dt.date.today().isoformat(),
        "n_images": outcome["n_train"],
        "regularisation_c": outcome["c"],
        "referable_from_grade": REFERABLE_FROM,
        "validation": validation,
        # Which entries under `metrics` the sentence above is quoting, so a test
        # can hold the claim to the numbers.
        "validated_on": quoted,
        "classes": CLASSES,
        "metrics": results,
        "referable": {"coef": "@binary_coef", "intercept": round(float(binary_intercept[0]), 6)},
        "grading": {"coef": "@grading_coef", "intercept": "@grading_intercept"},
    }

    # Pretty-printed metadata, one line per weight vector. Twelve thousand
    # numbers at one per line would bury the part a reviewer needs to read.
    text = json.dumps(spec, indent=2)
    text = text.replace('"@binary_coef"', compact(binary_coef[0]))
    text = text.replace('"@grading_coef"', compact(grading_coef))
    text = text.replace('"@grading_intercept"', compact(grading_intercept))

    target = REPO_ROOT / "apps" / "api" / "app" / "arms" / "dr_fundus_model.json"
    target.write_text(text + "\n")
    print(f"\nwrote {target.relative_to(REPO_ROOT)}  ({target.stat().st_size / 1024:.0f} KB)")
    print(f"validation: {validation}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("features", "compare", "train"))
    parser.add_argument("backbone", nargs="?", choices=tuple(BACKBONES))
    parser.add_argument("dataset", nargs="?", choices=DATASETS)
    parser.add_argument("--limit", type=int, default=None, help="images per dataset")
    args = parser.parse_args()

    if args.command == "features":
        if not (args.backbone and args.dataset):
            parser.error("features needs a backbone and a dataset")
        extract(args.backbone, args.dataset, args.limit)
        return 0

    if args.command == "compare":
        for backbone in BACKBONES:
            evaluate(backbone, args.limit, ("idrid", "deepdrid", "aptos"))
        return 0

    if not args.backbone:
        parser.error("train needs a backbone")
    outcome = evaluate(args.backbone, args.limit, ("deepdrid", "idrid", "aptos"))
    if args.backbone == "flair":
        export(outcome)
    else:
        print("\nnot exported: only the backbone the platform ships writes a model file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
