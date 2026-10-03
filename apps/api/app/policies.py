"""Date arithmetic for policies: terms, month steps and end dates.

Kept apart from the router so it is tested on its own: a month-end mistake
here would put a premium due, or a policy's end, on a day that does not exist.
Premiums themselves are collected by the bank; nothing here tracks payment.
"""

import calendar
from datetime import date

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
