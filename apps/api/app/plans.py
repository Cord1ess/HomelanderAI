"""Insurance plans: what each risk tier means for the policy.

The tiers and their premiums come from `docs/Idea.md` §5, restated under the
decision-support framing in `docs/SPEC.md` §7 — the platform recommends, a
licensed underwriter decides. Nothing here approves or prices anything on its
own.

Kept free of database and framework imports, like `scoring.py`, so it can be
tested on its own and so the API and the dashboard read the same numbers from
one place instead of each keeping their own copy.

**These are illustrative rates, not actuarial pricing.** Idea.md gives a monthly
premium per tier but no rate card, so the figures below are treated as the
premium at a reference sum assured and scaled linearly with the cover actually
requested. That assumption is shown on screen wherever a number is; it is a
worked illustration for a capstone, not a quote.
"""

from dataclasses import dataclass

# The sum assured Idea.md's premiums are taken to describe. Everything scales
# from here, so asking for twice the cover doubles the premium.
REFERENCE_COVER_BDT = 1_000_000.0


@dataclass(frozen=True)
class Policy:
    """A company's pricing policy: the rates behind the two quotable plans.

    Set by the company's administrator (tenants.premium_low_bdt and friends);
    the defaults are Idea.md's figures. Elevated and unscorable tiers have no
    rate here because they carry none anywhere: a price on a case a person has
    not yet looked at would imply an outcome that has not been decided.
    """

    premium_low_bdt: float = 5_000.0
    premium_moderate_bdt: float = 7_500.0
    reference_cover_bdt: float = REFERENCE_COVER_BDT

    def base_for(self, tier: str) -> float | None:
        if tier == "low":
            return self.premium_low_bdt
        if tier == "moderate":
            return self.premium_moderate_bdt
        return None

    @classmethod
    def from_tenant(cls, tenant) -> "Policy":
        """From a Tenant row. Typed loosely so this module stays free of ORM imports."""
        return cls(
            premium_low_bdt=float(tenant.premium_low_bdt),
            premium_moderate_bdt=float(tenant.premium_moderate_bdt),
            reference_cover_bdt=float(tenant.reference_cover_bdt),
        )


DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Plan:
    tier: str
    name: str
    # What the platform recommends. Never what it does — see SPEC §1.
    recommendation: str
    # The human step that has to happen before anything is issued.
    human_step: str
    # Idea.md's monthly premium at REFERENCE_COVER_BDT, kept as documentation
    # of where the defaults came from. The live figure is the company's Policy.
    base_monthly_bdt: float | None
    wellness_discount_eligible: bool = False


PLANS: dict[str, Plan] = {
    "low": Plan(
        tier="low",
        name="Standard",
        recommendation="Cleared for fast-track at baseline rates",
        human_step="One-click underwriter confirmation",
        base_monthly_bdt=5_000.0,
    ),
    "moderate": Plan(
        tier="moderate",
        name="Standard with adjustment",
        recommendation="Approve with a rate adjustment",
        human_step="Underwriter reviews and sets the final rate",
        base_monthly_bdt=7_500.0,
        wellness_discount_eligible=True,
    ),
    "elevated": Plan(
        tier="elevated",
        name="Medical review",
        # No rate is quoted here on purpose. Tier 3 is a routing decision, and
        # attaching a price to it would imply an outcome that has not been
        # decided. Never an automated denial (SPEC §7).
        recommendation="Route to a medical professional with the full evidence pack",
        human_step="Mandatory medical review — never an automated denial",
        base_monthly_bdt=None,
    ),
    "insufficient_evidence": Plan(
        tier="insufficient_evidence",
        name="Not assessable",
        recommendation="Request additional evidence before pricing",
        human_step="Underwriter requests what is missing",
        base_monthly_bdt=None,
    ),
}


def monthly_premium(
    tier: str, coverage_amount: float | None, policy: Policy = DEFAULT_POLICY
) -> float | None:
    """Illustrative monthly premium for a tier at the requested cover.

    Returns None when the tier carries no quotable rate, or when no coverage
    amount was requested — a premium invented from a missing number is worse
    than no premium at all.
    """
    base = policy.base_for(tier)
    if tier not in PLANS or base is None or not coverage_amount:
        return None

    return round(base * (float(coverage_amount) / policy.reference_cover_bdt), 2)


def for_tier(
    tier: str, coverage_amount: float | None = None, policy: Policy = DEFAULT_POLICY
) -> dict | None:
    """The plan for a tier, with the premium worked out for this application
    under this company's policy."""
    plan = PLANS.get(tier)
    if plan is None:
        return None

    return {
        "tier": plan.tier,
        "name": plan.name,
        "recommendation": plan.recommendation,
        "human_step": plan.human_step,
        "base_monthly_bdt": policy.base_for(tier),
        "reference_cover_bdt": policy.reference_cover_bdt,
        "monthly_premium_bdt": monthly_premium(tier, coverage_amount, policy),
        "wellness_discount_eligible": plan.wellness_discount_eligible,
    }
