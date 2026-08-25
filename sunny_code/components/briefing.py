"""Briefing engine with hardcoded templates, real task data, and honest Q&A support.

Tasks are real (queried straight from tasks.db). Weather, calendar, and email
are real once their respective setup is done (OPENWEATHERMAP_API_KEY +
WEATHER_LOCATION for weather; Google Sign-In for calendar/email). Commute,
health, news, and motorsports have no live API wired up yet. Sections/
questions about anything not yet real say so explicitly instead of
pretending mock data is real — and every time that happens, it gets logged
to sunny-vault/log/requests.md.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from sunny_code.config import get_settings
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.data_sources import is_configured, missing_requirement
from sunny_code.components.llm_client import ask_claude, ask_claude_stream
from sunny_code.components.request_log import log_unfulfilled
from sunny_code.components import conversation_memory, docs_search, google_calendar, google_gmail, health_check, weather

OnChunk = Callable[[str], Awaitable[None]]
OnSearchStart = Callable[[], Awaitable[None]]


logger = logging.getLogger(__name__)

_TOPIC_LABELS = {
    "weather": "WEATHER FORECAST",
    "calendar": "YOUR SCHEDULE",
    "email": "EMAIL SUMMARY",
    "commute": "COMMUTE INFORMATION",
    "health": "WELLNESS STATUS",
    "motorsports": "MOTORSPORTS UPDATE",
    "news": "TODAY'S HEADLINES",
}


class BriefingTemplates:
    """Hardcoded briefing templates. Real data where it exists, honest gaps where it doesn't."""

    @staticmethod
    def format_time_list(events: List[Dict], key: str = "time") -> str:
        """Format a list of timed events."""
        if not events:
            return "No scheduled events"
        lines = []
        for event in events:
            time = event.get(key, "")
            title = event.get("title", "")
            duration = event.get("duration", "")
            location = event.get("location", "")
            priority = event.get("priority", "")

            line = f"{time} — {title}"
            if duration:
                line += f" ({duration})"
            if location:
                line += f", {location}"
            if priority and priority != "low":
                line += f" [{priority.upper()}]"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _note(source: str) -> Optional[str]:
        """'Not connected' note for a source, or None if it's real."""
        if is_configured(source):
            return None
        return f"Not connected — {missing_requirement(source)}"

    @staticmethod
    async def _calendar_text(day_offset: int = 0, unconfigured: Optional[List[str]] = None) -> str:
        """Real events via Google Calendar if connected, else the standard
        'not connected' note. The actual API call is a real network
        request through Google's (sync-only) client library — run off
        the event loop via to_thread so it never blocks anything else
        the app is doing (Discord, the web console, the voice conversation
        pipeline) for however long that call takes."""
        if not is_configured("calendar"):
            if unconfigured is not None:
                unconfigured.append("calendar")
            return BriefingTemplates._note("calendar")
        events = await asyncio.to_thread(google_calendar.get_events, day_offset)
        if events is None:
            return "Google Calendar temporarily unavailable — check logs"
        if not events:
            return "No events scheduled"
        return BriefingTemplates.format_time_list(events)

    @staticmethod
    async def _email_text(unconfigured: Optional[List[str]] = None) -> str:
        """Real unread/urgent summary via Gmail if connected, else the
        standard 'not connected' note. See _calendar_text's docstring for
        why this runs via to_thread."""
        if not is_configured("email"):
            if unconfigured is not None:
                unconfigured.append("email")
            return BriefingTemplates._note("email")
        summary = await asyncio.to_thread(google_gmail.get_summary)
        if summary is None:
            return "Gmail temporarily unavailable — check logs"
        lines = [f"{summary['unread_count']} unread ({summary['urgent_count']} marked important)"]
        for s in summary["top_subjects"][:3]:
            lines.append(f" • {s['subject'] or '(no subject)'} — {s['from']}")
        return "\n ".join(lines)

    @staticmethod
    async def _weather_text(tomorrow: bool = False, unconfigured: Optional[List[str]] = None) -> str:
        """Real conditions via OpenWeatherMap if connected, else the
        standard 'not connected' note. See _calendar_text's docstring for
        why this runs via to_thread (weather.py uses the sync `requests`
        library, same blocking-call concern)."""
        if not is_configured("weather"):
            if unconfigured is not None:
                unconfigured.append("weather")
            return BriefingTemplates._note("weather")
        data = await asyncio.to_thread(weather.get_tomorrow if tomorrow else weather.get_current)
        if data is None:
            return "Weather temporarily unavailable — check logs"
        line = f"{data['temp']}°F, {data['condition']}"
        if data.get("rain_chance") is not None:
            line += f", {data['rain_chance']}% chance of rain"
        return line

    @staticmethod
    async def morning_briefing(tasks_db: TaskDB) -> str:
        """Morning briefing: real tasks, honest gaps everywhere else."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")

        unconfigured = []

        def note(source: str) -> str:
            n = BriefingTemplates._note(source)
            if n:
                unconfigured.append(source)
                return n
            return ""

        # Weather/calendar/email are three independent network calls --
        # fetch them concurrently instead of one after another, so the
        # briefing's total latency is roughly the slowest single call,
        # not the sum of all three. Safe to share `unconfigured` across
        # them: each one's own append happens synchronously before its
        # first await, never interleaved with another's.
        weather_note, calendar_note, email_note = await asyncio.gather(
            BriefingTemplates._weather_text(False, unconfigured),
            BriefingTemplates._calendar_text(0, unconfigured),
            BriefingTemplates._email_text(unconfigured),
        )
        commute_note = note("commute")
        health_note = note("health")
        news_note = note("news")

        open_tasks = tasks_db.get_open_tasks()
        in_progress = tasks_db.get_in_progress_tasks()
        task_count = len(open_tasks) + len(in_progress)
        top = (in_progress + open_tasks)[0] if (in_progress or open_tasks) else None
        task_str = f"{len(in_progress)} in progress, {len(open_tasks)} open — {task_count} total"

        # Nudge only, never the report content itself — see health_check.py's
        # BACKLOG-sourced requirement to tell the user to check it, not what
        # it is. Persists across days until acknowledged (morning briefings
        # are manual-trigger-only, so a same-day-only check could silently
        # lose the reminder if "morning" isn't said on the Sunday it ran).
        health_notice = health_check.pending_notice()
        health_line = f"\n{health_notice}\n" if health_notice else ""

        briefing = f"""
=== PROJECT SUNNY — MORNING BRIEFING ===

Good morning, Keaton! Here's your day at a glance.

TODAY: {date_str}

WEATHER
   {weather_note}

COMMUTE
   {commute_note}

TODAY'S SCHEDULE
   {calendar_note}

EMAIL
   {email_note}

TASKS ({task_count} total)
   {task_str}
   Next up: {top['title'] if top else 'None'}

WELLNESS
   {health_note}

HEADLINES
   {news_note}

YOUR DAY AHEAD
   1. Focus on: {top['title'] if top else 'nothing on your task list right now'}
   2. {len(unconfigured)} section(s) above need a real data source connected — logged to sunny-vault/log/requests.md
{health_line}
Have a productive day!
"""
        if unconfigured:
            log_unfulfilled(
                "morning_briefing",
                f"sections without a real data source: {', '.join(unconfigured)}",
            )

        return briefing

    @staticmethod
    async def evening_briefing(tasks_db: TaskDB) -> str:
        """Evening briefing: real tasks, honest gaps everywhere else."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        today_prefix = now.strftime("%Y-%m-%d")

        unconfigured = []

        def note(source: str) -> str:
            n = BriefingTemplates._note(source)
            if n:
                unconfigured.append(source)
                return n
            return ""

        # Concurrent, not sequential -- see morning_briefing's comment.
        calendar_note, weather_note = await asyncio.gather(
            BriefingTemplates._calendar_text(1, unconfigured),  # tomorrow preview
            BriefingTemplates._weather_text(True, unconfigured),  # tomorrow's forecast
        )
        health_note = note("health")

        open_tasks = tasks_db.get_open_tasks()
        done_today = [
            t for t in tasks_db.get_done_tasks()
            if (t.get("updated_at") or "").startswith(today_prefix)
        ]

        briefing = f"""
=== PROJECT SUNNY — EVENING BRIEFING ===

Good evening, Keaton. Here's your day recap.

TODAY: {date_str}

WHAT YOU ACCOMPLISHED
   • {len(done_today)} tasks completed today
{chr(10).join(f" {t['title']}" for t in done_today[:5])}

WHAT'S STILL PENDING ({len(open_tasks)} items)
{chr(10).join(f" ◯ {t['title']}" for t in open_tasks[:5]) if open_tasks else " (none)"}

TOMORROW AT A GLANCE
   {calendar_note}

TOMORROW'S WEATHER
   {weather_note}

TODAY'S WELLNESS
   {health_note}

Sleep well and rest up for tomorrow!
"""
        if unconfigured:
            log_unfulfilled(
                "evening_briefing",
                f"sections without a real data source: {', '.join(unconfigured)}",
            )

        return briefing

    @staticmethod
    async def custom_briefing(
        question: str,
        tasks_db: TaskDB,
        session_id: str = "default",
        on_chunk: Optional[OnChunk] = None,
        on_search_start: Optional[OnSearchStart] = None,
    ) -> str:
        """Answer a question with real data if we have it, an honest gap if we don't.

        on_chunk is optional and additive: when given, the LLM fallback
        (the final branch, for genuinely open-ended questions) streams
        its answer sentence-by-sentence through this callback as it's
        generated, in addition to still returning the complete
        accumulated string at the end exactly as before -- so a caller
        that doesn't pass on_chunk (every caller before 2026-08-21, and
        every text-based one still) sees zero behavior change. Built for
        /join specifically, so TTS can start speaking the first sentence
        while Claude is still writing the rest — see ask_claude_stream().

        The LLM fallback also has real web search available now (see
        llm_client.ask_claude[_stream]'s enable_web_search) -- Claude
        decides for itself whether a question actually needs it (see
        general-chat.md). on_search_start, if given (only meaningful
        alongside on_chunk -- the non-streaming path has no live-progress
        channel to fire it through), gets called the instant a search
        starts, so a caller can play/show a distinct "searching" cue
        for what's otherwise unexplained extra silence.

        docs_search.py runs unconditionally ahead of every fallback
        question (cheap -- local file reads, no LLM call) and prepends
        any well-matched doc content from sunny-vault/docs/ so a question
        about how Sunny itself works ("how does class setup work") gets
        answered from the real current docs instead of the model's own
        guess -- a genuinely unrelated question just scores 0 everywhere
        and the prompt is unchanged.

        session_id scopes conversation memory (see conversation_memory.py)
        for the LLM fallback specifically -- deliberately not applied to
        the deterministic branches above (weather/calendar/tasks/etc.),
        which are stateless by design and re-answered fresh every time."""
        question_lower = question.lower().strip()

        def unconfigured_reply(source: str, label: Optional[str] = None) -> str:
            log_unfulfilled("qa_question", f'"{question}" — {missing_requirement(source)}')
            return f"""
{label or _TOPIC_LABELS[source]}

{BriefingTemplates._note(source)}
"""

        # Weather questions
        if any(w in question_lower for w in ["weather", "forecast", "temperature", "rain", "sunny"]):
            if not is_configured("weather"):
                return unconfigured_reply("weather")
            return f"\n{_TOPIC_LABELS['weather']}\n\n{await BriefingTemplates._weather_text()}\n"

        # Calendar/Schedule questions
        elif any(s in question_lower for s in ["calendar", "schedule", "event", "meeting", "appointment", "when"]):
            if not is_configured("calendar"):
                return unconfigured_reply("calendar")
            return f"\n{_TOPIC_LABELS['calendar']}\n\n{await BriefingTemplates._calendar_text()}\n"

        # Email questions
        elif any(e in question_lower for e in ["email", "mail", "inbox", "message"]):
            if not is_configured("email"):
                return unconfigured_reply("email")
            return f"\n{_TOPIC_LABELS['email']}\n\n{await BriefingTemplates._email_text()}\n"

        # Task questions — real data
        elif any(t in question_lower for t in ["task", "todo", "checklist", "assignment"]):
            open_tasks = tasks_db.get_open_tasks()
            in_progress = tasks_db.get_in_progress_tasks()
            return f"""
YOUR TASKS

In progress ({len(in_progress)}):
{chr(10).join(f" → {t['title']}" for t in in_progress) if in_progress else " (none)"}

Open ({len(open_tasks)}):
{chr(10).join(f" ◯ {t['title']}" + (f" (due {t['due_date']})" if t['due_date'] else "") for t in open_tasks[:5]) if open_tasks else " (none)"}

Total: {len(open_tasks) + len(in_progress)} tasks
"""

        # Commute/Traffic questions
        elif any(c in question_lower for c in ["traffic", "commute", "drive", "route", "travel"]):
            return unconfigured_reply("commute")

        # Health/Wellness questions
        elif any(h in question_lower for h in ["health", "wellness", "sleep", "exercise", "step", "mood"]):
            return unconfigured_reply("health")

        # Motorsports questions
        elif any(m in question_lower for m in ["motorsport", "racing", "formula", "motogp", "f1", "nascar"]):
            return unconfigured_reply("motorsports")

        # News questions
        elif any(n in question_lower for n in ["news", "headline", "update"]):
            return unconfigured_reply("news")

        # Tomorrow questions
        elif "tomorrow" in question_lower:
            if not is_configured("calendar"):
                return unconfigured_reply("calendar", label="TOMORROW'S PREVIEW")
            return f"\nTOMORROW'S PREVIEW\n\n{await BriefingTemplates._calendar_text(1)}\n"

        # Default: nothing above matched — genuinely open-ended, hand it to
        # Claude for a real answer/conversation (judgment only, never used
        # for the data lookups above — those stay on real APIs or say so
        # honestly). ask_claude() never raises; None means not configured,
        # over budget, or a live API failure, all treated the same way.
        # Model/length/temperature are all live-tunable via .env
        # (LLM_CHAT_MODEL/LLM_CHAT_MAX_TOKENS/LLM_CHAT_TEMPERATURE) --
        # the actual behavior/tone/persona tuning knob is the system
        # prompt itself, sunny-vault/instructions/general-chat.md.
        else:
            settings = get_settings()
            prompt = (
                docs_search.format_for_prompt(docs_search.search(question))
                + conversation_memory.format_for_prompt(session_id) + question
            )
            if on_chunk is not None:
                parts = []
                async for sentence in ask_claude_stream(
                    prompt,
                    model=settings.llm_chat_model,
                    max_tokens=settings.llm_chat_max_tokens,
                    temperature=settings.llm_chat_temperature,
                    purpose="general_chat",
                    enable_web_search=True,
                    on_search_start=on_search_start,
                ):
                    parts.append(sentence)
                    await on_chunk(sentence)
                answer = " ".join(parts) if parts else None
            else:
                answer = await ask_claude(
                    prompt,
                    model=settings.llm_chat_model,
                    max_tokens=settings.llm_chat_max_tokens,
                    temperature=settings.llm_chat_temperature,
                    purpose="general_chat",
                    enable_web_search=True,
                )
            if answer:
                conversation_memory.record_turn(session_id, "user", question)
                conversation_memory.record_turn(session_id, "assistant", answer)
                return answer
            log_unfulfilled("qa_question", f'"{question}" — not understood, no matching topic')
            return f'No good answer for "{question}" — try asking about tasks, or say "help".'


_MORNING_PREWARM_MAX_AGE_SECONDS = 15 * 60 # a prep run more than this old is
# stale enough that live data is worth the wait again -- covers the case
# where nothing ever asked for the briefing near the alarm it was prepped for


class BriefingEngine:
    """Generate templated briefings with Q&A support."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        settings = get_settings()
        self.tasks_db = TaskDB(settings.project_root / "sunny-vault" / "state" / "tasks")
        # (text, generated_at) from the most recent prewarm_morning_briefing()
        # call -- see that method and generate_morning_briefing() below.
        self._prewarmed_morning: Optional[Tuple[str, float]] = None

    async def prewarm_morning_briefing(self) -> None:
        """Generates the morning briefing now (fresh weather/calendar/email,
        same as a live request) and caches it, so a real request shortly
        after — e.g. right after an alarm goes off — returns instantly
        instead of waiting on live API calls. Meant to be called a few
        minutes ahead of a known wake-up alarm (see discord_bot.py's
        scheduled_check_loop) so the cached copy's email is fresh at the
        moment it matters, not fetched hours earlier."""
        self.logger.info("Pre-warming morning briefing ahead of an upcoming alarm...")
        text = await BriefingTemplates.morning_briefing(self.tasks_db)
        self._prewarmed_morning = (text, time.monotonic())

    async def generate_morning_briefing(self) -> str:
        """Generate morning briefing — returns a recent prewarm_morning_briefing()
        result instead of hitting live APIs again if one's fresh enough."""
        if self._prewarmed_morning is not None:
            text, generated_at = self._prewarmed_morning
            self._prewarmed_morning = None  # one-shot -- the next call is either a fresh prewarm or a live fetch
            if time.monotonic() - generated_at <= _MORNING_PREWARM_MAX_AGE_SECONDS:
                self.logger.info("Using pre-warmed morning briefing")
                return text
        self.logger.info("Generating morning briefing...")
        return await BriefingTemplates.morning_briefing(self.tasks_db)

    async def generate_evening_briefing(self) -> str:
        """Generate evening briefing."""
        self.logger.info("Generating evening briefing...")
        return await BriefingTemplates.evening_briefing(self.tasks_db)

    async def answer_question(
        self,
        question: str,
        session_id: str = "default",
        on_chunk: Optional[OnChunk] = None,
        on_search_start: Optional[OnSearchStart] = None,
    ) -> str:
        """Answer a natural language question about today's data. See
        custom_briefing()'s docstring for on_chunk's streaming contract,
        on_search_start's web-search cue contract, and session_id's
        conversation-memory scope."""
        self.logger.info(f"Processing question: {question}")
        return await BriefingTemplates.custom_briefing(
            question, self.tasks_db, session_id=session_id, on_chunk=on_chunk, on_search_start=on_search_start
        )
