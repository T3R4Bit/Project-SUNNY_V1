"""Alarm/reminder engine — combines DB, parsing, and time resolution.

Storage + query/cancel only. Nothing here makes noise by itself — see
discord_bot.py's scheduled-items loop for the actual "ping when due" delivery,
which only runs once the Discord bot is connected.
"""

import logging
import re
from datetime import date, datetime, time
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



# Cheap prefilter for the extraction fallback below. try_execute() runs on
# every message that reaches it, so calling the LLM whenever the regex
# missed would mean an API call per unmatched message -- most of which are
# ordinary chat. This only has to be generous: a false positive costs one
# extraction that returns kind != "reminder" and falls through, while a
# false negative costs the whole feature.
# Hour used when a reminder has a date but no time. 9am is the start of
# a working day rather than a neutral midnight, which would fire while
# asleep and be missed.
DEFAULT_REMINDER_HOUR = 9

_REMINDER_HINT = re.compile(
    r"(remind|reminder|wake me|alarm|don'?t let me forget|ping me|nudge me)",
    re.IGNORECASE,
)


def _looks_like_a_reminder(text: str) -> bool:
    return bool(_REMINDER_HINT.search(text or ""))






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
            # The regex is the fast path and stays the fast path. Only when
            # it misses AND the text mentions reminding does extraction get
            # a turn -- "remind me to call mom tomorrow at 7pm" used to
            # become a TASK with a due date, which never fires. A reminder
            # that silently becomes a note is worse than one that errors.
            if not _looks_like_a_reminder(command):
                return False, False, None
            recovered = await self._extract_reminder(command, source)
            if recovered is None:
                return False, False, None
            return recovered

        action, data = parsed

        if "error" in data:
            # A partial match: it read as a reminder but the time didn't
            # parse. Extraction resolves relative dates the regex cannot
            # ("a week friday", "after my last class"), so it gets a turn
            # here too before the error is returned.
            recovered = await self._extract_reminder(command, source)
            if recovered is not None:
                return recovered
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

    async def _extract_reminder(self, command: str, source: Optional[str]):
        """Try to recover a reminder the regex could not read.

        Returns a (handled, success, message) tuple, or None to let the
        caller fall through unchanged. None rather than a failure tuple
        matters: an extraction that comes back as a task, or does not come
        back at all, must leave the message available to every other
        feature rather than consuming it.
        """
        from sunny_code.components import extract

        result = await extract.capture(command)
        if result is None or result.get("kind") != "reminder":
            return None
        if not result.get("due_date"):
            # A reminder with no time is not a reminder. Let it fall
            # through -- the capture path will file it as a task, which is
            # the honest outcome for "remind me to buy milk".
            return None

        # Built directly from the structured fields. The first version
        # formatted them back into a string and handed it to
        # parse_time_expression, which is a parser for HUMAN expressions
        # ("at 5pm", "in 30 minutes") and returned None for a bare ISO
        # date -- so every date-only reminder silently fell through.
        # Re-parsing data you already have structured is a bug waiting to
        # happen, and this was it.
        try:
            day = date.fromisoformat(result["due_date"])
        except (TypeError, ValueError):
            logger.warning(f"extraction produced a bad date: {result['due_date']!r}")
            return None

        assumed_time = False
        if result.get("due_time"):
            hour, _, minute = result["due_time"].partition(":")
            trigger_at = datetime.combine(day, time(int(hour), int(minute or 0)))
        else:
            # A reminder needs a time; extract deliberately never invents
            # one. Rather than failing, assume a sensible hour and SAY so
            # in the reply -- an assumption you can see and correct beats
            # an error that drops the reminder entirely.
            trigger_at = datetime.combine(day, time(DEFAULT_REMINDER_HOUR, 0))
            assumed_time = True

        if trigger_at < datetime.now():
            logger.info(f"extraction produced a past time: {trigger_at}")
            return None

        title = result.get("title") or command
        self.db.create_item("reminder", title, trigger_at, source=source)
        stamp = trigger_at.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
        trace.mark_route("scheduled_engine", "extracted", confidence="heuristic",
                         function="extract.capture")
        logger.info(f"Reminder recovered by extraction: {title!r} at {trigger_at}")
        note = " — you didn't say a time, so I picked one" if assumed_time else ""
        return True, True, f"I'll remind you to {title} on {stamp}{note}"

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
