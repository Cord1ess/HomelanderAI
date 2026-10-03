"""What each risk tier means for the policy: the recommendation, and its price.

The platform recommends; a licensed underwriter decides (docs/SPEC.md §7).
Prices come from `pricing.py`: the tier only suggests the rating to start
from (standard, +50%, +100%), and the underwriter approves at a rating, with
exclusions, or declines.

Kept free of database and framework imports, like `scoring.py`, so it can be
tested on its own and so the API and the dashboard read the same numbers from
one place.
"""

from dataclasses import dataclass

from app import pricing


@dataclass(frozen=True)
class Plan:
    tier: str
    name: str
    # What the platform recommends. Never what it does — see SPEC §1.
    recommendation: str
    # The human step that has to happen before anything is issued.
    human_step: str


PLANS: dict[str, Plan] = {
    "low": Plan(
        tier="low",
        name="Standard",
        recommendation="Approve at standard rates",
        human_step="An underwriter confirms",
    ),
    "moderate": Plan(
        tier="moderate",
        name="Rated",
        recommendation=(
            "Approve at a rating (about +50% on the premium), with exclusions for what the "
            "readers found, or decline if the evidence does not support cover"
        ),
        human_step="An underwriter sets the rating and exclusions",
    ),
    "elevated": Plan(
        tier="elevated",
        name="Medical review",
        # No price until a doctor has looked: a figure on a case nobody has
        # reviewed would imply an outcome. Never an automated decline (SPEC §7).
        recommendation=(
            "A doctor checks the results first; then approve at a high rating with "
            "exclusions, or decline"
        ),
        human_step="Mandatory medical review — never an automated decline",
    ),
    "insufficient_evidence": Plan(
        tier="insufficient_evidence",
        name="Not assessable",
        recommendation="Request what is missing before pricing",
        human_step="An underwriter requests the documents",
    ),
}


def for_tier(
    tier: str,
    product: str,
    sum_assured: float | None,
    term_years: int,
    age: int | None,
    sex: str | None = None,
    smoker: bool = False,
    rates: pricing.Rates = pricing.DEFAULT_RATES,
) -> dict | None:
    """The plan for a tier, with the premium at its suggested rating."""
    plan = PLANS.get(tier)
    if plan is None:
        return None
    rating = pricing.SUGGESTED_RATING.get(tier)
    priced = (
        pricing.quote(product, sum_assured, term_years, age, sex, smoker, rating, rates)
        if rating is not None and sum_assured
        else None
    )
    return {
        "tier": plan.tier,
        "name": plan.name,
        "recommendation": plan.recommendation,
        "human_step": plan.human_step,
        "product": product,
        "rating_pct": rating,
        "annual_premium_bdt": priced.annual_bdt if priced and priced.eligible else None,
        "monthly_premium_bdt": priced.monthly_bdt if priced and priced.eligible else None,
        "ineligible_reason": priced.reason if priced and not priced.eligible else None,
    }
