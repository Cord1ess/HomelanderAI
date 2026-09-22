"""Scoring rules.

The headline test is `test_same_image_opposite_conclusion` — it is the behaviour
the whole product exists to demonstrate.
"""

import pytest

from app.scoring import (
    INSUFFICIENT,
    RULES,
    SYMPTOM_KEYS,
    Thresholds,
    score,
    tier_for,
)


def history(**flags) -> dict:
    """Build a declared-history payload, splitting symptom keys from history keys
    the way the intake form posts them."""
    sym = {k: v for k, v in flags.items() if k in SYMPTOM_KEYS}
    hist = {k: v for k, v in flags.items() if k not in SYMPTOM_KEYS}
    return {"symptoms": sym, "history": hist}


# ── the case that justifies the product ──────────────────────────────────────


def test_same_image_opposite_conclusion():
    """Identical imaging, opposite conclusions, driven only by history.

    An image classifier cannot do this, because it never sees the history.
    """
    vision = 62.0

    untreated = score(vision, history())
    scarring = score(
        vision,
        history(prior_tb=True, prior_tb_treatment_completed=True),
    )

    assert untreated.crs == 62.0
    assert untreated.tier == "moderate"

    # -25 points applied to the 62 already there: 62 - 25 * 0.62.
    assert scarring.crs == 46.5
    assert scarring.tier == "moderate"
    assert scarring.crs < untreated.crs

    # The reason must be legible to an underwriter, not just a key.
    assert any("scarring" in a.reason for a in scarring.adjustments)


def test_prior_tb_with_symptoms_raises_instead():
    """Same prior-TB history, but symptomatic — relapse, not scarring."""
    vision = 50.0

    scarring = score(vision, history(prior_tb=True, prior_tb_treatment_completed=True))
    relapse = score(
        vision,
        history(prior_tb=True, prior_tb_treatment_completed=True, cough_over_2_weeks=True),
    )

    assert scarring.crs < vision < relapse.crs
    # +25 on the 50 points of room left: 50 + 25 * 0.5. History refines the
    # evidence; it does not turn an ambiguous film into a certainty on its own.
    assert relapse.crs == 62.5
    assert relapse.tier == "moderate"


def test_scarring_and_relapse_are_mutually_exclusive():
    """Both rules read prior_tb. They must never fire together."""
    for flags in (
        history(prior_tb=True, prior_tb_treatment_completed=True),
        history(prior_tb=True, prior_tb_treatment_completed=True, fever=True),
        history(prior_tb=True, fever=True),
    ):
        keys = {a.key for a in score(50.0, flags).adjustments}
        assert not {"prior_tb_scarring", "prior_tb_relapse"} <= keys


# ── insufficient evidence ────────────────────────────────────────────────────


def test_no_vision_score_is_insufficient_not_zero():
    """A missing arm result must never be scored as a harmless zero."""
    result = score(None, history(hiv=True))

    assert result.crs is None
    assert result.tier == INSUFFICIENT
    assert result.vision_component is None
    assert result.adjustments == []


def test_insufficient_ignores_history_entirely():
    """With no imaging there is nothing to adjust, however alarming the history."""
    result = score(None, history(prior_tb=True, hiv=True, haemoptysis=True))
    assert result.crs is None


# ── arithmetic ───────────────────────────────────────────────────────────────


def test_no_history_leaves_score_untouched():
    assert score(41.0, history()).crs == 41.0
    assert score(41.0, None).crs == 41.0
    assert score(41.0, {}).crs == 41.0


def test_score_is_clamped_to_range():
    piled_on = history(
        hiv=True,
        diabetes=True,
        household_tb_contact=True,
        antibiotics_no_improvement=True,
        smoker=True,
        haemoptysis=True,
        fever=True,
        night_sweats=True,
    )
    # Every positive rule at once is 77 points, capped at 30, applied to the 5
    # points of room left: 95 + 30 * 0.05. Piling on history approaches 100 and
    # never reaches it; only the readers themselves can go that high.
    piled = score(95.0, piled_on, age=70).crs
    assert piled == 96.5
    assert piled < 100.0

    # And a downgrade scales with what is there: -25 on 5 takes off 1.25.
    low = score(5.0, history(prior_tb=True, prior_tb_treatment_completed=True)).crs
    assert low == 3.75
    assert low >= 0.0


@pytest.mark.parametrize(
    ("crs", "expected"),
    [
        (0.0, "low"),
        (30.0, "low"),
        (30.01, "moderate"),
        (65.0, "moderate"),
        (65.01, "elevated"),
        (100.0, "elevated"),
    ],
)
def test_tier_boundaries(crs, expected):
    assert tier_for(crs) == expected


def test_thresholds_are_configurable_and_snapshotted():
    strict = Thresholds(low_max=10.0, moderate_max=40.0)
    result = score(45.0, history(), thresholds=strict)

    assert result.tier == "elevated"
    assert result.thresholds.as_dict() == {"low_max": 10.0, "moderate_max": 40.0}


def test_age_rule_only_fires_when_age_known():
    assert "age_over_60" not in {a.key for a in score(50.0, history()).adjustments}
    assert "age_over_60" not in {a.key for a in score(50.0, history(), age=59).adjustments}
    assert "age_over_60" in {a.key for a in score(50.0, history(), age=61).adjustments}


# ── invariants ───────────────────────────────────────────────────────────────


def test_no_outcome_is_ever_a_denial():
    """The platform never denies anyone. Escalation to a human is the only path
    out of a high score. Asserted here so it cannot regress silently."""
    allowed = {"low", "moderate", "elevated", INSUFFICIENT}

    for vision in (None, 0.0, 25.0, 50.0, 75.0, 100.0):
        for flags in (history(), history(hiv=True), history(prior_tb=True)):
            assert score(vision, flags).tier in allowed


def test_rule_keys_are_unique():
    keys = [r.key for r in RULES]
    assert len(keys) == len(set(keys))


def test_every_rule_can_actually_fire():
    """Guards against a predicate reading a misspelled key — it would silently
    never fire, and no other test would notice."""
    triggers = {
        "prior_tb_scarring": (history(prior_tb=True, prior_tb_treatment_completed=True), None),
        "prior_tb_relapse": (history(prior_tb=True, fever=True), None),
        "haemoptysis": (history(haemoptysis=True), None),
        "multiple_symptoms": (history(fever=True, night_sweats=True), None),
        "hiv": (history(hiv=True), None),
        "diabetes": (history(diabetes=True), None),
        "household_tb_contact": (history(household_tb_contact=True), None),
        "antibiotics_no_improvement": (history(antibiotics_no_improvement=True), None),
        "smoker": (history(smoker=True), None),
        "age_over_60": (history(), 70),
        "diabetes_duration_over_10_years": ({"diabetes_duration": "Over 10 years"}, None),
        "diabetes_duration_5_to_10_years": ({"diabetes_duration": "5–10 years"}, None),
        "diabetes_with_hypertension": ({"hypertension": True}, None),
    }

    assert set(triggers) == {r.key for r in RULES}, "a rule has no trigger case"

    for rule in RULES:
        declared, age = triggers[rule.key]
        fired = {a.key for a in score(50.0, declared, age=age).adjustments}
        assert rule.key in fired, f"rule {rule.key!r} never fires"


# ── fusing the readers ───────────────────────────────────────────────────────


def test_fusion_accumulates_with_diminishing_returns():
    """One certain reading is elevated, not a verdict; more positives add less
    each time and never reach 100; a clean reading never lowers a concerning one."""
    from app.scoring import fuse

    assert fuse([]) == 0.0
    assert fuse([0.0]) == 0.0
    assert fuse([100.0]) == 75.0
    assert fuse([100.0, 100.0]) == 93.75
    assert fuse([100.0, 100.0, 100.0]) < 100.0
    assert fuse([100.0, 100.0, 100.0, 100.0, 100.0]) < 100.0

    # Order does not matter, and a clean film does not dilute a concerning one.
    assert fuse([100.0, 2.0]) == fuse([2.0, 100.0])
    assert fuse([100.0, 2.0]) >= fuse([100.0])
    # A single moderate reading stays moderate.
    assert 30.0 < fuse([50.0]) < 65.0
