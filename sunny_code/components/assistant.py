"""Shared message-routing logic: one entry point used by both the web chatbot
and the Discord bot, so behavior stays identical across interfaces.

Routing order: pending follow-up (if any) -> help trigger -> list command ->
alarm/reminder command -> calendar-event command -> Spotify command ->
task command (natural phrasing or legacy !task) -> morning/evening briefing
-> briefing Q&A fallback.

Lists, alarms/reminders, and calendar-event commands are checked *before*
tasks on purpose: their trigger phrases require a specific keyword
("list"/"alarm"/"reminder"/"calendar"/"event"), while tasks' bare
"delete X"/"mark X as done" patterns are deliberately broad and would
otherwise swallow "delete my reminder to X", "remove milk from my list", or
"cancel my dentist appointment from my calendar" before the more specific
parser ever saw it.
"""

import random
import time
from typing import Dict, Optional

from sunny_code.components import category_store, health_check, setup_guides
from sunny_code.components.briefing import BriefingEngine, OnChunk, OnSearchStart
from sunny_code.components.calendar_engine import CalendarEngine
from sunny_code.components.device import device_from_session
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.lists_parser import ListCommandParser
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.scheduled_parser import ScheduledCommandParser
from sunny_code.components.spotify_engine import SpotifyEngine
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

SPOTIFY (needs setup — see "setup spotify")
  play <song/artist> — search and start playback
  pause / resume — pause the music / resume the music
  skip / previous song
  volume up / volume down / set volume to 50
  what's playing
  Acts on whatever device Spotify itself considers active — same as the
  Spotify app or Siri, no device selection built in.

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
  run health check — run one right now instead of waiting for Sunday
    (short spoken summary over voice, full report everywhere else)

VOICE (Discord slash commands, not plain text)
  /speak <text> — one-shot: Sunny says it out loud in the channel
  /join — Sunny joins your voice channel for a live conversation; say
    "Hey Sunny" before every request (no listening window — each request
    needs its own wake word)
  /leave — ends the voice session

DISCORD-ONLY COMMANDS
  /category add|remove <name> — manage the task category list
  /usage [days] — chart of Claude API cost over the last N days (default 30)

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
  Claude for a real answer, not a canned "I don't know." Claude can also
  search the web for things that genuinely need current information —
  it decides for itself when that's actually needed, not by default.

SETUP
  setup — what's connected, what still needs setup
  setup weather / calendar / email / discord
                                  — step-by-step to connect that one

Type "help" any time to see this again."""

_HELP_TRIGGERS = ("", "help", "/help", "commands", "info", "what can you do", "what can i ask")
_CANCEL_WORDS = ("cancel", "nevermind", "never mind", "stop", "skip", "forget it")
_MORNING_TRIGGERS = (
    "morning", "morning briefing", "good morning", "good morning sunny",
    "hey sunny good morning", "im up", "i'm up", "im up sunny", "i'm up sunny",
    "hey sunny im up", "hey sunny i'm up",
)
_EVENING_TRIGGERS = (
    "evening", "evening briefing", "good night", "goodnight",
    "good night sunny", "goodnight sunny", "hey sunny good night",
    "hey sunny goodnight", "im going to bed", "i'm going to bed",
    "going to bed", "hey sunny im going to bed", "hey sunny i'm going to bed",
)
_BRIEFING_KEYWORDS = _MORNING_TRIGGERS + _EVENING_TRIGGERS
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
_YES_WORDS = ("yes", "y", "yeah", "yep", "yup", "sure", "do it", "go ahead", "build it", "sounds good")
_NO_WORDS = ("no", "n", "nope", "nah", "no thanks", "don't")
# A little phrasing variety per step so the wizard doesn't read as a rigid
# form -- picked at random each time, not per-session-sticky (a personal,
# single-user tool doesn't need to remember which variant it used last).
_PROJECT_NAME_PROMPTS = (
    "What's the project called?",
    "What should I call this one?",
    "Alright — what's the name?",
)
_PROJECT_DESCRIPTION_PROMPTS = (
    "One or two lines on what it's about?",
    "Give me a quick rundown — what's this project for?",
    "What's the idea here, in a sentence or two?",
)
_PROJECT_SECTIONS_PROMPTS = (
    'Any specific sections or files you want to start with, or should I decide based on that? (say "you decide" to skip)',
    'Want to call out particular sections, or should I figure that out myself? (say "you decide" to skip)',
    'Anything specific you want covered, or am I picking the structure? (say "you decide" to skip)',
)
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


async def _run_health_check_now(session_id: str) -> str:
    """Triggers a real, immediate health check — same work the automatic
    Sunday 4am one does (gather the week's summary, ask Claude to write
    it up, log it to the vault, flip the acknowledgment marker) — and
    returns a reply sized for the calling interface: a short, no-LLM
    spoken summary (health_check.short_summary()) for voice sessions
    (Discord /join or the Pi companion, both session_id-prefixed
    accordingly), the full written report everywhere else. The check
    itself is identical either way; only what gets said back differs."""
    report = await health_check.run_weekly_health_check()
    if session_id.startswith("voice:") or session_id.startswith("pi:"):
        return health_check.short_summary()
    return report


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
    optional sections -> confirm -> scaffold). Returns the response text,
    or None if the reply didn't look like an answer at all (caller falls
    through to normal routing, same as the task_title/task_category
    pending states). A firm "no" at the confirm step ends the whole thing
    without ever calling the LLM -- only "yes" hands off to project_engine."""
    awaiting = pending["awaiting"]

    if lowered in _CANCEL_WORDS:
        _pending.pop(session_id, None)
        return "No worries — cancelled."

    if awaiting != "project_confirm" and _looks_like_a_command(stripped, lowered):
        _pending.pop(session_id, None)
        return None

    _pending.pop(session_id, None)

    if awaiting == "project_name":
        name = stripped.strip().strip('"\'')
        if not name:
            _set_pending(session_id, "project_name")
            return 'Still need a name for this one — what should I call it? (or say "cancel")'
        _set_pending(session_id, "project_description", name=name)
        return random.choice(_PROJECT_DESCRIPTION_PROMPTS)

    if awaiting == "project_description":
        _set_pending(session_id, "project_sections", name=pending["name"], description=stripped.strip())
        return random.choice(_PROJECT_SECTIONS_PROMPTS)

    if awaiting == "project_sections":
        sections = "" if lowered in _SKIP_SECTIONS_WORDS else stripped.strip()
        _set_pending(
            session_id, "project_confirm", name=pending["name"], description=pending["description"], sections=sections
        )
        sections_line = f' covering {sections}' if sections else ''
        return (
            f'So: "{pending["name"]}"{sections_line} — want me to build it? (yes/no)'
        )

    # awaiting == "project_confirm" -- the wizard's last step. Not gated by
    # _looks_like_a_command above (a bare "yes"/"no" would otherwise get
    # misread as looking like some other command and silently drop the
    # wizard) -- an unrecognized reply here just re-asks instead of either
    # building or cancelling on a guess.
    if lowered in _NO_WORDS:
        return "No worries — didn't build it."
    if lowered not in _YES_WORDS:
        _set_pending(
            session_id, "project_confirm",
            name=pending["name"], description=pending["description"], sections=pending["sections"],
        )
        return 'Just need a yes or no — want me to build it?'

    if project_engine is None:
        return "Project system isn't available right now."
    _, message = await project_engine.scaffold(pending["name"], pending["description"], pending["sections"])
    return message


async def handle_message(
    text: str,
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: Optional[ListEngine] = None,
    scheduled_engine: Optional[ScheduledEngine] = None,
    project_engine: Optional[ProjectEngine] = None,
    spotify_engine: Optional[SpotifyEngine] = None,
    calendar_engine: Optional[CalendarEngine] = None,
    session_id: str = "default",
    on_chunk: Optional[OnChunk] = None,
    on_search_start: Optional[OnSearchStart] = None,
) -> str:
    """Route one free-text message and return the response text.

    on_chunk is optional and additive — see briefing.py's
    custom_briefing() docstring for the streaming contract it enables.
    on_search_start is the same idea for a live web-search cue -- only
    meaningful alongside on_chunk. Every caller that doesn't pass them
    (every text interface) sees zero
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

    elif pending and pending.get("awaiting") in (
        "project_name", "project_description", "project_sections", "project_confirm"
    ):
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
        return random.choice(_PROJECT_NAME_PROMPTS)

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

    if calendar_engine is not None:
        handled, _, message = await calendar_engine.try_execute(stripped, source=source)
        if handled:
            return message

    if spotify_engine is not None:
        handled, _, message = await spotify_engine.try_execute(stripped, source=source)
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

    if lowered in _MORNING_TRIGGERS:
        return await briefing_engine.generate_morning_briefing()

    if lowered in _EVENING_TRIGGERS:
        return await briefing_engine.generate_evening_briefing()

    # Substring, not an exact-phrase tuple -- "can you run a system health
    # check" (a real phrasing that failed live, 2026-08-23) doesn't match
    # a fixed tuple entry, and unlike "health" alone, "health check"/
    # "system health" isn't generic enough to collide with the unrelated
    # personal-wellness "health"/"sleep"/"mood" keyword check further down
    # this routing chain (see briefing.py's custom_briefing) -- catching
    # it here, before that fallback is ever reached, is what fixes it.
    # The exact bare phrase means "show me the last one"; anything else
    # that mentions it ("run a health check", "check system health",
    # "can you run a system health check") reads as wanting a fresh one --
    # simpler and more robust than trying to enumerate every verb someone
    # might use ("check" itself is ambiguous, since it's also half of the
    # bare phrase this branch has to leave alone).
    if lowered in ("health check", "health report"):
        report = health_check.latest_report()
        return report if report else "No health check report yet — the first one runs Sunday at 4am."
    if "health check" in lowered or "system health" in lowered:
        return await _run_health_check_now(session_id)

    return await briefing_engine.answer_question(stripped, on_chunk=on_chunk, on_search_start=on_search_start)


def is_briefing_trigger(text: str) -> bool:
    """Whether `text` would make handle_message() generate a full morning/evening
    briefing — used by discord_bot.py to decide whether to also cross-post the
    result to a #briefings channel, without duplicating the trigger phrases."""
    return text.strip().lower().strip("? ") in _BRIEFING_KEYWORDS
