"""Schedule-aware workout windows: real gaps in the calendar, ranked by
how ready the body is to use them.

This is the first thing in Sunny that looks at the day and proposes an
action rather than answering a question. It is deliberately a suggestion
engine and nothing more -- it never writes to the calendar on its own.
Creating events unprompted is the kind of autonomy the vision doc puts
behind an explicit approval step, and a wrong guess there costs more
trust than a missed workout costs fitness.

WHY WINDOWS RATHER THAN REMINDERS
---------------------------------
"Remind me to work out at 6pm" fails the moment 6pm has a class in it,
and a reminder that fires during something else trains you to dismiss
reminders. A window is derived from what the calendar actually says is
free, so it can only ever suggest time that exists.

RANKING
-------
Windows are scored on three things, in descending importance:

  1. Readiness (readiness.py) -- the same number for every window today,
     so it separates days rather than windows. A low-readiness day
     downgrades a suggestion to something easy rather than suppressing it.
  2. Length -- past a point, more time stops helping. A 90-minute gap is
     not twice as good as a 45-minute one.
  3. Time of day -- a gap at 2am is technically free and practically
     useless.

The load gap (see readiness.load_gap) does not affect ranking. It decides
whether to surface anything at all and what to say, which is a different
question from which window is best.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sunny_code.components import readiness

logger = logging.getLogger(__name__)

# Shorter than this isn't a workout once travel and changing are counted.
MIN_WINDOW_MINUTES = 45

# Hours a suggestion may start in. Outside this a gap is free on paper and
# useless in practice.
EARLIEST_HOUR = 6
LATEST_START_HOUR = 21

# Past this, extra time stops improving a window -- a 3-hour gap is not
# four times better than a 45-minute one, and treating it that way buries
# a perfectly good after-class window under an empty Sunday afternoon.
DIMINISHING_MINUTES = 90

# A free block longer than this stops being a suggestion and becomes a
# statement about the day. "Tomorrow 6:00 AM, 960 min free" is accurate
# and useless -- an empty calendar is not an instruction to train for
# sixteen hours. Blocks above this are narrowed to a concrete slot at the
# best-scoring hour inside them, with the full block reported separately
# as context.
MAX_SUGGESTED_MINUTES = 120
SUGGESTED_SESSION_MINUTES = 75

# Preferred start hours, by how well they tend to work rather than by
# physiology: late afternoon beats late evening beats early morning.
_HOUR_SCORES = [
    (range(15, 20), 1.0),   # 3pm-8pm
    (range(11, 15), 0.9),   # late morning / midday
    (range(20, 22), 0.7),   # evening
    (range(6, 11), 0.65),   # early
]


def _hour_score(hour: int) -> float:
    for hours, value in _HOUR_SCORES:
        if hour in hours:
            return value
    return 0.4


def _busy_blocks(day_offset: int) -> Optional[List[Dict]]:
    """Timed events for a day as [{start, end}], or None if the calendar
    isn't available.

    None and [] mean different things and must not be conflated: [] is "a
    genuinely free day", None is "no idea". Suggesting a wide-open day
    because Google is disconnected would be inventing free time.

    google_calendar is imported lazily: it pulls in the whole Google API
    client at module load, and nothing else in this module needs it --
    same reason briefing.py imports garmin_client inside the function
    that uses it.
    """
    from sunny_code.components import google_calendar

    events = google_calendar.get_events(day_offset)
    if events is None:
        return None

    blocks = []
    for event in events:
        start, end = _event_bounds(event, day_offset)
        if start and end:
            blocks.append({"start": start, "end": end})

    blocks.sort(key=lambda b: b["start"])
    return blocks


def _event_bounds(event: Dict, day_offset: int):
    """(start, end) datetimes for a calendar event, or (None, None) for an
    all-day event -- those block a date, not a time, and treating one as a
    24-hour busy block would erase every window on the day it falls on."""
    target = date.today() + timedelta(days=day_offset)
    raw_start = event.get("start_dt") or event.get("start")
    raw_end = event.get("end_dt") or event.get("end")

    start = _coerce(raw_start, target)
    end = _coerce(raw_end, target)
    if start and not end:
        # Untimed end -- assume an hour rather than dropping the event,
        # which would leave its time looking free.
        end = start + timedelta(hours=1)
    return start, end


def _coerce(value, target: date) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 10:  # a bare date -> all-day
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
        # "3:30 PM" / "15:30" style, as the briefing formats them.
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                parsed = datetime.strptime(text, fmt).time()
                return datetime.combine(target, parsed)
            except ValueError:
                continue
    return None


def _gaps_for_day(day_offset: int) -> Optional[List[Dict]]:
    blocks = _busy_blocks(day_offset)
    if blocks is None:
        return None

    target = date.today() + timedelta(days=day_offset)
    cursor = datetime.combine(target, time(EARLIEST_HOUR, 0))
    day_end = datetime.combine(target, time(LATEST_START_HOUR + 1, 0))

    # Never suggest time that has already passed.
    now = datetime.now()
    if day_offset == 0 and cursor < now:
        cursor = now

    gaps = []
    for block in blocks:
        if block["start"] > cursor:
            gaps.append({"start": cursor, "end": min(block["start"], day_end)})
        cursor = max(cursor, block["end"])
    if cursor < day_end:
        gaps.append({"start": cursor, "end": day_end})

    usable = []
    for gap in gaps:
        minutes = (gap["end"] - gap["start"]).total_seconds() / 60
        if minutes < MIN_WINDOW_MINUTES or not (EARLIEST_HOUR <= gap["start"].hour <= LATEST_START_HOUR):
            continue
        usable.append(_narrow(gap, int(minutes)))
    return usable


def _narrow(gap: Dict, minutes: int) -> Dict:
    """Turn a very long free block into a concrete slot inside it.

    Leaves ordinary gaps untouched. For anything above
    MAX_SUGGESTED_MINUTES it picks the best-scoring start hour within the
    block and proposes a session-length slot there, keeping the block's
    real size in `free_minutes` so the brief can still say how much room
    there is. Suggesting a specific time is the difference between advice
    and an observation about your calendar.
    """
    if minutes <= MAX_SUGGESTED_MINUTES:
        return {"start": gap["start"], "end": gap["end"], "minutes": minutes, "free_minutes": minutes}

    latest_start = gap["end"] - timedelta(minutes=SUGGESTED_SESSION_MINUTES)
    best = gap["start"]
    best_score = _hour_score(best.hour)
    cursor = gap["start"].replace(minute=0) + timedelta(hours=1)
    while cursor <= latest_start:
        if cursor.hour > LATEST_START_HOUR:
            break
        if _hour_score(cursor.hour) > best_score:
            best, best_score = cursor, _hour_score(cursor.hour)
        cursor += timedelta(hours=1)

    return {
        "start": best,
        "end": best + timedelta(minutes=SUGGESTED_SESSION_MINUTES),
        "minutes": SUGGESTED_SESSION_MINUTES,
        "free_minutes": minutes,
    }


def find_windows(days_ahead: int = 2) -> Dict:
    """Free windows over the next `days_ahead` days, best first.

    Returns a result dict rather than a bare list so callers can tell
    "no free time" from "no calendar" -- the honest-gap contract every
    other data source here follows.
    """
    current = readiness.score()
    load = readiness.load_gap()
    readiness_value = current["score"] if current else None

    windows: List[Dict] = []
    calendar_available = False

    for offset in range(days_ahead):
        gaps = _gaps_for_day(offset)
        if gaps is None:
            continue
        calendar_available = True
        for gap in gaps:
            windows.append({
                "start": gap["start"].isoformat(timespec="minutes"),
                "day_offset": offset,
                "label": _window_label(gap["start"], offset),
                "minutes": gap["minutes"],
                "free_minutes": gap.get("free_minutes", gap["minutes"]),
                "rank": _rank(gap, readiness_value),
                "intensity": _intensity(readiness_value),
            })

    windows.sort(key=lambda w: -w["rank"])
    return {
        "available": calendar_available,
        "readiness": readiness_value,
        "band": current["band"] if current else None,
        "load_gap": load,
        "windows": windows[:5],
        "advice": _advice(windows, readiness_value, load, calendar_available),
    }


def _window_label(start: datetime, offset: int) -> str:
    """e.g. "tomorrow 3:30 PM". Hour formatting is done by hand rather than
    with %-I (glibc-only) or %#I (Windows-only) -- this module is tested on
    one platform and runs on another."""
    prefix = "today" if offset == 0 else ("tomorrow" if offset == 1 else start.strftime("%A"))
    hour = start.hour % 12 or 12
    return f"{prefix} {hour}:{start.minute:02d} {start.strftime('%p')}"


def _rank(gap: Dict, readiness_value: Optional[int]) -> float:
    length = min(gap["minutes"], DIMINISHING_MINUTES) / DIMINISHING_MINUTES
    hour = _hour_score(gap["start"].hour)
    # Readiness is the same for every window today, so it separates days
    # rather than windows -- which is the intent. Neutral 0.7 when
    # unknown, so a missing score doesn't silently suppress everything.
    ready = (readiness_value / 100) if readiness_value is not None else 0.7
    return round(ready * 0.5 + length * 0.3 + hour * 0.2, 4)


def _intensity(readiness_value: Optional[int]) -> str:
    """What kind of session the day supports. A low-readiness day gets an
    easy session, never "skip" -- consistency is the stated problem, and
    an assistant that talks you out of training is solving the wrong one."""
    if readiness_value is None:
        return "your call"
    if readiness_value >= readiness.BAND_PRIME:
        return "hard session"
    if readiness_value >= readiness.BAND_GOOD:
        return "moderate session"
    if readiness_value >= readiness.BAND_MODERATE:
        return "easy session"
    return "light movement or a walk"


def _advice(windows: List[Dict], readiness_value, load, calendar_available: bool) -> str:
    if not calendar_available:
        return "Calendar isn't connected, so I can't see your free time."
    if not windows:
        return "No free windows long enough in the next couple of days."

    best = windows[0]
    parts = [f"Best window: {best['label']} ({best['minutes']} min) — {best['intensity']}"]
    if readiness_value is not None:
        parts.append(f"readiness {readiness_value}")
    if load and load["under_target"]:
        worst = load["worst"]
        parts.append(f"{worst['label']} load is {worst['deficit_pct']}% under target")
    return " · ".join(parts)
