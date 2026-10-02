"""The TB arm's external number: the shipped model, on a hospital it never saw.

    uv run --directory apps/api python ../../scripts/tb_external.py

Runs every Montgomery County film through the same path an application takes
— `intake.process_upload`, then `tb_xray.run` — and reports the AUC. Nothing
is trained or written: this measures the model in `tb_xray_model.json` as it
ships, which `tb_experiment.py` cannot do because it retrains and overwrites it.

Montgomery is the right test because it differs in everything the model could
have latched onto: another country (USA, not China), other equipment, another
decade, and its labels come from a different programme. The model was trained
on Shenzhen alone. Fetch with `python scripts/fetch_tb_data.py montgomery`.

Also prints the operating point at the platform's tier boundaries, because an
AUC says the ranking is good and nothing about whether the cut-points that
decide an applicant's tier still mean the same thing on new data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.arms import tb_xray  # noqa: E402
from app.intake import process_upload  # noqa: E402

FOLDER = REPO / "data" / "montgomery"
CACHE = REPO / "data" / "montgomery_scores.json"


def label_of(path: Path) -> int:
    """MCUCXR_0001_0.png -> 0 (normal), MCUCXR_0104_1.png -> 1 (TB)."""
    return int(path.stem.rsplit("_", 1)[1])


def auc(labels: list[int], scores: list[float]) -> float:
    """Mann-Whitney AUC, ties counted half. No scikit-learn needed."""
    pos = [s for s, y in zip(scores, labels, strict=True) if y == 1]
    neg = [s for s, y in zip(scores, labels, strict=True) if y == 0]
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def bootstrap_ci(labels: list[int], scores: list[float], n: int = 2000) -> tuple[float, float]:
    import random

    rng = random.Random(0)
    pairs = list(zip(labels, scores, strict=True))
    estimates = []
    for _ in range(n):
        sample = [rng.choice(pairs) for _ in pairs]
        ys = [y for y, _ in sample]
        if 0 < sum(ys) < len(ys):
            estimates.append(auc(ys, [s for _, s in sample]))
    estimates.sort()
    return estimates[int(0.025 * len(estimates))], estimates[int(0.975 * len(estimates))]


def main() -> int:
    films = sorted(FOLDER.glob("*.png"))
    if len(films) != 138:
        print(f"expected 138 Montgomery films in {FOLDER}, found {len(films)}")
        print("run: python scripts/fetch_tb_data.py montgomery")
        return 1

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for i, film in enumerate(films, 1):
        if film.name in cache:
            continue
        result = tb_xray.run(process_upload(film.read_bytes(), film.name).data)
        if result.score is None:
            print(f"  {film.name}: no score — {result.error}")
            continue
        cache[film.name] = result.score
        if i % 10 == 0:
            CACHE.write_text(json.dumps(cache))
            print(f"  {i}/{len(films)}")
    CACHE.write_text(json.dumps(cache))

    names = [f.name for f in films if f.name in cache]
    labels = [label_of(Path(n)) for n in names]
    scores = [cache[n] for n in names]
    lo, hi = bootstrap_ci(labels, scores)

    print(f"\nMontgomery (external): {sum(labels)} TB, {len(labels) - sum(labels)} normal")
    print(f"  AUC {auc(labels, scores):.3f}   95% CI {lo:.3f}-{hi:.3f}")

    print("\nAt the platform's tier boundaries:")
    for cut in (30.0, 65.0):
        tp = sum(1 for s, y in zip(scores, labels, strict=True) if s > cut and y == 1)
        tn = sum(1 for s, y in zip(scores, labels, strict=True) if s <= cut and y == 0)
        p, n = sum(labels), len(labels) - sum(labels)
        print(f"  score > {cut:4.0f}   sensitivity {tp / p:.2f}   specificity {tn / n:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
