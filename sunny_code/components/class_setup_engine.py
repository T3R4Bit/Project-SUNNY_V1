"""The class-setup wizard's actual work, called from assistant.py's
multi-step pending state (semester -> per-class name/syllabus/confirm
loop), same split as project_engine.py: this module does the real work,
assistant.py owns the conversation state.

Two-phase per class, matching project_engine's confirm-before-building
pattern (real calendar writes are higher-stakes than a project folder):
preview() parses the syllabus and returns a recap, nothing is created
yet; commit() is only called after the user confirms, and does the real
work -- a recurring calendar event per meeting-time block, an all-day
event per due date/exam, the class memory file, and a deadline tracker
per due date/exam for the proactive #reminders ping.
"""

import logging
from datetime import date, datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Tuple

from sunny_code.components import class_deadlines, class_memory, google_calendar, syllabus_parser

logger = logging.getLogger(__name__)

_WEEKDAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _first_occurrence(semester_start: date, days: List[str], start_time: str) -> Optional[datetime]:
    """The earliest date on/after semester_start whose weekday is one of
    `days`, combined with start_time -- the first real occurrence of a
    recurring class, since the semester doesn't necessarily start on one
    of the class's own meeting days. None on an unrecognized weekday name
    (already validated by syllabus_parser, but never trust a second time
    for free)."""
    try:
        target_weekdays = {_WEEKDAY_INDEX[d.strip().lower()] for d in days}
    except KeyError:
        return None
    d = semester_start
    for _ in range(7):
        if d.weekday() in target_weekdays:
            break
        d += timedelta(days=1)
    else:
        return None
    hour, minute = (int(x) for x in start_time.split(":"))
    return datetime.combine(d, dt_time(hour=hour, minute=minute))


def _duration_minutes(start_time: str, end_time: str) -> int:
    sh, sm = (int(x) for x in start_time.split(":"))
    eh, em = (int(x) for x in end_time.split(":"))
    minutes = (eh * 60 + em) - (sh * 60 + sm)
    return minutes if minutes > 0 else 60


def recap(parsed: Dict) -> str:
    """The confirm-step message, re-shareable as-is whenever parsed data
    changes (a fresh parse, or the user correcting a wrong/missing
    class_name — see assistant.py's confirm-step handling, which accepts
    a reply that isn't yes/no as a name correction and re-shows this)."""
    class_name = parsed.get("class_name", "").strip()
    name_line = f'"{class_name}"' if class_name else "(couldn't find a class name in the syllabus — reply with one)"
    lines = [f"Here's what I found — class: {name_line}"]
    semester_start = parsed.get("semester_start", "")
    semester_end = parsed.get("semester_end", "")
    if parsed["meeting_times"]:
        if semester_start and semester_end:
            lines.append(f"- Runs {semester_start} to {semester_end}")
        else:
            lines.append("- Couldn't find this syllabus's own start/end dates — recurring meeting times won't be added")
        for mt in parsed["meeting_times"]:
            days_str = "/".join(d[:3] for d in mt["days"])
            loc = f" @ {mt['location']}" if mt.get("location") else ""
            lines.append(f"- Meets {days_str} {mt['start_time']}-{mt['end_time']}{loc}")
    else:
        lines.append("- No fixed meeting time found")
    lines.append(f"- {len(parsed['due_dates'])} due date(s), {len(parsed['exams'])} exam(s)")
    lines.append('Set this up — calendar events plus reminders 2 days before and the day of? "yes"/"no", or reply with the correct class name if I got it wrong.')
    return "\n".join(lines)


async def preview(semester_name: str, syllabus_text: str) -> Tuple[bool, str, Optional[Dict]]:
    """Parses the syllabus only -- creates nothing. Returns
    (ok, message, parsed_data). ok=False means parsing failed and
    `message` is the reason; ok=True means `message` is recap(parsed),
    ready for the user to confirm (or correct the class name).
    semester_name (e.g. "Fall 2026") is only a year/season hint for
    resolving bare dates in the source text -- the semester's actual
    start/end dates come back as part of `parsed`, pulled from the
    syllabus itself, not asked of the user."""
    parsed = await syllabus_parser.parse_syllabus(semester_name, syllabus_text)
    if parsed is None:
        return False, "Couldn't parse that syllabus — try again, or paste it differently.", None
    return True, recap(parsed), parsed


def commit(semester_name: str, parsed: Dict) -> str:
    """Creates everything from an already-parsed, already-confirmed
    syllabus. Sync, not async -- matches calendar_engine.py's own
    precedent of calling google_calendar's write functions directly
    rather than wrapping each one in asyncio.to_thread; callers that want
    this off the event loop (it can make several real API calls in a
    row) should wrap the whole call, e.g. asyncio.to_thread(commit, ...).
    A single calendar-event failure is logged and skipped, not fatal to
    the rest -- same fail-quiet spirit as google_calendar.py itself.
    parsed["class_name"] must already be non-empty -- assistant.py's
    confirm-step gate guarantees this before commit() is ever called.

    parsed["semester_start"]/["semester_end"] came from this specific
    syllabus, not a wizard-level date the user typed -- if the syllabus
    genuinely didn't state them, recurring meeting events are skipped
    (due dates/exams are self-contained dates, unaffected) rather than
    guessing a range to build a recurrence on."""
    class_name = parsed["class_name"]
    semester_start = date.fromisoformat(parsed["semester_start"]) if parsed.get("semester_start") else None
    semester_end = date.fromisoformat(parsed["semester_end"]) if parsed.get("semester_end") else None

    created_events = 0
    dates_missing = False
    for mt in parsed["meeting_times"]:
        if semester_start is None or semester_end is None:
            dates_missing = True
            continue
        start_dt = _first_occurrence(semester_start, mt["days"], mt["start_time"])
        if start_dt is None:
            logger.warning(f"class_setup_engine: couldn't resolve meeting days for {class_name}: {mt['days']}")
            continue
        event = google_calendar.create_recurring_event(
            class_name,
            start=start_dt,
            duration_minutes=_duration_minutes(mt["start_time"], mt["end_time"]),
            days=mt["days"],
            until=semester_end,
            location=mt.get("location"),
        )
        if event is not None:
            created_events += 1

    key_dates = []
    for entry in parsed["due_dates"]:
        google_calendar.create_all_day_event(f"{class_name}: {entry['title']}", date.fromisoformat(entry["date"]))
        class_deadlines.create_deadline(class_name, entry["title"], entry["date"], "due")
        key_dates.append({"title": entry["title"], "date": entry["date"], "kind": "due"})

    for entry in parsed["exams"]:
        google_calendar.create_all_day_event(f"{class_name}: {entry['title']}", date.fromisoformat(entry["date"]))
        class_deadlines.create_deadline(class_name, entry["title"], entry["date"], "exam")
        key_dates.append({"title": entry["title"], "date": entry["date"], "kind": "exam"})

    class_memory.save_class(class_name, semester_name, parsed.get("summary", ""), key_dates)

    logger.info(f"Class set up: {class_name!r} ({semester_name}) — {created_events} recurring events, {len(key_dates)} dates")
    message = (
        f'Set up "{class_name}" — {created_events} recurring class time(s), '
        f'{len(parsed["due_dates"])} due date(s), {len(parsed["exams"])} exam(s). '
        f"Reminders will post 2 days before and the day of each."
    )
    if dates_missing:
        message += " (Couldn't find this syllabus's own start/end dates, so recurring meeting times weren't added.)"
    return message
