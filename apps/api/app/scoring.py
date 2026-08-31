"""Composite Risk Score: turn model findings plus declared history into a
number, a tier, and the reasons behind both.

Kept free of any database or framework import so it can be tested on its own.

The rules live in one list. Adding a condition later is one entry, not a new
branch in a function — that is the whole reason this is a list of data rather
than a chain of ifs.

The two prior-TB rules carry the point of the product: the same chest X-ray
means opposite things depending on treatment history, and an image model alone
can never know that.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

# Declared history keys the rules read. Kept here so a typo in a rule predicate
# fails a test rather than silently never firing.
SYMPTOM_KEYS = (
    "cough_over_2_weeks",
    "weight_loss",
    "night_sweats",
    "haemoptysis",
    "fever",
)


@dataclass(frozen=True)
class Thresholds:
    """Tier cut-points. Snapshotted onto every score so an old result can still
    be explained after the thresholds are re-tuned."""

    low_max: float = 30.0
    moderate_max: float = 65.0

    def as_dict(self) -> dict[str, float]:
        return {"low_max": self.low_max, "moderate_max": self.moderate_max}


@dataclass(frozen=True)
class Rule:
    key: str
    points: float
    reason: str
    applies: Callable[[dict, int | None], bool]


@dataclass(frozen=True)
class Adjustment:
    """One rule that fired. `reason` is shown verbatim to the underwriter."""

    key: str
    points: float
    reason: str


@dataclass
class ScoreResult:
    crs: float | None
    tier: str
    vision_component: float | None
    adjustments: list[Adjustment] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def total_adjustment(self) -> float:
        return sum(a.points for a in self.adjustments)


# ── helpers the rules are built from ─────────────────────────────────────────


def _symptoms(declared: dict) -> list[str]:
    sym = declared.get("symptoms") or {}
    return [k for k in SYMPTOM_KEYS if sym.get(k)]


def _has(declared: dict, key: str) -> bool:
    return bool((declared.get("history") or {}).get(key))


# ── the rules ────────────────────────────────────────────────────────────────
#
# Order matters only for display. Points are additive.

RULES: list[Rule] = [
    Rule(
        key="prior_tb_scarring",
        points=-25.0,
        reason=(
            "Previously treated for TB, course completed, and no current symptoms — "
            "imaging findings are consistent with post-treatment scarring rather than "
            "active disease"
        ),
        applies=lambda d, age: (
            _has(d, "prior_tb")
            and _has(d, "prior_tb_treatment_completed")
            and not _symptoms(d)
        ),
    ),
    Rule(
        key="prior_tb_relapse",
        points=25.0,
        reason=(
            "Previously treated for TB and currently symptomatic — possible relapse, "
            "which also raises the question of drug resistance"
        ),
        applies=lambda d, age: _has(d, "prior_tb") and bool(_symptoms(d)),
    ),
    Rule(
        key="haemoptysis",
        points=12.0,
        reason="Coughing up blood — a red flag for active disease",
        applies=lambda d, age: (d.get("symptoms") or {}).get("haemoptysis", False),
    ),
    Rule(
        key="multiple_symptoms",
        points=10.0,
        reason="Two or more current symptoms associated with active TB",
        applies=lambda d, age: len(_symptoms(d)) >= 2,
    ),
    Rule(
        key="hiv",
        points=15.0,
        reason="HIV positive — a major risk multiplier, and presentations are often atypical",
        applies=lambda d, age: _has(d, "hiv"),
    ),
    Rule(
        key="diabetes",
        points=10.0,
        reason="Diabetes — associated with roughly three times the TB risk",
        applies=lambda d, age: _has(d, "diabetes"),
    ),
    Rule(
        key="household_tb_contact",
        points=10.0,
        reason="Household TB contact — documented exposure",
        applies=lambda d, age: _has(d, "household_tb_contact"),
    ),
    Rule(
        key="antibiotics_no_improvement",
        points=10.0,
        reason=(
            "Completed a course of antibiotics without improvement — argues against "
            "bacterial pneumonia"
        ),
        applies=lambda d, age: _has(d, "antibiotics_no_improvement"),
    ),
    Rule(
        key="smoker",
        points=5.0,
        reason="Current or former smoker — widens the differential toward malignancy",
        applies=lambda d, age: _has(d, "smoker"),
    ),
    Rule(
        key="age_over_60",
        points=5.0,
        reason="Age over 60 — widens the differential toward malignancy",
        applies=lambda d, age: age is not None and age > 60,
    ),
]


# ── public API ───────────────────────────────────────────────────────────────

INSUFFICIENT = "insufficient_evidence"


def tier_for(crs: float, thresholds: Thresholds | None = None) -> str:
    t = thresholds or Thresholds()
    if crs <= t.low_max:
        return "low"
    if crs <= t.moderate_max:
        return "moderate"
    return "elevated"


def score(
    vision_score: float | None,
    declared_history: dict | None = None,
    age: int | None = None,
    thresholds: Thresholds | None = None,
) -> ScoreResult:
    """Combine the vision arm's score with declared history.

    `vision_score` is 0-100, or None when the arm produced nothing usable. A
    missing vision score is not a zero — it means we cannot score at all, and
    the application needs more evidence.
    """
    t = thresholds or Thresholds()
    declared = declared_history or {}

    if vision_score is None:
        return ScoreResult(
            crs=None,
            tier=INSUFFICIENT,
            vision_component=None,
            adjustments=[],
            thresholds=t,
        )

    applied = [
        Adjustment(r.key, r.points, r.reason)
        for r in RULES
        if r.applies(declared, age)
    ]

    crs = vision_score + sum(a.points for a in applied)
    crs = max(0.0, min(100.0, crs))

    return ScoreResult(
        crs=round(crs, 2),
        tier=tier_for(crs, t),
        vision_component=round(vision_score, 2),
        adjustments=applied,
        thresholds=t,
    )
