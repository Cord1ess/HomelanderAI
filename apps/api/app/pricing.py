"""What a policy costs: two products, priced from first principles.

Replaces the flat "৳5,000 a month per ৳10 lakh" placeholder, which was about
sixteen times what term life costs in Bangladesh. Kept free of database and
framework imports, like `scoring.py`, so it is tested on its own.

**Term life** (level premium, 5-25 years). The premium is the actuarial value
of the cover divided by the value of the premiums, loaded for expenses:

    net   = SA × Σ vᵗ⁺¹ ₜp q(x+t) / Σ vᵗ ₜp      over the term
    gross = net / (1 − expense loading)

* Mortality q(x): anchored at **3.0 per 1,000 at age 35** for an insured man
  (the Bangladesh Assured Lives Table 2015-18, as quoted in industry
  guidance), rising 8% a year of age (the usual adult slope). Women at 80%.
  Smokers and the underwriter's rating multiply it.
* Interest **5%** and expense loading **22.32%**: IDRA's limits for
  non-participating plans. The loading pays commission, running costs and
  profit; the company can lower it in Plans and pricing, not raise it past the
  cap.

Check against the published worked example (male 35, ৳20 lakh, 20 years): a
flat 3.0/1,000 gives gross ৳7,724; this engine, with mortality rising over the
term as it really does, gives ৳15,120 a year (৳1,323 a month). That is a
level premium for twenty years, so it is higher than one year's cost.

**Hospital cover** (one year, renewed each year). Pays hospital bills up to
the yearly limit. Priced per ৳1 lakh of limit by age band, in line with what
individual hospitalisation plans charge in Bangladesh (৳50,000-৳3 lakh limits,
roughly ৳1,500-৳5,000 per lakh a year by age). Pre-existing conditions wait
two years; other illness thirty days; accidents are covered from day one.

**Ratings.** A moderate or elevated reading does not just raise a flag: the
underwriter approves at a rating (+25% to +150% on the premium) and/or with
exclusions, or declines. The tier suggests a starting rating.

These are pricing assumptions a company would have an actuary confirm and
IDRA approve. They are not invented: each one is named above, and the
company's administrator can change the ones a company would.
"""

import math
from dataclasses import dataclass

from app import policies as _dates

PRODUCTS = ("life", "health")

# The years asked for at intake ("10", "10 years"), or ten.
term_years = _dates.term_years

# What each product offers. Few options on purpose: a choice a person cannot
# explain to a client is not a choice.
LIFE_AMOUNTS = (500_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000)
LIFE_TERMS = (5, 10, 15, 20, 25)
HEALTH_AMOUNTS = (100_000, 200_000, 300_000, 500_000)

LIFE_ENTRY_AGE = (18, 60)
LIFE_MAX_EXPIRY_AGE = 70
HEALTH_ENTRY_AGE = (18, 65)
HEALTH_MAX_RENEWAL_AGE = 70

# Extra on the premium an underwriter can approve at.
RATINGS = (0, 25, 50, 75, 100, 150)
# Where each tier's suggestion starts. Elevated starts high because a doctor
# has looked at it before anyone approves it.
SUGGESTED_RATING = {"low": 0, "moderate": 50, "elevated": 100}

# Days after a policy starts in which the client may cancel for a full refund.
FREE_LOOK_DAYS = 15
# Hospital cover waiting periods.
HEALTH_ILLNESS_WAIT_DAYS = 30
HEALTH_PREEXISTING_WAIT_MONTHS = 24

# Mortality anchor and slope (see the module docstring).
_Q35_MALE = 0.0030
_SLOPE = 0.08
_FEMALE = 0.80
_Q_CAP = 0.5

# Hospital cover: the company's base rate is for ages 18-35; older bands pay more.
HEALTH_AGE_BANDS = ((35, 1.00), (45, 1.35), (55, 1.90), (65, 2.80), (70, 3.60))


@dataclass(frozen=True)
class Rates:
    """A company's pricing assumptions (tenants.* columns)."""

    life_expense_loading_pct: float = 22.32
    life_interest_pct: float = 5.0
    health_rate_per_lakh_bdt: float = 1800.0
    smoker_loading_pct: float = 50.0
    # Paying monthly costs a little more than paying once a year.
    monthly_loading_pct: float = 5.0

    @classmethod
    def from_tenant(cls, tenant) -> "Rates":
        """From a Tenant row; typed loosely so this module stays ORM-free."""
        return cls(
            life_expense_loading_pct=float(tenant.life_expense_loading_pct),
            life_interest_pct=float(tenant.life_interest_pct),
            health_rate_per_lakh_bdt=float(tenant.health_rate_per_lakh_bdt),
            smoker_loading_pct=float(tenant.smoker_loading_pct),
            monthly_loading_pct=float(tenant.monthly_loading_pct),
        )


DEFAULT_RATES = Rates()


def product_for(coverage_type: str | None) -> str:
    """The product a cover type is sold as. Critical illness is no longer
    offered; older applications that asked for it are priced as life."""
    return "health" if (coverage_type or "").strip().lower() == "health" else "life"


def mortality(age: int, sex: str | None) -> float:
    """One year's probability of death for an insured life of this age."""
    q = _Q35_MALE * math.exp(_SLOPE * (age - 35))
    if (sex or "").strip().lower().startswith("f"):
        q *= _FEMALE
    return min(q, _Q_CAP)


@dataclass(frozen=True)
class Quote:
    product: str
    sum_assured: float
    term_years: int
    age: int
    annual_bdt: float
    monthly_bdt: float
    # What the company expects to pay out a year, before its loading: the
    # premium a policy would cost at cost.
    expected_claims_bdt: float
    rating_pct: int
    smoker: bool
    eligible: bool = True
    reason: str | None = None

    @property
    def total_bdt(self) -> float:
        return self.annual_bdt * self.term_years


def _round_up(value: float, to: int) -> float:
    return float(math.ceil(value / to) * to)


def eligibility(product: str, age: int | None, term_years: int) -> str | None:
    """Why this cannot be offered, or None when it can."""
    if age is None:
        return "The client's date of birth is needed to price the cover."
    if product == "life":
        low, high = LIFE_ENTRY_AGE
        if not low <= age <= high:
            return f"Term life is for ages {low} to {high}; the client is {age}."
        if age + term_years > LIFE_MAX_EXPIRY_AGE:
            longest = LIFE_MAX_EXPIRY_AGE - age
            return (
                f"Cover must end by age {LIFE_MAX_EXPIRY_AGE}: at {age} the longest term is "
                f"{longest} years."
            )
        return None
    low, high = HEALTH_ENTRY_AGE
    if not low <= age <= high:
        return f"Hospital cover starts between ages {low} and {high}; the client is {age}."
    return None


def quote(
    product: str,
    sum_assured: float,
    term_years: int,
    age: int | None,
    sex: str | None = None,
    smoker: bool = False,
    rating_pct: int = 0,
    rates: Rates = DEFAULT_RATES,
) -> Quote:
    """The premium for one policy. Never raises: an ineligible request comes
    back with `eligible=False` and the reason, and premiums of zero."""
    term = 1 if product == "health" else int(term_years)
    reason = eligibility(product, age, term)
    if reason is not None or age is None:
        return Quote(
            product,
            sum_assured,
            term,
            age or 0,
            0.0,
            0.0,
            0.0,
            rating_pct,
            smoker,
            eligible=False,
            reason=reason,
        )

    extra = (1 + rating_pct / 100) * (1 + (rates.smoker_loading_pct / 100 if smoker else 0))

    if product == "life":
        v = 1 / (1 + rates.life_interest_pct / 100)
        alive = 1.0
        benefits = annuity = 0.0
        for t in range(term):
            q = min(mortality(age + t, sex) * extra, _Q_CAP)
            annuity += v**t * alive
            benefits += v ** (t + 1) * alive * q
            alive *= 1 - q
        expected = sum_assured * benefits / annuity
        annual = expected / (1 - rates.life_expense_loading_pct / 100)
    else:
        factor = next(f for upto, f in HEALTH_AGE_BANDS if age <= upto)
        annual = sum_assured / 100_000 * rates.health_rate_per_lakh_bdt * factor * extra
        # The rate already carries the company's margin; about 70% of it is
        # expected to come back as claims.
        expected = annual * 0.70

    annual = _round_up(annual, 10)
    monthly = _round_up(annual * (1 + rates.monthly_loading_pct / 100) / 12, 1)
    return Quote(
        product, sum_assured, term, age, annual, monthly, round(expected, 2), rating_pct, smoker
    )


def age_on(born, on) -> int | None:
    """Whole years between a date of birth and a date."""
    if born is None:
        return None
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def is_smoker(declared: dict | None) -> bool:
    """Whether the declared answers say the client smokes, wherever it was asked."""
    declared = declared or {}
    for block in declared.values():
        if not isinstance(block, dict):
            continue
        if block.get("smoker") is True:
            return True
        history = block.get("history")
        if isinstance(history, dict) and history.get("smoker") is True:
            return True
    return False


# ── exclusions ───────────────────────────────────────────────────────────────

# Conditions a reader's finding can suggest leaving out of hospital cover. The
# underwriter decides; these are the starting point, named in words a client
# understands.
EXCLUSION_FOR_ARM = {
    "tb_xray": "Lung disease, including tuberculosis",
    "dr_fundus": "Eye disease from diabetes (diabetic retinopathy)",
    "ecg_12lead": "Heart disease and heart rhythm problems",
    "mirai": "Breast cancer",
    "medication_check": "The conditions found in the clinical notes that were not declared",
}
EXCLUSION_FOR_DECLARED = {
    "diabetes": "Diabetes and its complications",
    "hypertension": "High blood pressure and its complications",
    "high_cholesterol": "Heart disease linked to high cholesterol",
    "hiv": "HIV-related illness",
    "prior_tb": "Lung disease, including tuberculosis",
}


def suggested_exclusions(arm_tiers: dict[str, str], declared: dict | None) -> list[str]:
    """Exclusions to start from: one per reader that found a moderate or
    elevated risk, and one per condition the client declared."""
    out: list[str] = []
    for arm, tier in arm_tiers.items():
        text = EXCLUSION_FOR_ARM.get(arm)
        if text and tier in ("moderate", "elevated") and text not in out:
            out.append(text)
    for block in (declared or {}).values():
        if not isinstance(block, dict):
            continue
        flags = {**block, **(block.get("history") or {}), **(block.get("cardio") or {})}
        for key, text in EXCLUSION_FOR_DECLARED.items():
            if flags.get(key) is True and text not in out:
                out.append(text)
    return out
