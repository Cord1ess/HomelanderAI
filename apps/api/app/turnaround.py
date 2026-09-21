"""When an applicant can expect an answer.

Two rules, both chosen for honesty rather than precision:

**Business days, not hours.** An application submitted on a Friday afternoon
with a two-day estimate should read Tuesday, not Sunday. Weekends are skipped;
public holidays are not, because the platform has no calendar of them and a
wrong holiday table is worse than none. Say "business days" on screen and it is
true.

**A date, never a countdown.** A countdown that slips looks like a broken
promise. A date that an underwriter openly revises, with a reason, looks
managed. So the estimate is stored as a date on the application, set once at
submit from the carrier's default, and changed only by a person who says why.

Pure functions. No database, no framework, so the arithmetic is testable on
its own and the same code can serve the console and the client portal.
"""

from datetime import date, timedelta

# Statuses in which the clock is not running against the carrier. Decided is
# finished; awaiting_evidence is waiting on the applicant, and telling them
# their own delay is "overdue" would be both wrong and irritating.
_CLOCK_STOPPED = frozenset({"decided", "awaiting_evidence"})

# Sensible bounds for a carrier default. One day is aggressive but possible;
# thirty is the point past which an estimate stops meaning anything.
MIN_BUSINESS_DAYS = 1
MAX_BUSINESS_DAYS = 30
DEFAULT_BUSINESS_DAYS = 2


def add_business_days(start: date, days: int) -> date:
    """The date `days` working days after `start`, skipping Saturday and Sunday.

    A start on a weekend counts from the following Monday, so a Saturday
    submission with a one-day estimate is due Tuesday, not Sunday.
    """
    if days < 0:
        raise ValueError("days must not be negative")

    current = start
    # Move a weekend start to Monday before counting.
    while current.weekday() >= 5:
        current += timedelta(days=1)

    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def is_overdue(expected_by: date | None, status: str, today: date | None = None) -> bool:
    """Whether an application has passed its estimate while still in progress.

    Not overdue when there is no estimate, when it is decided, or when the wait
    is on the applicant rather than the carrier.
    """
    if expected_by is None or status in _CLOCK_STOPPED:
        return False
    return (today or date.today()) > expected_by
