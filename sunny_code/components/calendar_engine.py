"""Google Calendar write engine -- create/delete events via natural
language. Same try_execute(command, source) -> (handled, success, message)
shape as scheduled_engine.py (the alarms/reminders engine, the closest
existing analog: create + cancel by natural phrasing).

Needs the full `calendar` OAuth scope, not just calendar.readonly -- see
google_auth.SCOPES and sunny-vault/docs/architecture/google-integration.md
for what that means for anyone who connected before this scope widened.

Stateless -- no local DB, unlike tasks/lists/scheduled. Google Calendar
itself is the only store; every call goes straight through to the live API
via google_calendar.py.
"""

import logging
from typing import Dict, Optional, Tuple

from sunny_code.components import google_calendar
from sunny_code.components.calendar_parser import CalendarCommandParser
from sunny_code.components.request_log import log_unfulfilled
from sunny_code.components.time_parse import parse_time_expression

logger = logging.getLogger(__name__)

DEFAULT_EVENT_DURATION_MINUTES = 60


class CalendarEngine:
    """Natural-language calendar-event create/delete."""

    async def try_execute(self, command: str, source: Optional[str] = None) -> Tuple[bool, bool, Optional[str]]:
        """Returns (handled, success, message). handled=False means this
        wasn't recognized as a calendar-event command at all."""
        parsed = CalendarCommandParser.parse(command)
        if parsed is None:
            return False, False, None

        action, data = parsed

        if "error" in data:
            log_unfulfilled("calendar_command", f'"{command}" — {data["error"]}')
            return True, False, data["error"]

        if action == "create_event":
            success, message = self._create_event(data)
        elif action == "delete_event":
            success, message = self._delete_event(data)
        else:
            success, message = False, "Unknown calendar action"

        if not success:
            log_unfulfilled("calendar_command", f'"{command}" — {message}')

        return True, success, message

    def _create_event(self, data: Dict) -> Tuple[bool, str]:
        start = parse_time_expression(data["time_expr"])
        if start is None:
            return False, (
                f'Couldn\'t understand the time "{data["time_expr"]}" — '
                'try something like "3pm" or "6:30pm tomorrow"'
            )

        result = google_calendar.create_event(data["title"], start, duration_minutes=DEFAULT_EVENT_DURATION_MINUTES)
        if result is None:
            return False, "Couldn't reach Google Calendar — is it connected? Check /console."

        when = start.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
        return True, f'Added "{data["title"]}" to your calendar for {when} ({DEFAULT_EVENT_DURATION_MINUTES} min).'

    def _delete_event(self, data: Dict) -> Tuple[bool, str]:
        match = google_calendar.find_event_by_title(data["title"])
        if match is None:
            return False, f'Couldn\'t find a calendar event matching "{data["title"]}" in the next two weeks.'

        ok = google_calendar.delete_event(match["calendar_id"], match["event_id"])
        if not ok:
            return False, "Couldn't reach Google Calendar to delete that — try again or check /console."

        return True, f'Removed "{match["title"]}" from your calendar.'
