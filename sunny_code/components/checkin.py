"""Daily check-in questions asked at the end of the day.

Deliberately a framework with one question in it, not a hardcoded migraine
prompt. The first question is migraine yes/no, but the second and third
(sleep quality, mood, soreness) should cost a dict entry rather than
another pass through briefing.py, assistant.py and the storage layer.

WHY THIS EXISTS AT ALL
----------------------
Almost everything else Sunny stores can be reconstructed after the fact:
Garmin retains sleep and HR history server-side, the calendar is the
calendar, task history is in the vault. Check-in answers cannot. A night
that goes unasked is a permanently missing row, and the value of this data
is entirely in correlation over months -- "migraines follow nights under
six hours", "migraines follow barometric swings" -- which a gappy series
cannot support. That is why this shipped before the scoring, the charts
and the dashboards that will eventually read it.

Barometric pressure is captured on the same day key by daily_ingest.py for
exactly this reason: the pressure/migraine correlation needs both series
to start on the same day, and pressure for a day already past cannot be
backfilled from a free weather API.

STORAGE
-------
Answers go to metrics_store under `health.<id>` and are also appended to
`sunny-vault/log/checkins.md` so they are readable and editable in Obsidian
like everything else. metrics_store is the queryable copy; the vault file
is the human one.

There is no separate "was this asked today" state. An answer's presence in
metrics_store for today's logging day *is* the record that it was
answered, which means the state cannot drift out of sync with the data --
and re-answering simply overwrites, so a correction late at night does the
right thing.

DAY ATTRIBUTION
---------------
Every answer files against day_boundary.logging_day(), not date.today().
Answering "yes" at 2am records a migraine for the day you were awake for.
See day_boundary's module docstring.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sunny_code.components import day_boundary, metrics_store
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

TYPE_YES_NO = "yes_no"
TYPE_SCALE = "scale_1_5"

# Each question's `metric` is the metrics_store series name it writes to.
# Keep the `health.` prefix -- the series endpoint groups the dashboard's
# health panel by it.
QUESTIONS: List[Dict] = [
    {
        "id": "migraine",
        "metric": "health.migraine",
        "type": TYPE_YES_NO,
        "prompt": "Did you have a migraine today?",
        # Asked even on days with no other health signal -- a "no" is as
        # much a data point as a "yes", and a series of only "yes" rows
        # would make every correlation look total.
        "always_ask": True,
    },
]

_BY_ID = {q["id"]: q for q in QUESTIONS}

_YES = {"yes", "y", "yeah", "yep", "yup", "ya", "true", "1", "affirmative", "i did", "unfortunately"}
_NO = {"no", "n", "nope", "nah", "none", "false", "0", "negative", "i didnt", "i didn't", "thankfully"}


def _log_path():
    return get_settings().project_root / "sunny-vault" / "log" / "checkins.md"


def parse_answer(question: Dict, reply: str) -> Optional[float]:
    """Turn a natural reply into a stored value, or None if it does not
    read as an answer to this question at all.

    None matters: it is how the caller tells "the user answered no" from
    "the user said something unrelated and the question is still open."
    Conflating those would record a 0 for every stray message that arrived
    while a check-in was pending.
    """
    cleaned = reply.strip().lower().strip("?!. ")
    if not cleaned:
        return None

    if question["type"] == TYPE_YES_NO:
        if cleaned in _YES:
            return 1.0
        if cleaned in _NO:
            return 0.0
        # A leading yes/no still counts ("no, slept fine"), but only as a
        # prefix -- searching anywhere in the string would read "I don't
        # know" as a yes on the "know"/"no" boundary.
        first = cleaned.split()[0].strip(",")
        if first in _YES:
            return 1.0
        if first in _NO:
            return 0.0
        return None

    if question["type"] == TYPE_SCALE:
        try:
            value = float(cleaned.split()[0])
        except (ValueError, IndexError):
            return None
        return value if 1 <= value <= 5 else None

    return None


def pending(day: Optional[str] = None) -> List[Dict]:
    """Questions not yet answered for `day` (defaults to today's logging
    day), in registry order."""
    day = day or day_boundary.day_key()
    return [q for q in QUESTIONS if metrics_store.get_for_day(q["metric"], day) is None]


def answered(day: Optional[str] = None) -> Dict[str, float]:
    """Everything already answered for `day`, as {question_id: value}."""
    day = day or day_boundary.day_key()
    out = {}
    for q in QUESTIONS:
        value = metrics_store.get_for_day(q["metric"], day)
        if value is not None:
            out[q["id"]] = value
    return out


def next_question(day: Optional[str] = None) -> Optional[Dict]:
    """The next unanswered question, or None if the check-in is complete.
    Asking one at a time is deliberate -- a nightly brief that ends in a
    list of four questions gets ignored wholesale, which produces no data
    at all rather than partial data."""
    outstanding = pending(day)
    return outstanding[0] if outstanding else None


def record_answer(question_id: str, value: float, day: Optional[str] = None) -> None:
    """Store an answer for `day` (default: today's logging day). Writing
    the same question twice overwrites -- corrections are expected."""
    question = _BY_ID.get(question_id)
    if question is None:
        logger.error(f"Unknown check-in question {question_id!r}")
        return

    day = day or day_boundary.day_key()
    metrics_store.record(question["metric"], value, ts=day)
    _append_to_vault(question, value, day)
    logger.info(f"Check-in recorded: {question_id}={value} for {day}")


def _append_to_vault(question: Dict, value: float, day: str) -> None:
    """Mirror the answer into the Obsidian-readable log. Best-effort: the
    metrics_store write above is the authoritative one, so a vault write
    failure must not lose the answer or raise into the caller."""
    if question["type"] == TYPE_YES_NO:
        rendered = "yes" if value else "no"
    else:
        rendered = f"{value:g}"

    line = f"- {day} · {question['id']}: {rendered} _(recorded {datetime.now():%H:%M})_\n"
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            header = (
                "---\nid: checkins\ntype: log\ntags: [health, checkin]\n---\n\n"
                "# Daily check-ins\n\n"
                "Appended by `checkin.py`. Dates are logging days "
                "(a day rolls over at 5am, not midnight) — see "
                "`day_boundary.py`.\n\n"
            )
            path.write_text(header, encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as e:
        logger.error(f"Could not append check-in to vault log: {e}", exc_info=True)


def prompt_text(day: Optional[str] = None) -> Optional[str]:
    """The line to append to the evening brief, or None if nothing is
    outstanding. Returning None rather than an empty string lets callers
    skip the whole section with a plain `if`."""
    question = next_question(day)
    return question["prompt"] if question else None


def summary_line(day: Optional[str] = None) -> Optional[str]:
    """One-line recap of what was answered, for a brief that runs after the
    check-in is already complete. None if nothing was answered."""
    results = answered(day)
    if not results:
        return None
    parts = []
    for q in QUESTIONS:
        if q["id"] not in results:
            continue
        value = results[q["id"]]
        if q["type"] == TYPE_YES_NO:
            parts.append(f"{q['id']}: {'yes' if value else 'no'}")
        else:
            parts.append(f"{q['id']}: {value:g}")
    return " · ".join(parts) if parts else None
