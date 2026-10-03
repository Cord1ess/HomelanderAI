"""Policies: what an approval issues, and the monthly payments that keep it going.

The schedule is worked out, not stored. A policy starting on 3 March is due on
the 3rd of every month (the last day in a shorter month) until it ends; a
payment row marks a month paid. So the schedule can never disagree with the
policy's own dates, and nothing has to be generated in advance.

**Grace period.** A month's premium unpaid `GRACE_DAYS` after it fell due is
overdue. Thirty days is common practice for life policies in Bangladesh; check
the company's own policy terms before relying on it.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

GRACE_DAYS = 30

# What each approval issues. The plan comes from the decision, never the
# model's tier (see routers/portal.py).
PLAN_FOR_DECISION = {
    "confirmed_fast_track": "Standard",
    "approved_with_adjustment": "Standard with adjustment",
}

DEFAULT_TERM_YEARS = 10


def term_years(policy_term: str | None) -> int:
    """The years asked for at intake ("10", "10 years"), or ten when none was."""
    digits = "".join(ch for ch in (policy_term or "") if ch.isdigit())
    years = int(digits) if digits else DEFAULT_TERM_YEARS
    return max(1, min(40, years))


def add_months(start: date, months: int) -> date:
    """`start` moved on by whole months, kept to the last day of a short month."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def end_date(start: date, years: int) -> date:
    return add_months(start, years * 12)


@dataclass(frozen=True)
class Installment:
    number: int
    due_date: date
    amount: Decimal
    # paid | overdue | due | upcoming
    status: str
    paid_on: date | None = None
    method: str | None = None


def schedule(
    start: date,
    end: date,
    amount: Decimal,
    paid: dict[date, tuple[date, str]],
    today: date,
    *,
    cancelled_on: date | None = None,
    ahead: int = 1,
) -> list[Installment]:
    """Every month that has fallen due, plus `ahead` months still to come.

    `paid` maps a due date to (the day it was paid, how). A cancelled policy
    stops falling due on the day it was cancelled.
    """
    stop = min(end, cancelled_on) if cancelled_on else end
    out: list[Installment] = []
    number = 0
    future_shown = 0
    while True:
        due = add_months(start, number)
        if due >= stop:
            break
        if due > today:
            if future_shown >= ahead:
                break
            future_shown += 1
        number += 1
        if due in paid:
            paid_on, method = paid[due]
            out.append(Installment(number, due, amount, "paid", paid_on, method))
        elif due > today:
            out.append(Installment(number, due, amount, "upcoming"))
        elif (today - due).days > GRACE_DAYS:
            out.append(Installment(number, due, amount, "overdue"))
        else:
            out.append(Installment(number, due, amount, "due"))
    return out


@dataclass(frozen=True)
class Summary:
    paid_count: int
    paid_total: Decimal
    overdue_count: int
    overdue_total: Decimal
    next_due: date | None
    next_amount: Decimal | None
    months_total: int


def summarise(installments: list[Installment], term: int) -> Summary:
    paid = [i for i in installments if i.status == "paid"]
    overdue = [i for i in installments if i.status == "overdue"]
    unpaid = [i for i in installments if i.status in ("overdue", "due", "upcoming")]
    first_unpaid = unpaid[0] if unpaid else None
    return Summary(
        paid_count=len(paid),
        paid_total=sum((i.amount for i in paid), Decimal(0)),
        overdue_count=len(overdue),
        overdue_total=sum((i.amount for i in overdue), Decimal(0)),
        next_due=first_unpaid.due_date if first_unpaid else None,
        next_amount=first_unpaid.amount if first_unpaid else None,
        months_total=term * 12,
    )
