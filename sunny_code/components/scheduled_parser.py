"""Natural-language command parser for alarms and reminders (no LLM, regex only).

Extraction is staged rather than one giant regex: strip a trailing "called LABEL"
or "every RECURRENCE" clause first, then hand whatever's left to time_parse for
the actual time expression. Keeps each piece simple and independently testable.
"""

import re
from typing import Dict, Optional, Tuple

from sunny_code.components.time_parse import parse_recurrence

_CALLED_RE = re.compile(r"\s+called\s+['\"]?(.+?)['\"]?$", re.IGNORECASE)
_EVERY_RE = re.compile(r"\s+every\s+(.+)$", re.IGNORECASE)
_IN_DURATION_RE = re.compile(r"\s+in\s+(\d+\s+(?:minute|min|hour|hr)s?)$", re.IGNORECASE)
_ON_AT_RE = re.compile(r"\s+on\s+(\d{4}-\d{2}-\d{2})\s+at\s+(.+)$", re.IGNORECASE)
_AT_RE = re.compile(r"\s+at\s+(.+)$", re.IGNORECASE)
_LOCATION_RE = re.compile(r"\s+when\s+(?:i\s+)?(?:get\s+(?:to|home)\b.*|arrive\b.*|home\b.*)$", re.IGNORECASE)

_ALARM_CREATE_RE = re.compile(
    r"^(?:set\s+(?:an?\s+|a\s+recurring\s+)?alarm\s+for|wake\s+me\s+up\s+at)\s+(.+)$",
    re.IGNORECASE,
)
_ALARM_QUERY_TRIGGERS = [
    re.compile(r"^what\s+alarms?\s+(?:are|is)?\s*set\??$", re.IGNORECASE),
    re.compile(r"^when\s+is\s+my\s+next\s+alarm\??$", re.IGNORECASE),
    re.compile(r"^(?:show|list)\s+(?:my\s+)?alarms\??$", re.IGNORECASE),
]
_ALARM_CANCEL_ALL_RE = re.compile(r"^cancel\s+all\s+(?:my\s+)?alarms$", re.IGNORECASE)
_ALARM_CANCEL_ONE_RE = re.compile(r"^cancel\s+(?:my\s+)?(.+?)\s+alarms?$", re.IGNORECASE)

_REMINDER_CREATE_RE = re.compile(
    r"^(?:set\s+(?:a\s+recurring\s+)?reminder\s+to|remind\s+me\s+to)\s+(.+)$",
    re.IGNORECASE,
)
_REMINDER_QUERY_TRIGGERS = [
    re.compile(r"^what\s+are\s+my\s+reminders(?:\s+for\s+today)?\??$", re.IGNORECASE),
    re.compile(r"^(?:show|list)\s+(?:my\s+)?reminders\??$", re.IGNORECASE),
]
_REMINDER_CLEAR_ALL_RE = re.compile(r"^clear\s+all\s+reminders$", re.IGNORECASE)
# "delete" only used to be accepted -- "remove my reminder to call mom" (a
# real, natural phrasing) missed this entirely and fell through to
# tasks_parser's own delete/remove pattern, which tried to delete a task
# literally titled "my reminder to call mom" instead.
_REMINDER_DELETE_ONE_RE = re.compile(r"^(?:delete|remove|cancel)\s+(?:my\s+)?reminder\s+to\s+(.+)$", re.IGNORECASE)


class ScheduledCommandParser:
    """Parse alarm/reminder commands. Actions: create_alarm, create_reminder,
    query_alarms, query_reminders, cancel_alarm, cancel_all_alarms,
    delete_reminder, clear_all_reminders."""

    @staticmethod
    def _extract_called(text: str) -> Tuple[str, Optional[str]]:
        match = _CALLED_RE.search(text)
        if not match:
            return text.strip(), None
        return text[: match.start()].strip(), match.group(1).strip()

    @staticmethod
    def _extract_every(text: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Returns (remaining_text, recurrence, unparsed_phrase). unparsed_phrase
        is only set when an "every ..." clause was present but parse_recurrence
        didn't understand it (anything beyond daily/weekdays/a single weekday
        name, e.g. "every other week") -- previously that text was stripped
        and silently discarded either way, so a request like "every other
        week" created a one-time alarm/reminder with no indication the
        recurrence wasn't understood."""
        match = _EVERY_RE.search(text)
        if not match:
            return text.strip(), None, None
        raw_phrase = match.group(1).strip()
        recurrence = parse_recurrence("every " + raw_phrase)
        unparsed = None if recurrence else raw_phrase
        return text[: match.start()].strip(), recurrence, unparsed

    @classmethod
    def parse(cls, command: str) -> Optional[Tuple[str, Dict]]:
        stripped = command.strip()

        # --- Alarms ---
        for pattern in _ALARM_QUERY_TRIGGERS:
            if pattern.match(stripped):
                return "query_alarms", {}
        if _ALARM_CANCEL_ALL_RE.match(stripped):
            return "cancel_all_alarms", {}
        match = _ALARM_CANCEL_ONE_RE.match(stripped)
        if match:
            return "cancel_alarm", {"label_text": match.group(1).strip()}

        match = _ALARM_CREATE_RE.match(stripped)
        if match:
            rest, recurrence, recurrence_unparsed = cls._extract_every(match.group(1))
            rest, label = cls._extract_called(rest)
            time_expr = rest.strip()
            if not time_expr:
                return "create_alarm", {"error": "Needs a time — try \"set an alarm for 7am\""}
            return "create_alarm", {
                "time_expr": time_expr,
                "label": label or "Alarm",
                "recurrence": recurrence,
                "recurrence_unparsed": recurrence_unparsed,
            }

        # --- Reminders ---
        for pattern in _REMINDER_QUERY_TRIGGERS:
            if pattern.match(stripped):
                return "query_reminders", {}
        if _REMINDER_CLEAR_ALL_RE.match(stripped):
            return "clear_all_reminders", {}
        match = _REMINDER_DELETE_ONE_RE.match(stripped)
        if match:
            return "delete_reminder", {"label_text": match.group(1).strip()}

        match = _REMINDER_CREATE_RE.match(stripped)
        if match:
            rest = match.group(1)

            location_match = _LOCATION_RE.search(rest)
            if location_match:
                task = rest[: location_match.start()].strip()
                return "create_reminder", {
                    "error": f'Location-based reminders aren\'t supported yet (no location tracking) — '
                    f'I can still remind you to "{task}" at a specific time instead, e.g. "remind me to {task} at 5pm".'
                }

            rest, recurrence, recurrence_unparsed = cls._extract_every(rest)

            duration_match = _IN_DURATION_RE.search(rest)
            on_at_match = _ON_AT_RE.search(rest)
            at_match = _AT_RE.search(rest)

            if duration_match:
                task = rest[: duration_match.start()].strip()
                time_expr = "in " + duration_match.group(1)
            elif on_at_match:
                task = rest[: on_at_match.start()].strip()
                time_expr = f"on {on_at_match.group(1)} at {on_at_match.group(2)}"
            elif at_match:
                task = rest[: at_match.start()].strip()
                time_expr = at_match.group(1)
            else:
                task = rest.strip()
                time_expr = None

            if not task:
                return "create_reminder", {"error": 'Needs something to remind you about — try "remind me to call Mom at 5pm"'}
            if not time_expr:
                return "create_reminder", {"error": f'When should I remind you to {task}? Try "at 5pm" or "in 30 minutes".'}

            return "create_reminder", {
                "task": task, "time_expr": time_expr, "recurrence": recurrence,
                "recurrence_unparsed": recurrence_unparsed,
            }

        return None
