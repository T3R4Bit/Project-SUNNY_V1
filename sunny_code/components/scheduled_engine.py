"""Alarm/reminder engine — combines DB, parsing, and time resolution.

Storage + query/cancel only. Nothing here makes noise by itself — see
discord_bot.py's scheduled-items loop for the actual "ping when due" delivery,
which only runs once the Discord bot is connected.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

from sunny_code.components.scheduled_db import ScheduledDB
from sunny_code.components.scheduled_parser import ScheduledCommandParser
from sunny_code.components.time_parse import parse_time_expression
from sunny_code.components.request_log import log_unfulfilled
from sunny_code.components import trace

logger = logging.getLogger(__name__)


def _format_when(iso_str: str, fmt: str) -> str:
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime(fmt).replace(" 0", " ")


class ScheduledEngine:
    """High-level alarm/reminder management with command execution."""

    def __init__(self, db: ScheduledDB):
        self.db = db
        # Optional async callable, invoked after create/cancel — mirrors
        # TaskEngine.on_change so the Discord dashboard-style refresh pattern
        # is consistent, even though alarms/reminders don't have a dashboard yet.
        self.on_change = None

    async def try_execute(self, command: str, source: str = None) -> Tuple[bool, bool, Optional[str]]:
        """Returns (handled, success, message). handled=False means this wasn't
        recognized as an alarm/reminder command at all."""
        parsed = ScheduledCommandParser.parse(command)
        if parsed is None:
            return False, False, None

        action, data = parsed

        if "error" in data:
            log_unfulfilled("scheduled_command", f'"{command}" — {data["error"]}')
            return True, False, f"{data['error']}"

        if action == "create_alarm":
            success, message = self._create_alarm(data, source)
        elif action == "create_reminder":
            success, message = self._create_reminder(data, source)
        elif action == "query_alarms":
            success, message = True, self._query_alarms()
        elif action == "query_reminders":
            success, message = True, self._query_reminders()
        elif action == "cancel_alarm":
            success, message = self._cancel_alarm(data)
        elif action == "cancel_all_alarms":
            success, message = True, self._cancel_all_alarms()
        elif action == "delete_reminder":
            success, message = self._delete_reminder(data)
        elif action == "clear_all_reminders":
            success, message = True, self._clear_all_reminders()
        else:
            success, message = False, "Unknown scheduled-item action"

        if not success:
            log_unfulfilled("scheduled_command", f'"{command}" — {message}')
        elif action not in ("query_alarms", "query_reminders") and self.on_change:
            try:
                await self.on_change()
            except Exception as e:
                logger.error(f"on_change callback failed: {e}", exc_info=True)

        return True, success, message

    @staticmethod
    def _recur_note(data: Dict) -> str:
        """Repeat-schedule suffix for the create_alarm/create_reminder reply.
        If an "every ..." clause was present but not understood, say so
        instead of silently creating a one-time item with no explanation --
        see ScheduledCommandParser._extract_every."""
        if data.get("recurrence"):
            return f" (repeats {data['recurrence']})"
        if data.get("recurrence_unparsed"):
            trace.note_guard(f'recurrence phrase "every {data["recurrence_unparsed"]}" not understood — created as one-time')
            return f' — didn\'t understand "every {data["recurrence_unparsed"]}" as a repeat schedule, created as one-time'
        return ""

    def _create_alarm(self, data: Dict, source: Optional[str]) -> Tuple[bool, str]:
        trigger_at = parse_time_expression(data["time_expr"])
        if trigger_at is None:
            return False, f'Couldn\'t understand the time "{data["time_expr"]}" — try something like "7:00 AM" or "6:30pm tomorrow"'

        self.db.create_item("alarm", data["label"], trigger_at, recurrence=data.get("recurrence"), source=source)
        when = trigger_at.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
        return True, f'Alarm "{data["label"]}" set for {when}{self._recur_note(data)}'

    def _create_reminder(self, data: Dict, source: Optional[str]) -> Tuple[bool, str]:
        trigger_at = parse_time_expression(data["time_expr"])
        if trigger_at is None:
            return False, f'Couldn\'t understand the time "{data["time_expr"]}" — try something like "at 5pm" or "in 30 minutes"'

        self.db.create_item("reminder", data["task"], trigger_at, recurrence=data.get("recurrence"), source=source)
        when = trigger_at.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
        return True, f'I\'ll remind you to {data["task"]} on {when}{self._recur_note(data)}'

    def _query_alarms(self) -> str:
        alarms = self.db.get_active_items(kind="alarm")
        if not alarms:
            return "No alarms set."
        lines = []
        for a in alarms:
            when = _format_when(a["trigger_at"], "%a %I:%M %p")
            recur = f" (repeats {a['recurrence']})" if a["recurrence"] else ""
            lines.append(f"{a['label']} — {when}{recur}")
        return "\n".join(lines)

    def _query_reminders(self) -> str:
        reminders = self.db.get_active_items(kind="reminder")
        if not reminders:
            return "No reminders set."
        lines = []
        for r in reminders:
            when = _format_when(r["trigger_at"], "%a %b %d, %I:%M %p")
            recur = f" (repeats {r['recurrence']})" if r["recurrence"] else ""
            lines.append(f"{r['label']} — {when}{recur}")
        return "\n".join(lines)

    def _cancel_alarm(self, data: Dict) -> Tuple[bool, str]:
        active = self.db.get_active_items(kind="alarm")
        if not active:
            return False, "No active alarms to cancel."

        matches = self.db.find_active("alarm", data["label_text"])

        if not matches:
            # Most alarms just use the default "Alarm" label, so "cancel my 7am
            # alarm" means the one at 7am, not one literally labeled "7am".
            target_time = parse_time_expression(data["label_text"])
            if target_time:
                matches = [
                    a for a in active
                    if datetime.fromisoformat(a["trigger_at"]).time() == target_time.time()
                ]

        if not matches:
            return False, f'No active alarm matching "{data["label_text"]}"'
        if len(matches) > 1:
            labels = ", ".join(f'"{m["label"]}"' for m in matches[:5])
            return False, f'That matches multiple alarms: {labels} — try being more specific'
        self.db.deactivate(matches[0]["id"])
        return True, f'Cancelled alarm "{matches[0]["label"]}"'

    def _cancel_all_alarms(self) -> str:
        count = self.db.deactivate_all("alarm")
        return f"Cancelled {count} alarm(s)" if count else "No active alarms to cancel."

    def _delete_reminder(self, data: Dict) -> Tuple[bool, str]:
        if not self.db.get_active_items(kind="reminder"):
            return False, "No active reminders to delete."
        matches = self.db.find_active("reminder", data["label_text"])
        if not matches:
            return False, f'No active reminder matching "{data["label_text"]}"'
        if len(matches) > 1:
            labels = ", ".join(f'"{m["label"]}"' for m in matches[:5])
            return False, f'That matches multiple reminders: {labels} — try being more specific'
        self.db.deactivate(matches[0]["id"])
        return True, f'Deleted reminder "{matches[0]["label"]}"'

    def _clear_all_reminders(self) -> str:
        count = self.db.deactivate_all("reminder")
        return f"Cleared {count} reminder(s)" if count else "No active reminders to clear."
