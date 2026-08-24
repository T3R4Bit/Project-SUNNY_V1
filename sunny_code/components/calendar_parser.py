"""Natural-language command parser for creating/deleting real Google Calendar
events (no LLM, regex only) -- same shape as scheduled_parser.py, and reuses
time_parse.parse_time_expression for the actual time resolution rather than
inventing a second time grammar.

Trigger phrasing is deliberately narrow and requires the word "calendar" (or
"event" for delete) -- this runs in the same routing tier as scheduled_engine
(alarms/reminders) and ahead of tasks_parser's much broader bare "delete X"
pattern, so staying unambiguous here matters more than covering every
possible phrasing.
"""

import re
from typing import Dict, Optional, Tuple

_CREATE_RE = re.compile(
    r"^(?:add|schedule|create)\s+(?:an?\s+event\s+)?(?:called\s+)?(.+?)\s+"
    r"(?:to|on)\s+my\s+calendar\s+(?:for|at|on)\s+(.+)$",
    re.IGNORECASE,
)
_DELETE_RE = re.compile(
    r"^(?:cancel|delete|remove)\s+(?:the\s+|my\s+)?(.+?)\s+"
    r"(?:from\s+(?:my\s+)?calendar|calendar\s+event|event)$",
    re.IGNORECASE,
)


class CalendarCommandParser:
    """Parse calendar-event commands. Actions: create_event, delete_event."""

    @classmethod
    def parse(cls, command: str) -> Optional[Tuple[str, Dict]]:
        stripped = command.strip()

        match = _CREATE_RE.match(stripped)
        if match:
            title, time_expr = match.group(1).strip(), match.group(2).strip()
            if not title:
                return "create_event", {"error": 'Needs a title — try "add dentist appointment to my calendar at 3pm"'}
            return "create_event", {"title": title, "time_expr": time_expr}

        match = _DELETE_RE.match(stripped)
        if match:
            title = match.group(1).strip()
            if not title:
                return None
            return "delete_event", {"title": title}

        return None
