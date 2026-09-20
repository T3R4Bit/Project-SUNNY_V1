"""The single source of truth for "what day is it, really" and "which brief
is active right now."

Both questions have the same answer for the same reason: a day, as lived,
does not start at midnight. Someone still awake at 3am is finishing the
previous day, not starting a new one.

This was already true in one place before this module existed --
briefing.py's BriefingTemplates._DAY_BOUNDARY_HOUR (5am) with
_perceived_today(), used only by evening_briefing(). That constant is
correct and its reasoning is unchanged; it was just private to one class
while three other features need the same boundary:

  - check-in answers (checkin.py) -- a migraine logged at 2am belongs to
    the day you were awake for. Filing it under the calendar date instead
    smears every late night into the wrong row, and because the paired
    sleep/barometric-pressure readings for that night file correctly, the
    correlation those rows exist to support is quietly destroyed. This is
    not recoverable after the fact.
  - Garmin ingest (garmin_client.py) -- same rows, same day key.
  - brief selection (active_brief_period) -- see below.

So it lives here now and briefing.py imports it.

BRIEF SELECTION

Two boundaries, not one:

    05:00 ---------- morning brief ---------- 18:30 ---------- evening brief ---------- 05:00

active_brief_period() answers only "which brief is the DEFAULT right now."
It deliberately does not answer "which brief did the user ask for" -- an
explicit "good morning" at 2am returns the morning brief, because the user
said the word. The window decides only when nothing was named (opening the
dashboard, a bare "brief"). Routing an explicit request through this
function would mean refusing to answer the question actually asked, which
is worse than being occasionally out of step with the clock.
"""

from datetime import date, datetime, time, timedelta
from typing import Optional

# Before this hour, a goodnight is still talking about the day you were
# awake for, not the calendar day that technically started at midnight --
# a goodnight said at 3am on the 27th recaps the 26th and previews the
# 27th (the day not yet been through), not the 28th.
DAY_BOUNDARY_HOUR = 5

# After this time, "the brief" means the evening one. 18:30 rather than a
# round hour because it is meant to land after a normal day's commitments
# rather than on a tidy boundary.
EVENING_SWITCH = time(18, 30)

MORNING = "morning"
EVENING = "evening"


def logging_day(now: Optional[datetime] = None) -> date:
    """The date a record made at `now` belongs to.

    Anything before DAY_BOUNDARY_HOUR files against the previous calendar
    date. Use this -- never `date.today()` -- for any row that describes a
    lived day: check-in answers, sleep, workouts, daily Garmin metrics.
    """
    now = now or datetime.now()
    today = now.date()
    if now.hour < DAY_BOUNDARY_HOUR:
        today -= timedelta(days=1)
    return today


def day_key(now: Optional[datetime] = None) -> str:
    """logging_day() as an ISO date string, for use as a storage key."""
    return logging_day(now).isoformat()


def active_brief_period(now: Optional[datetime] = None) -> str:
    """Which brief is the default right now: MORNING or EVENING.

    Morning runs from DAY_BOUNDARY_HOUR to EVENING_SWITCH; evening runs
    from EVENING_SWITCH through to DAY_BOUNDARY_HOUR the next calendar
    day. There is no gap and no overlap -- every instant maps to exactly
    one period.

    Only for the *default* case. An explicit request ("good morning",
    "good night") must bypass this entirely -- see the module docstring.
    """
    now = now or datetime.now()
    if now.hour < DAY_BOUNDARY_HOUR:
        return EVENING  # still last night
    if now.time() >= EVENING_SWITCH:
        return EVENING
    return MORNING


def is_late_night(now: Optional[datetime] = None) -> bool:
    """True between midnight and DAY_BOUNDARY_HOUR -- i.e. the window where
    the calendar date and the lived day disagree. Useful for wording ("last
    night" vs "tonight") rather than for storage decisions, which should
    just use logging_day().
    """
    now = now or datetime.now()
    return 0 <= now.hour < DAY_BOUNDARY_HOUR
