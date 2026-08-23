"""Shared message-routing logic: one entry point used by both the web chatbot
and the Discord bot, so behavior stays identical across interfaces.

Routing order: pending follow-up (if any) -> help trigger -> list command ->
alarm/reminder command -> task command (natural phrasing or legacy !task) ->
morning/evening briefing -> briefing Q&A fallback.

Lists and alarms/reminders are checked *before* tasks on purpose: their
trigger phrases require a specific keyword ("list"/"alarm"/"reminder"), while
tasks' bare "delete X"/"mark X as done" patterns are deliberately broad and
would otherwise swallow "delete my reminder to X" or "remove milk from my
list" before the more specific parser ever saw it.
"""

import time
from typing import Dict, Optional

from sunny_code.components import category_store, health_check, setup_guides
from sunny_code.components.briefing import BriefingEngine, OnChunk
from sunny_code.components.device import device_from_session
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.lists_parser import ListCommandParser
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.scheduled_parser import ScheduledCommandParser
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.tasks_parser import TaskCommandParser

HELP_TEXT = """Here's what I can do:

TASKS (real data, stored in the vault)
  add <title> to my tasks — create a task
  show my tasks — list open tasks
  mark <id-or-title> as done — complete a task
  delete <id-or-title> — remove a task

LISTS (groceries, packing, anything checkable)
  add <item> to my <name> list — creates the list if it's new
  what's on my <name> list — show items
  remove <item> from my <name> list
  my lists — show all your lists

ALARMS & REMINDERS
  set an alarm for 7am / wake me up at 6:30am tomorrow
  remind me to call Mom at 5pm / in 30 minutes
  what alarms are set / what are my reminders
  cancel my 7am alarm / delete my reminder to call Mom
  Nothing sounds yet without hardware — these create real data and (once
  Discord is connected) ping the tasks channel when they're due.

BRIEFINGS
  morning / evening — full briefing
  health check — latest weekly system report (runs Sunday 4am on its own)

VOICE (Discord slash commands, not plain text)
  /speak <text> — one-shot: Sunny says it out loud in the channel
  /join — Sunny joins your voice channel for a live conversation; say
    "Hey Sunny" before every request (no listening window — each request
    needs its own wake word)
  /leave — ends the voice session

SERVER ADMIN (Discord only — needs a live server to act on)
  create/delete channel <name> — text channels
  create/delete role <name>
  give <@user> the <role> role / remove <@user> from the <role> role
  list channels / list roles
  Deletions run immediately, no confirmation — same as everything else here.

QUESTIONS
  Ask about tasks, weather, or your calendar and I'll answer with real
  data once each is connected (see "setup" below) — I'll say so plainly
  instead of making something up if one isn't. Anything else genuinely
  open-ended — a question, a request, plain conversation — goes to
  Claude for a real answer, not a canned "I don't know."

SETUP
  setup — what's connected, what still needs setup
  setup weather / calendar / email / discord
                                  — step-by-step to connect that one

Type "help" any time to see this again."""

_HELP_TRIGGERS = ("", "help", "/help", "commands", "info", "what can you do", "what can i ask")
_CANCEL_WORDS = ("cancel", "nevermind", "never mind", "stop", "skip", "forget it")
_BRIEFING_KEYWORDS = ("morning", "morning briefing", "evening", "evening briefing")
# Exact-phrase, not a regex -- this launches a multi-question wizard, so a
# false positive (an unrelated sentence that happens to contain "project")
# is worse than a false negative (a real phrasing that doesn't match).
_PROJECT_TRIGGERS = (
    "i would like to make a new project",
    "i'd like to make a new project",
    "i want to make a new project",
    "start a new project",
    "make a new project",
    "create a new project",
    "create a project",
    "new project",
)
_SKIP_SECTIONS_WORDS = ("no", "none", "nope", "you decide", "your choice", "up to you", "doesn't matter", "whatever you think")
_SETUP_BARE = ("setup", "/setup", "set up", "connect", "setup steps", "connect steps")
_SETUP_PREFIXES = (
    "setup ", "/setup ", "set up ", "connect ",
    "how do i connect ", "how do i set up ", "how to connect ", "how to set up ",
)


def _extract_setup_query(lowered: str) -> Optional[str]:
    """None if this isn't a setup-style command at all; "" for the bare
    overview; otherwise the source name/alias the user asked about."""
    if lowered in _SETUP_BARE:
        return ""
    for prefix in _SETUP_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix):].strip()
    return None

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


def _set_pending(session_id: str, awaiting: str, **extra) -> None:
    _pending[session_id] = {"awaiting": awaiting, "ts": time.time(), **extra}


def _looks_like_a_command(stripped: str, lowered: str) -> bool:
    """True if the text matches some other recognized command grammar (task,
    list, alarm/reminder, help, or a briefing keyword) — used so a pending
    follow-up question doesn't swallow an unrelated message as if it were
    the answer.

    A blank reply is deliberately never "a command" here, even though ""
    is itself one of _HELP_TRIGGERS for a top-level message — every pending
    handler already has its own "still need X" re-prompt for an empty
    answer, and that's clearly the right response to silence/whitespace
    sent while a question is outstanding, not the general help text."""
    if not stripped:
        return False
    if lowered in _HELP_TRIGGERS or lowered in _BRIEFING_KEYWORDS:
        return True
    task_cmd_type, _, _ = TaskCommandParser.parse_command(stripped)
    if task_cmd_type not in ("unknown", "add"):
        return True
    if ListCommandParser.parse(stripped) is not None:
        return True
    if ScheduledCommandParser.parse(stripped) is not None:
        return True
    return False


async def _create_task_from_reply(reply: str, tasks_engine: TaskEngine, session_id: str, source: str) -> str:
    """Treat a follow-up reply as a task title (optionally with --flags) and create it."""
    phrase, flags = TaskCommandParser._split_flags(reply)
    title = phrase.strip().strip('"\'')

    if not title:
        _set_pending(session_id, "task_title")
        return 'Still need a title for this one — what should I call it? (or say "cancel")'

    command = f"add {title} to my tasks" + (f" {flags}" if flags else "")
    _, message = await tasks_engine.execute_command(command, source=source)
    return message


async def _finish_task_with_category(
    reply: str, pending_data: Dict, tasks_engine: TaskEngine, session_id: str, source: str
) -> str:
    """Resolve a pending "which category?" follow-up and create the task.
    pending_data is everything parse_command already resolved (title,
    priority, due_date, description, ...) minus "tag" — there's no single
    command string left to re-parse here, unlike _create_task_from_reply,
    so this goes through TaskEngine.create_task_from_data() directly.

    Accepts the reply as-is even if it doesn't match a category in
    category_store — same permissive spirit as every other field here
    (categories are still free-form storage; the live list is just what
    gets offered/asked about)."""
    category = reply.strip().strip('"\'')
    if not category:
        _set_pending(session_id, "task_category", **pending_data)
        categories = category_store.get_categories()
        return f'Still need a category — {", ".join(categories)}? (or say "cancel")'

    matched = next((c for c in category_store.get_categories() if c.lower() == category.lower()), category)
    data = {**pending_data, "tag": matched}
    _, message = await tasks_engine.create_task_from_data(data, source=source)
    return message


async def _advance_project_wizard(
    stripped: str, lowered: str, pending: Dict, project_engine, session_id: str
) -> Optional[str]:
    """One step of the fixed "new project" wizard (name -> description ->
    optional sections -> scaffold). Returns the response text, or None if
    the reply didn't look like an answer at all (caller falls through to
    normal routing, same as the task_title/task_category pending states)."""
    awaiting = pending["awaiting"]

    if lowered in _CANCEL_WORDS:
        _pending.pop(session_id, None)
        return "No worries — cancelled."

    if _looks_like_a_command(stripped, lowered):
        _pending.pop(session_id, None)
        return None

    _pending.pop(session_id, None)

    if awaiting == "project_name":
        name = stripped.strip().strip('"\'')
        if not name:
            _set_pending(session_id, "project_name")
            return 'Still need a name for this one — what should I call it? (or say "cancel")'
        _set_pending(session_id, "project_description", name=name)
        return "One or two lines on what it's about?"

    if awaiting == "project_description":
        _set_pending(session_id, "project_sections", name=pending["name"], description=stripped.strip())
        return (
            'Any specific sections or files you want to start with, or should I decide based on that? '
            '(say "you decide" to skip)'
        )

    # awaiting == "project_sections" -- the wizard's last step
    sections = "" if lowered in _SKIP_SECTIONS_WORDS else stripped.strip()
    if project_engine is None:
        return "Project system isn't available right now."
    _, message = await project_engine.scaffold(pending["name"], pending["description"], sections)
    return message


async def handle_message(
    text: str,
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: Optional[ListEngine] = None,
    scheduled_engine: Optional[ScheduledEngine] = None,
    project_engine: Optional[ProjectEngine] = None,
    session_id: str = "default",
    on_chunk: Optional[OnChunk] = None,
) -> str:
    """Route one free-text message and return the response text.

    on_chunk is optional and additive — see briefing.py's
    custom_briefing() docstring for the streaming contract it enables.
    Every caller that doesn't pass it (every text interface) sees zero
    behavior change; only reaches anything when routing falls all the
    way through to the LLM Q&A fallback."""
    stripped = text.strip()
    lowered = stripped.lower().strip("? ")
    source = device_from_session(session_id)

    pending = _get_pending(session_id)
    if pending and pending.get("awaiting") == "task_title":
        if lowered in _CANCEL_WORDS:
            _pending.pop(session_id, None)
            return "No worries — cancelled."

        if not _looks_like_a_command(stripped, lowered):
            _pending.pop(session_id, None)
            return await _create_task_from_reply(stripped, tasks_engine, session_id, source)

        _pending.pop(session_id, None)
        # falls through to normal handling below

    elif pending and pending.get("awaiting") == "task_category":
        task_data = {k: v for k, v in pending.items() if k not in ("awaiting", "ts")}
        if lowered in _CANCEL_WORDS:
            _pending.pop(session_id, None)
            return "No worries — cancelled."

        if not _looks_like_a_command(stripped, lowered):
            _pending.pop(session_id, None)
            return await _finish_task_with_category(stripped, task_data, tasks_engine, session_id, source)

        _pending.pop(session_id, None)
        # falls through to normal handling below

    elif pending and pending.get("awaiting") in ("project_name", "project_description", "project_sections"):
        wizard_reply = await _advance_project_wizard(stripped, lowered, pending, project_engine, session_id)
        if wizard_reply is not None:
            return wizard_reply
        # falls through to normal handling below

    if lowered in _HELP_TRIGGERS:
        return HELP_TEXT

    if lowered in _PROJECT_TRIGGERS:
        if project_engine is None:
            return "Project system isn't available right now."
        _set_pending(session_id, "project_name")
        return "What's the project called?"

    setup_query = _extract_setup_query(lowered)
    if setup_query is not None:
        return setup_guides.respond(setup_query)

    if list_engine is not None:
        handled, _, message = list_engine.try_execute(stripped, source=source)
        if handled:
            return message

    if scheduled_engine is not None:
        handled, _, message = await scheduled_engine.try_execute(stripped, source=source)
        if handled:
            return message

    cmd_type, success, task_data = TaskCommandParser.parse_command(stripped, category_store.get_categories())

    if cmd_type == "add" and not success:
        # The only real failure mode for a natural "add" is a missing title
        # (e.g. bare "make a task") — ask for it instead of just erroring out.
        _set_pending(session_id, "task_title")
        return 'Sure — what should I call it? (or say "cancel")'

    if cmd_type == "add" and success and "tag" not in task_data:
        # Title (and any --flags) resolved, but no category was stated or
        # recognized inline — ask instead of silently defaulting to General.
        _set_pending(session_id, "task_category", **task_data)
        categories = category_store.get_categories()
        return f'Got it — which category: {", ".join(categories)}? (or say "cancel")'

    if cmd_type != "unknown":
        _, message = await tasks_engine.execute_command(
            stripped, source=source, known_categories=category_store.get_categories()
        )
        return message

    if lowered in ("morning", "morning briefing"):
        return await briefing_engine.generate_morning_briefing()

    if lowered in ("evening", "evening briefing"):
        return await briefing_engine.generate_evening_briefing()

    if lowered in ("health check", "health report"):
        report = health_check.latest_report()
        return report if report else "No health check report yet — the first one runs Sunday at 4am."

    return await briefing_engine.answer_question(stripped, on_chunk=on_chunk)


def is_briefing_trigger(text: str) -> bool:
    """Whether `text` would make handle_message() generate a full morning/evening
    briefing — used by discord_bot.py to decide whether to also cross-post the
    result to a #briefings channel, without duplicating the trigger phrases."""
    return text.strip().lower().strip("? ") in _BRIEFING_KEYWORDS
