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

import asyncio
import random
import time
from datetime import datetime
from typing import Dict, Optional

from sunny_code.components import (
    build_info, category_store, class_setup_engine, exam_prep, health_check, service_registry, setup_guides,
    token_tracker,
)
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
  what's my usage — today's/this month's Claude spend, plus Anthropic's
    real remaining-tokens-this-window number if a call has been made
    since the last restart
  what version are you running — the commit currently deployed
  my classes — classes found under sunny-vault/KSU/<semester>/<class>/
  when is my <class> exam — looks for a matching event on your calendar
  study review for <class> — Claude writes a focused review from your
    actual notes on whatever hasn't been marked mastered yet
  set up my classes — paste a syllabus per class; creates recurring
    calendar events for meeting times, all-day events for due dates/exams,
    saves the syllabus + a summary into that class's own vault folder, and
    pings #reminders 2 days before and the day of each

VOICE
  /speak <text> — one-shot: Sunny says it out loud in the channel (slash command)
  Sunny stays connected to a configured voice channel for live conversation
    (no join command) — say "Hey Sunny" before every request (no listening
    window — each request needs its own wake word). Toggle with /service
    voice_join enable|disable.

DISCORD-ONLY COMMANDS
  add category <name> / remove category <name> — manage the task category
    list (also /category add|remove <name> in Discord)
  my categories — list them
  /usage [days] — chart of Claude API cost over the last N days (default 30)
  /version — the commit currently deployed
  /services — on/off + autostart status for every background service
  /service <name> enable|disable|autostart_on|autostart_off
  /vacation on|off — same as saying "vacation mode on"/"off" below

ANY INTERFACE
  vacation mode on/off — pauses morning-prep pre-warming and the
    proactive morning/evening nudge cycle until turned back off

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
_VACATION_ON_TRIGGERS = ("vacation mode on", "vacation mode", "turn on vacation mode", "start vacation mode")
_VACATION_OFF_TRIGGERS = ("vacation mode off", "turn off vacation mode", "stop vacation mode", "end vacation mode")
_USAGE_QUERY_TRIGGERS = (
    "what's my usage", "whats my usage", "what is my usage", "how much have i spent",
    "how much have i spent on claude", "my usage", "usage", "claude usage",
)
_VERSION_QUERY_TRIGGERS = (
    "version", "what version are you running", "what version is this",
    "what's your version", "whats your version", "what build are you running",
    "what build is this", "build version", "what version are you on",
)
_CATEGORY_ADD_PREFIXES = ("add category ", "create category ", "new category ")
_CATEGORY_REMOVE_PREFIXES = ("remove category ", "delete category ")
_CATEGORY_LIST_TRIGGERS = ("my categories", "what categories are there", "list categories", "show categories")


def _extract_category_add(stripped: str, lowered: str) -> Optional[str]:
    """The category name out of "add/create/new category <name>" -- taken
    from `stripped`, not `lowered`, so the name keeps whatever
    capitalization was typed (category_store shows it back verbatim, e.g.
    "General"/"School", not lowercased)."""
    for prefix in _CATEGORY_ADD_PREFIXES:
        if lowered.startswith(prefix):
            name = stripped[len(prefix):].strip().strip('"\'')
            return name or None
    return None


def _extract_category_remove(stripped: str, lowered: str) -> Optional[str]:
    for prefix in _CATEGORY_REMOVE_PREFIXES:
        if lowered.startswith(prefix):
            name = stripped[len(prefix):].strip().strip('"\'')
            return name or None
    return None


_MY_CLASSES_TRIGGERS = ("my classes", "what classes am i tracking", "list my classes", "show my classes")
_EXAM_DATE_PREFIXES = (
    "when is my ", "when's my ", "whens my ", "when is the ", "when's the ", "whens the ",
)
_EXAM_DATE_SUFFIX = " exam"
_STUDY_REVIEW_PREFIXES = ("study review for ", "exam review for ")
_REVIEW_NOTES_PREFIXES = ("review my ", "review the ", "review ")
_REVIEW_NOTES_SUFFIX = " notes"


def _extract_exam_date_query(lowered: str) -> Optional[str]:
    """The class name out of "when is my <class> exam", or None if this
    isn't that phrasing at all."""
    if not lowered.endswith(_EXAM_DATE_SUFFIX):
        return None
    for prefix in _EXAM_DATE_PREFIXES:
        if lowered.startswith(prefix):
            class_name = lowered[len(prefix):-len(_EXAM_DATE_SUFFIX)].strip()
            return class_name or None
    return None


def _extract_study_review_query(lowered: str) -> Optional[str]:
    """The class name out of "study review for <class>"/"exam review for
    <class>"/"review my <class> notes", or None. Deliberately doesn't
    accept a bare "review <anything>" -- too generic a word to risk
    colliding with something else said in passing; every accepted form
    here has both a specific lead-in and (for the "review ... notes" form)
    a specific trailing anchor."""
    for prefix in _STUDY_REVIEW_PREFIXES:
        if lowered.startswith(prefix):
            class_name = lowered[len(prefix):].strip()
            return class_name or None
    if lowered.endswith(_REVIEW_NOTES_SUFFIX):
        for prefix in _REVIEW_NOTES_PREFIXES:
            if lowered.startswith(prefix):
                class_name = lowered[len(prefix):-len(_REVIEW_NOTES_SUFFIX)].strip()
                return class_name or None
    return None
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
# Exact-phrase, same reasoning as _PROJECT_TRIGGERS -- this launches a much
# longer wizard (a per-class syllabus loop with real calendar writes), so a
# false positive is far worse than a false negative.
_CLASS_SETUP_TRIGGERS = (
    "set up my classes",
    "set up classes",
    "class setup",
    "setup my classes",
    "setup classes",
    "i want to set up my classes",
    "i want to set up classes",
    "can we set up my classes",
    "can we set up classes",
    "can you set up my classes",
    "can you set up classes",
    "let's set up my classes",
    "lets set up my classes",
    "let's set up classes",
    "lets set up classes",
)
_CLASS_SETUP_SEMESTER_PROMPTS = (
    "What semester is this? (e.g. \"Fall 2026\")",
    "Which semester are we setting up?",
)
_CLASS_SETUP_SYLLABUS_PROMPTS = (
    'Paste the syllabus for a class (or say "done" if that\'s all of them).',
    'Next syllabus — paste it in, or say "done" if you\'ve added them all.',
)
_CLASS_SETUP_DONE_WORDS = ("done", "that's all", "thats all", "no more", "finished", "that's it", "thats it")

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
    if lowered in _VACATION_ON_TRIGGERS or lowered in _VACATION_OFF_TRIGGERS:
        return True
    if lowered in _USAGE_QUERY_TRIGGERS:
        return True
    if lowered in _VERSION_QUERY_TRIGGERS:
        return True
    if (lowered in _MY_CLASSES_TRIGGERS or _extract_exam_date_query(lowered) is not None
            or _extract_study_review_query(lowered) is not None):
        return True
    if (lowered in _CATEGORY_LIST_TRIGGERS or _extract_category_add(stripped, lowered) is not None
            or _extract_category_remove(stripped, lowered) is not None):
        return True
    task_cmd_type, _, _ = TaskCommandParser.parse_command(stripped)
    if task_cmd_type not in ("unknown", "add"):
        return True
    if ListCommandParser.parse(stripped) is not None:
        return True
    if ScheduledCommandParser.parse(stripped) is not None:
        return True
    return False


def _describe_usage() -> str:
    """Plain-text, TTS-safe answer to "what's my usage" -- same numbers the
    /console dashboard and Discord's /usage chart show, just as one spoken-
    friendly line instead of an image (which no voice interface, including
    the Pi companion, can render). Answers the open "wire a what's-my-usage
    intent" item from sunny-companion/BUILD_PLAN.md's Phase 6 -- this is
    that intent, and it works from every interface since it's routed here,
    not Discord-command-only like /usage's chart."""
    today = token_tracker.get_today_usage()
    month_cost = token_tracker.get_month_cost()
    parts = [f"${today['cost']:.2f} spent today, ${month_cost:.2f} this month"]

    limits = token_tracker.get_latest_rate_limits()
    tok_remaining = limits.get("anthropic-ratelimit-tokens-remaining")
    tok_limit = limits.get("anthropic-ratelimit-tokens-limit")
    if tok_remaining and tok_limit:
        parts.append(f"{tok_remaining} of {tok_limit} tokens left in the current rate window")

    return ". ".join(parts) + "."


def _describe_version() -> str:
    """Plain-text answer to "what version are you running" -- works over
    voice too (the hash just gets spelled out, same as any other spoken
    identifier), not Discord-command-only like /version."""
    return f"Running build {build_info.get_build_version()}."


def _describe_classes() -> str:
    classes = exam_prep.list_classes()
    if not classes:
        return (
            "No classes found yet — add notes under sunny-vault/KSU/<semester>/<class name>/"
            "<topic>.md and I'll pick them up next time you ask."
        )
    lines = [f"{c['semester']}/{c['class']} — {len(c['notes'])} note(s)" for c in classes]
    return "Classes:\n" + "\n".join(lines)


def _format_exam_time(event: Dict) -> str:
    start = event.get("start", {})
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"])
        return dt.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
    if "date" in start:
        dt = datetime.fromisoformat(start["date"])
        return dt.strftime("%A, %B %d") + " (all day)"
    return "an unknown time"


async def _describe_exam_date(class_name: str) -> str:
    class_info = exam_prep.find_class(class_name)
    if class_info is None:
        return f'No class matching "{class_name}" found under sunny-vault/KSU/.'
    event = await asyncio.to_thread(exam_prep.find_exam_date, class_info["class"])
    if event is None:
        return (
            f'No upcoming exam found on the calendar for {class_info["class"]} in the next 60 days '
            "(or Calendar isn't connected — see \"setup calendar\")."
        )
    return f'{event.get("summary", "Exam")} — {_format_exam_time(event)}'


async def _run_study_review(class_name: str) -> str:
    class_info = exam_prep.find_class(class_name)
    if class_info is None:
        return f'No class matching "{class_name}" found under sunny-vault/KSU/.'
    if not exam_prep.topics_needing_review(class_info["class"]):
        return f'Nothing to review for {class_info["class"]} — no notes found, or everything\'s already mastered.'
    review = await exam_prep.generate_study_review(class_info["class"])
    if review is None:
        return "Couldn't reach Claude to write the review — try again in a moment."
    return review


async def _run_health_check_now(session_id: str) -> str:
    """Triggers a real, immediate health check — same work the automatic
    Sunday 4am one does (gather the week's summary, ask Claude to write
    it up, log it to the vault, flip the acknowledgment marker) — and
    returns a reply sized for the calling interface: a short, no-LLM
    spoken summary (health_check.short_summary()) for voice sessions
    (Sunny's persistent Discord voice presence or the Pi companion, both
    session_id-prefixed accordingly), the full written report everywhere
    else. The check
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
    due_date, description, ...) minus "tag" — there's no single
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


async def _advance_class_setup_wizard(stripped: str, lowered: str, pending: Dict, session_id: str) -> Optional[str]:
    """One step of the class-setup wizard: semester name -> per-class loop
    (paste syllabus -> confirm/correct the extracted class name -> next
    syllabus or done). Same "return None means fall through to normal
    routing" contract as _advance_project_wizard.

    No separate "what are the start/end dates" question -- semester_name
    (e.g. "Fall 2026") is only a year/season hint for the parser; the
    semester's actual start/end dates are pulled straight from each
    syllabus by syllabus_parser.py, same as class_name already was.

    class_setup_syllabus and class_setup_confirm are both excluded from
    the _looks_like_a_command gate below — a pasted syllabus is long,
    free-form text that could easily contain a phrase matching some
    other command's pattern by coincidence (e.g. a policy sentence
    starting with "add"), and the confirm step accepts a bare class-name
    correction with the same risk. Both need to be taken literally as
    wizard input, not risk being misread as an unrelated command."""
    awaiting = pending["awaiting"]

    if lowered in _CANCEL_WORDS:
        _pending.pop(session_id, None)
        return "No worries — cancelled."

    if awaiting not in ("class_setup_syllabus", "class_setup_confirm") and _looks_like_a_command(stripped, lowered):
        _pending.pop(session_id, None)
        return None

    _pending.pop(session_id, None)

    if awaiting == "class_setup_semester_name":
        name = stripped.strip().strip('"\'')
        if not name:
            _set_pending(session_id, "class_setup_semester_name")
            return 'Still need a semester name — what is it? (or say "cancel")'
        _set_pending(session_id, "class_setup_syllabus", semester_name=name, count=0)
        return random.choice(_CLASS_SETUP_SYLLABUS_PROMPTS)

    if awaiting == "class_setup_syllabus":
        if lowered in _CLASS_SETUP_DONE_WORDS:
            count = pending["count"]
            return f"Class setup done — {count} class{'es' if count != 1 else ''} set up." if count else "Class setup done — nothing was added."
        if not stripped.strip():
            _set_pending(session_id, "class_setup_syllabus", semester_name=pending["semester_name"], count=pending["count"])
            return 'Still need a syllabus to paste — go ahead. (or say "done")'
        ok, message, parsed = await class_setup_engine.preview(pending["semester_name"], stripped)
        if not ok:
            _set_pending(session_id, "class_setup_syllabus", semester_name=pending["semester_name"], count=pending["count"])
            return message
        _set_pending(
            session_id, "class_setup_confirm",
            semester_name=pending["semester_name"], count=pending["count"], parsed=parsed, syllabus_text=stripped,
        )
        return message

    # awaiting == "class_setup_confirm"
    if lowered in _NO_WORDS:
        _set_pending(session_id, "class_setup_syllabus", semester_name=pending["semester_name"], count=pending["count"])
        skipped_name = pending["parsed"].get("class_name") or "that one"
        return f'Skipped "{skipped_name}". ' + random.choice(_CLASS_SETUP_SYLLABUS_PROMPTS)

    if lowered not in _YES_WORDS:
        # Not yes/no -- treat the reply as a class-name correction (or the
        # first real answer, if the parse came back with no name at all)
        # and re-show the recap for another confirm round.
        parsed = pending["parsed"]
        parsed["class_name"] = stripped.strip().strip('"\'')
        _set_pending(
            session_id, "class_setup_confirm",
            semester_name=pending["semester_name"], count=pending["count"], parsed=parsed,
            syllabus_text=pending["syllabus_text"],
        )
        return class_setup_engine.recap(parsed)

    parsed = pending["parsed"]
    if not parsed.get("class_name", "").strip():
        _set_pending(
            session_id, "class_setup_confirm",
            semester_name=pending["semester_name"], count=pending["count"], parsed=parsed,
            syllabus_text=pending["syllabus_text"],
        )
        return "Still need a class name before I can set this up — what is it?"

    result_message = await asyncio.to_thread(
        class_setup_engine.commit, pending["semester_name"], parsed, pending["syllabus_text"],
    )
    _set_pending(session_id, "class_setup_syllabus", semester_name=pending["semester_name"], count=pending["count"] + 1)
    return f"{result_message} " + random.choice(_CLASS_SETUP_SYLLABUS_PROMPTS)


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

    elif pending and pending.get("awaiting") in (
        "class_setup_semester_name", "class_setup_syllabus", "class_setup_confirm",
    ):
        wizard_reply = await _advance_class_setup_wizard(stripped, lowered, pending, session_id)
        if wizard_reply is not None:
            return wizard_reply
        # falls through to normal handling below

    if lowered in _HELP_TRIGGERS:
        return HELP_TEXT

    if lowered in _VACATION_ON_TRIGGERS:
        _, message = service_registry.set_vacation_mode(True)
        return message

    if lowered in _VACATION_OFF_TRIGGERS:
        _, message = service_registry.set_vacation_mode(False)
        return message

    if lowered in _PROJECT_TRIGGERS:
        if project_engine is None:
            return "Project system isn't available right now."
        _set_pending(session_id, "project_name")
        return random.choice(_PROJECT_NAME_PROMPTS)

    if lowered in _CLASS_SETUP_TRIGGERS:
        _set_pending(session_id, "class_setup_semester_name")
        return random.choice(_CLASS_SETUP_SEMESTER_PROMPTS)

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

    if lowered in _CATEGORY_LIST_TRIGGERS:
        return "Categories: " + ", ".join(category_store.get_categories())

    category_to_add = _extract_category_add(stripped, lowered)
    if category_to_add is not None:
        _, message = category_store.add_category(category_to_add)
        return message

    category_to_remove = _extract_category_remove(stripped, lowered)
    if category_to_remove is not None:
        _, message = category_store.remove_category(category_to_remove)
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
    if lowered in _MY_CLASSES_TRIGGERS:
        return _describe_classes()

    exam_date_query = _extract_exam_date_query(lowered)
    if exam_date_query is not None:
        return await _describe_exam_date(exam_date_query)

    study_review_query = _extract_study_review_query(lowered)
    if study_review_query is not None:
        return await _run_study_review(study_review_query)

    if lowered in _USAGE_QUERY_TRIGGERS:
        return _describe_usage()

    if lowered in _VERSION_QUERY_TRIGGERS:
        return _describe_version()

    if lowered in ("health check", "health report"):
        report = health_check.latest_report()
        return report if report else "No health check report yet — the first one runs Sunday at 4am."
    if "health check" in lowered or "system health" in lowered:
        return await _run_health_check_now(session_id)

    return await briefing_engine.answer_question(
        stripped, session_id=session_id, on_chunk=on_chunk, on_search_start=on_search_start
    )


def is_briefing_trigger(text: str) -> bool:
    """Whether `text` would make handle_message() generate a full morning/evening
    briefing — used by discord_bot.py to decide whether to also cross-post the
    result to a #briefings channel, without duplicating the trigger phrases."""
    return text.strip().lower().strip("? ") in _BRIEFING_KEYWORDS
