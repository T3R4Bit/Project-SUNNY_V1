"""Shared message-routing logic: one entry point used by both the web chatbot
and the Discord bot, so behavior stays identical across interfaces.

Routing order: help trigger -> task command (natural phrasing or legacy !task)
-> morning/evening briefing -> briefing Q&A fallback.
"""

from sunny.components.briefing import BriefingEngine
from sunny.components.tasks_engine import TaskEngine
from sunny.components.tasks_parser import TaskCommandParser

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


async def handle_message(text: str, tasks_engine: TaskEngine, briefing_engine: BriefingEngine) -> str:
    """Route one free-text message and return the response text."""
    stripped = text.strip()
    lowered = stripped.lower().strip("? ")

    if lowered in _HELP_TRIGGERS:
        return HELP_TEXT

    cmd_type, _, _ = TaskCommandParser.parse_command(stripped)
    if cmd_type != "unknown":
        _, message = await tasks_engine.execute_command(stripped)
        return message

    if lowered in ("morning", "morning briefing"):
        return await briefing_engine.generate_morning_briefing()

    if lowered in ("evening", "evening briefing"):
        return await briefing_engine.generate_evening_briefing()

    return await briefing_engine.answer_question(stripped)
