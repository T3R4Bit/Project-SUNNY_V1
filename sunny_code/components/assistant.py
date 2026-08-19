"""Shared message-routing logic: one entry point used by both the web chatbot
and the Discord bot, so behavior stays identical across interfaces.

Routing order: pending follow-up (if any) -> help trigger -> task command
(natural phrasing or legacy !task) -> morning/evening briefing -> briefing
Q&A fallback.
"""

import time
from typing import Dict, Optional

from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.tasks_parser import TaskCommandParser

HELP_TEXT = """🌞 Here's what I can do — no LLM, plain pattern matching:

TASKS (real data, backed by tasks.db)
  add <title> to my tasks       — create a task
  show my tasks                 — list open tasks
  mark <id-or-title> as done    — complete a task
  delete <id-or-title>          — remove a task
  Examples: "add buy milk to my tasks", "mark buy milk as done"

BRIEFINGS
  morning / evening             — full briefing

QUESTIONS
  Ask about tasks and I'll answer for real.
  Weather, calendar, email, commute, health, motorsports, and news
  aren't connected to a real API yet, so I'll say so instead of
  making something up — every one of those gets logged to
  sunny-vault/log/requests.md.

Type "help" any time to see this again."""

_HELP_TRIGGERS = ("", "help", "commands", "info", "what can you do", "what can i ask")
_CANCEL_WORDS = ("cancel", "nevermind", "never mind", "stop", "skip", "forget it")
_BRIEFING_KEYWORDS = ("morning", "morning briefing", "evening", "evening briefing")

# Tiny per-session conversation state — just enough to support one pending
# follow-up question ("what should the task be called?"). This is a personal,
# single-user tool, so a plain in-memory dict keyed by session_id is enough;
# no database or persistence across restarts needed. Entries expire on their
# own (see _PENDING_TTL_SECONDS) so a stale follow-up can't hijack an
# unrelated message sent long afterward.
_pending: Dict[str, Dict] = {}
_PENDING_TTL_SECONDS = 300


def _get_pending(session_id: str) -> Optional[Dict]:
    entry = _pending.get(session_id)
    if entry and time.time() - entry["ts"] > _PENDING_TTL_SECONDS:
        _pending.pop(session_id, None)
        return None
    return entry


def _set_pending(session_id: str, awaiting: str) -> None:
    _pending[session_id] = {"awaiting": awaiting, "ts": time.time()}


async def _create_task_from_reply(reply: str, tasks_engine: TaskEngine, session_id: str) -> str:
    """Treat a follow-up reply as a task title (optionally with --flags) and create it."""
    phrase, flags = TaskCommandParser._split_flags(reply)
    title = phrase.strip().strip('"\'')

    if not title:
        _set_pending(session_id, "task_title")
        return 'Still need a title for this one — what should I call it? (or say "cancel")'

    command = f"add {title} to my tasks" + (f" {flags}" if flags else "")
    _, message = await tasks_engine.execute_command(command)
    return message


async def handle_message(
    text: str,
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    session_id: str = "default",
) -> str:
    """Route one free-text message and return the response text."""
    stripped = text.strip()
    lowered = stripped.lower().strip("? ")

    pending = _get_pending(session_id)
    if pending and pending.get("awaiting") == "task_title":
        if lowered in _CANCEL_WORDS:
            _pending.pop(session_id, None)
            return "No worries — cancelled."

        # If this looks like an unrelated command (not just a bare title),
        # abandon the follow-up and handle it normally instead of creating
        # a task titled "show my tasks".
        peek_cmd_type, _, _ = TaskCommandParser.parse_command(stripped)
        is_other_command = peek_cmd_type not in ("unknown", "add")
        is_help = lowered in _HELP_TRIGGERS
        is_briefing_kw = lowered in _BRIEFING_KEYWORDS
        if not (is_other_command or is_help or is_briefing_kw):
            _pending.pop(session_id, None)
            return await _create_task_from_reply(stripped, tasks_engine, session_id)

        _pending.pop(session_id, None)
        # falls through to normal handling below

    if lowered in _HELP_TRIGGERS:
        return HELP_TEXT

    cmd_type, success, _ = TaskCommandParser.parse_command(stripped)

    if cmd_type == "add" and not success:
        # The only real failure mode for a natural "add" is a missing title
        # (e.g. bare "make a task") — ask for it instead of just erroring out.
        _set_pending(session_id, "task_title")
        return 'Sure — what should I call it? (or say "cancel")'

    if cmd_type != "unknown":
        _, message = await tasks_engine.execute_command(stripped)
        return message

    if lowered in ("morning", "morning briefing"):
        return await briefing_engine.generate_morning_briefing()

    if lowered in ("evening", "evening briefing"):
        return await briefing_engine.generate_evening_briefing()

    return await briefing_engine.answer_question(stripped)
