"""Prices: the company's assumptions, what each product offers, and quotes.

The engine is `app/pricing.py`. This router lets the intake form quote while
the client is in the room, and shows the owner what their assumptions
produce at typical ages before they change one.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import pricing
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.models import Tenant, UserRole
from app.schemas.application import QuoteSchema
from app.schemas.auth import BaseSchema

router = APIRouter(tags=["Pricing"])


class RatesSchema(BaseSchema):
    life_expense_loading_pct: float
    life_interest_pct: float
    health_rate_per_lakh_bdt: float
    smoker_loading_pct: float
    monthly_loading_pct: float


class ExampleSchema(BaseSchema):
    product: str
    age: int
    sex: str
    sum_assured_bdt: float
    term_years: int
    annual_bdt: float
    monthly_bdt: float


class PricingSchema(BaseSchema):
    rates: RatesSchema
    life_amounts: list[int]
    life_terms: list[int]
    health_amounts: list[int]
    ratings: list[int]
    life_entry_ages: list[int]
    life_max_expiry_age: int
    health_entry_ages: list[int]
    free_look_days: int
    health_illness_wait_days: int
    health_preexisting_wait_months: int
    examples: list[ExampleSchema] = Field(default_factory=list)


class QuoteRequest(BaseSchema):
    product: str = Field(..., pattern="^(life|health)$")
    sum_assured_bdt: float = Field(..., gt=0)
    term_years: int = Field(default=10, ge=1, le=40)
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = None
    smoker: bool = False
    rating_pct: int = 0


async def _rates(db: AsyncSession, principal: Principal) -> pricing.Rates:
    tenant = await db.get(Tenant, principal.tenant_id)
    return pricing.Rates.from_tenant(tenant) if tenant else pricing.DEFAULT_RATES


@router.get(
    "/pricing", response_model=PricingSchema, summary="The products and their prices (owner)"
)
async def get_pricing(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> PricingSchema:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Plans and pricing are for the company owner (an administrator).",
        )
    rates = await _rates(db, principal)
    examples = []
    for age in (25, 35, 45, 55):
        for sex in ("male", "female"):
            q = pricing.quote("life", 1_000_000, 10, age, sex, rates=rates)
            examples.append(
                ExampleSchema(
                    product="life",
                    age=age,
                    sex=sex,
                    sum_assured_bdt=1_000_000,
                    term_years=10,
                    annual_bdt=q.annual_bdt,
                    monthly_bdt=q.monthly_bdt,
                )
            )
        q = pricing.quote("health", 200_000, 1, age, None, rates=rates)
        examples.append(
            ExampleSchema(
                product="health",
                age=age,
                sex="any",
                sum_assured_bdt=200_000,
                term_years=1,
                annual_bdt=q.annual_bdt,
                monthly_bdt=q.monthly_bdt,
            )
        )
    return PricingSchema(
        rates=RatesSchema(**rates.__dict__),
        life_amounts=list(pricing.LIFE_AMOUNTS),
        life_terms=list(pricing.LIFE_TERMS),
        health_amounts=list(pricing.HEALTH_AMOUNTS),
        ratings=list(pricing.RATINGS),
        life_entry_ages=list(pricing.LIFE_ENTRY_AGE),
        life_max_expiry_age=pricing.LIFE_MAX_EXPIRY_AGE,
        health_entry_ages=list(pricing.HEALTH_ENTRY_AGE),
        free_look_days=pricing.FREE_LOOK_DAYS,
        health_illness_wait_days=pricing.HEALTH_ILLNESS_WAIT_DAYS,
        health_preexisting_wait_months=pricing.HEALTH_PREEXISTING_WAIT_MONTHS,
        examples=examples,
    )


@router.post("/quote", response_model=QuoteSchema, summary="Price one policy")
async def quote(
    payload: QuoteRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> QuoteSchema:
    if principal.role == UserRole.MEDICAL_PROFESSIONAL.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Pricing is not a doctor's."
        )
    if payload.rating_pct not in pricing.RATINGS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown rating."
        )
    age = (
        payload.age
        if payload.age is not None
        else pricing.age_on(payload.date_of_birth, date.today())
    )
    q = pricing.quote(
        payload.product,
        payload.sum_assured_bdt,
        payload.term_years,
        age,
        payload.sex,
        payload.smoker,
        payload.rating_pct,
        await _rates(db, principal),
    )
    from app.routers.applications import _quote_schema

    return _quote_schema(q)
