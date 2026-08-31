"""Does TorchXRayVision's 18-finding output contain any TB signal?

The cheapest experiment that answers the question. No GPU, no fine-tuning.

    python scripts/tb_experiment.py

What it does:

  1. Extracts the 18 finding probabilities for every labelled image (cached, so
     re-runs are instant).
  2. Scores the current hand-weighted composite as a baseline.
  3. Trains a logistic regression on those same 18 features.
  4. Reports AUC for both, on the training set (cross-validated) and on a
     completely separate hospital.

Why AUC and not accuracy: the classes are imbalanced, and accuracy on an
imbalanced set flatters a model that just predicts the majority. AUC 0.5 means
a coin flip regardless of balance.

The honest number is the **external** one — trained on Shenzhen, tested on
Montgomery. Different country, different equipment, different decade. That gap
is the finding worth reporting.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"

sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))


def label_from_filename(path: Path) -> int | None:
    """Both datasets encode the label as the last underscore-separated digit:
    CHNCXR_0001_0.png -> 0 (normal), MCUCXR_0001_1.png -> 1 (TB)."""
    tail = path.stem.rsplit("_", 1)[-1]
    return int(tail) if tail in ("0", "1") else None


def extract(dataset: str) -> tuple[list[dict], list[int]]:
    """Findings + labels for one dataset, cached to disk."""
    from app.arms import tb_xray

    folder = DATA / dataset
    cache = DATA / f"features_{dataset}.json"

    if cache.exists():
        payload = json.loads(cache.read_text())
        print(f"  {dataset}: {len(payload['labels'])} images (cached)")
        return payload["features"], payload["labels"]

    images = sorted(folder.glob("*.png"))
    if not images:
        return [], []

    features, labels = [], []
    print(f"  {dataset}: extracting from {len(images)} images ...", flush=True)
    for i, path in enumerate(images, 1):
        label = label_from_filename(path)
        if label is None:
            continue
        try:
            features.append(tb_xray.findings(path.read_bytes()))
            labels.append(label)
        except Exception as exc:
            print(f"    skipped {path.name}: {exc}")
        if i % 50 == 0:
            print(f"    {i}/{len(images)}", flush=True)

    cache.write_text(json.dumps({"features": features, "labels": labels}))
    print(f"  {dataset}: {len(labels)} images ({sum(labels)} TB, {len(labels) - sum(labels)} normal)")
    return features, labels


def to_matrix(features: list[dict], columns: list[str]):
    import numpy as np

    return np.array([[f.get(c, 0.0) for c in columns] for f in features])


def report_composite(name: str, features: list[dict], labels: list[int]) -> None:
    from sklearn.metrics import roc_auc_score

    from app.arms import tb_xray

    scores = [tb_xray.composite(f) for f in features]
    print(f"  {name:<28} AUC {roc_auc_score(labels, scores):.3f}")


def main() -> int:
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import cross_val_score
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("scikit-learn missing. Run: uv add --optional vision scikit-learn")
        return 1

    print("Extracting features\n")
    train_x, train_y = extract("shenzhen")
    test_x, test_y = extract("montgomery")

    if not train_y:
        print("\nNo Shenzhen data yet — run scripts/fetch_tb_data.py first.")
        return 1

    columns = sorted({k for f in train_x for k in f})
    print(f"\n{len(columns)} features, {len(train_y)} training images\n")

    print("BASELINE — current hand-weighted composite")
    report_composite("shenzhen (in-sample)", train_x, train_y)
    if test_y:
        report_composite("montgomery (external)", test_x, test_y)

    print("\nLEARNED — logistic regression on the same 18 features")
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))

    xs = to_matrix(train_x, columns)
    cv = cross_val_score(model, xs, train_y, cv=5, scoring="roc_auc")
    print(f"  {'shenzhen (5-fold CV)':<28} AUC {cv.mean():.3f}  (+/- {cv.std():.3f})")

    model.fit(xs, train_y)

    if test_y:
        external = roc_auc_score(test_y, model.predict_proba(to_matrix(test_x, columns))[:, 1])
        print(f"  {'montgomery (external)':<28} AUC {external:.3f}   <-- the honest number")

    print("\nStrongest learned weights")
    coefs = model.named_steps["logisticregression"].coef_[0]
    ranked = sorted(zip(columns, coefs, strict=True), key=lambda kv: -abs(kv[1]))
    for name, weight in ranked[:8]:
        direction = "TB" if weight > 0 else "normal"
        print(f"  {name:<24} {weight:+.3f}  -> {direction}")

    export(model, columns, cv, len(train_y))
    return 0


def export(model, columns: list[str], cv, n_images: int) -> None:
    """Write the fitted model as plain JSON next to the arm that loads it.

    Not a pickle, deliberately. A logistic regression over 18 features is 18
    weights, an intercept and the scaler's mean/scale — small enough to read,
    diff and review. Pickles break across library versions and hide what the
    model does; this file can be inspected in a code review.

    It also means the arm needs **numpy only** at runtime, not scikit-learn:
    the prediction is one dot product and a sigmoid.
    """
    import datetime as dt

    scaler = model.named_steps["standardscaler"]
    logistic = model.named_steps["logisticregression"]

    target = REPO_ROOT / "apps" / "api" / "app" / "arms" / "tb_xray_model.json"
    target.write_text(
        json.dumps(
            {
                "model": "logistic_regression_on_txrv_findings",
                "version": "1.0.0",
                "trained_on": "shenzhen",
                "trained_at": dt.date.today().isoformat(),
                "n_images": n_images,
                "cv_auc_mean": round(float(cv.mean()), 4),
                "cv_auc_std": round(float(cv.std()), 4),
                "validation": "internal 5-fold cross-validation; NOT externally validated",
                "features": columns,
                "mean": [round(float(v), 6) for v in scaler.mean_],
                "scale": [round(float(v), 6) for v in scaler.scale_],
                "coef": [round(float(v), 6) for v in logistic.coef_[0]],
                "intercept": round(float(logistic.intercept_[0]), 6),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {target.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
