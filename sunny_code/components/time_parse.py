"""Deterministic time-expression parsing for alarms/reminders — no LLM, bounded
regex formats only: "7am", "7:00 AM", "6:30pm tomorrow", "on 2026-08-25 at 3pm",
"in 30 minutes". Anything outside these shapes returns None rather than guessing.
"""

import re
from datetime import date, datetime, timedelta
from typing import Optional

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_RELATIVE_RE = re.compile(r"^in\s+(\d+)\s+(minute|min|hour|hr)s?$")
_DATE_PREFIX_RE = re.compile(r"^(?:on\s+)?(\d{4}-\d{2}-\d{2})(?:\s+at)?\s+(.+)$")
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def parse_time_expression(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a time expression into a concrete datetime, or None if unparseable."""
    now = now or datetime.now()
    text = text.strip().lower()
    if not text:
        return None

    relative = _RELATIVE_RE.match(text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        delta = timedelta(minutes=amount) if unit in ("minute", "min") else timedelta(hours=amount)
        return now + delta

    date_part = None
    time_part = text
    dated = _DATE_PREFIX_RE.match(text)
    if dated:
        date_part = dated.group(1)
        time_part = dated.group(2)

    is_tomorrow = False
    if time_part.endswith(" tomorrow"):
        is_tomorrow = True
        time_part = time_part[: -len(" tomorrow")].strip()
    elif time_part.endswith(" today"):
        time_part = time_part[: -len(" today")].strip()

    time_match = _TIME_RE.match(time_part)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    ampm = time_match.group(3)

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif ampm is None and hour > 23:
        return None

    if hour > 23 or minute > 59:
        return None

    try:
        base_date = datetime.strptime(date_part, "%Y-%m-%d").date() if date_part else now.date()
    except ValueError:
        return None

    result = datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)

    if is_tomorrow:
        result += timedelta(days=1)
    elif not date_part and result <= now:
        # No explicit date, and that time already passed today — assume tomorrow.
        result += timedelta(days=1)

    return result


def parse_recurrence(text: str) -> Optional[str]:
    """Parse a recurrence phrase. Returns 'daily', 'weekdays', a weekday name, or None."""
    text = text.strip().lower()
    if text in ("every day", "daily", "everyday"):
        return "daily"
    if text in ("every weekday", "weekdays", "every week day"):
        return "weekdays"
    match = re.match(r"^every\s+(\w+)$", text)
    if match and match.group(1) in WEEKDAYS:
        return match.group(1)
    return None


def next_occurrence(current: datetime, recurrence: str) -> datetime:
    """Given a trigger_at that just fired and a recurrence rule, compute the next one."""
    if recurrence == "daily":
        return current + timedelta(days=1)
    if recurrence == "weekdays":
        next_dt = current + timedelta(days=1)
        while next_dt.weekday() >= 5:  # Sat=5, Sun=6
            next_dt += timedelta(days=1)
        return next_dt
    if recurrence in WEEKDAYS:
        target = WEEKDAYS.index(recurrence)
        next_dt = current + timedelta(days=1)
        while next_dt.weekday() != target:
            next_dt += timedelta(days=1)
        return next_dt
    return current
