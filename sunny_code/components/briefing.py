"""Briefing engine with hardcoded templates, real task data, and honest Q&A support.

Tasks are real (queried straight from tasks.db). Weather, calendar, email, commute,
health, news, and motorsports have no live API wired up yet, so sections/questions
about them say so explicitly instead of pretending mock data is real — and every
time that happens, it gets logged to sunny-vault/log/requests.md.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sunny_code.config import get_settings
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.data_sources import is_configured, missing_requirement
from sunny_code.components.request_log import log_unfulfilled


logger = logging.getLogger(__name__)

_TOPIC_LABELS = {
    "weather": "🌤️  WEATHER FORECAST",
    "calendar": "📅 YOUR SCHEDULE",
    "email": "📧 EMAIL SUMMARY",
    "commute": "🚗 COMMUTE INFORMATION",
    "health": "❤️  WELLNESS STATUS",
    "motorsports": "🏁 MOTORSPORTS UPDATE",
    "news": "📰 TODAY'S HEADLINES",
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
                line += f" [⚠️ {priority.upper()}]"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _note(source: str) -> Optional[str]:
        """'Not connected' note for a source, or None if it's real."""
        if is_configured(source):
            return None
        return f"⚠️  Not connected — {missing_requirement(source)}"

    @staticmethod
    def morning_briefing(tasks_db: TaskDB) -> str:
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

        weather_note = note("weather")
        calendar_note = note("calendar")
        email_note = note("email")
        commute_note = note("commute")
        health_note = note("health")
        news_note = note("news")

        open_tasks = tasks_db.get_open_tasks()
        in_progress = tasks_db.get_in_progress_tasks()
        task_count = len(open_tasks) + len(in_progress)
        top = (in_progress + open_tasks)[0] if (in_progress or open_tasks) else None
        task_str = f"{len(in_progress)} in progress, {len(open_tasks)} open — {task_count} total"

        briefing = f"""
=== PROJECT SUNNY — MORNING BRIEFING ===

Good morning, Keaton! Here's your day at a glance.

📅 TODAY: {date_str}

🌤️  WEATHER
   {weather_note}

📍 COMMUTE
   {commute_note}

📅 TODAY'S SCHEDULE
   {calendar_note}

📧 EMAIL
   {email_note}

✅ TASKS ({task_count} total)
   {task_str}
   Top priority: {top['title'] if top else 'None'}

❤️  WELLNESS
   {health_note}

📰 HEADLINES
   {news_note}

🎯 YOUR DAY AHEAD
   1. Focus on: {top['title'] if top else 'nothing on your task list right now'}
   2. {len(unconfigured)} section(s) above need a real data source connected — logged to sunny-vault/log/requests.md

Have a productive day! ☀️
"""
        if unconfigured:
            log_unfulfilled(
                "morning_briefing",
                f"sections without a real data source: {', '.join(unconfigured)}",
            )

        return briefing

    @staticmethod
    def evening_briefing(tasks_db: TaskDB) -> str:
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

        calendar_note = note("calendar")
        weather_note = note("weather")
        health_note = note("health")

        open_tasks = tasks_db.get_open_tasks()
        done_today = [
            t for t in tasks_db.get_done_tasks()
            if (t.get("updated_at") or "").startswith(today_prefix)
        ]

        briefing = f"""
=== PROJECT SUNNY — EVENING BRIEFING ===

Good evening, Keaton. Here's your day recap.

📅 TODAY: {date_str}

🎉 WHAT YOU ACCOMPLISHED
   • {len(done_today)} tasks completed today
{chr(10).join(f"   ✓ {t['title']}" for t in done_today[:5])}

📋 WHAT'S STILL PENDING ({len(open_tasks)} items)
{chr(10).join(f"   ◯ {t['title']}" for t in open_tasks[:5]) if open_tasks else "   (none)"}

⏰ TOMORROW AT A GLANCE
   {calendar_note}

🌤️  TOMORROW'S WEATHER
   {weather_note}

❤️  TODAY'S WELLNESS
   {health_note}

Sleep well and rest up for tomorrow! 🌙
"""
        if unconfigured:
            log_unfulfilled(
                "evening_briefing",
                f"sections without a real data source: {', '.join(unconfigured)}",
            )

        return briefing

    @staticmethod
    def custom_briefing(question: str, tasks_db: TaskDB) -> str:
        """Answer a question with real data if we have it, an honest gap if we don't."""
        question_lower = question.lower().strip()

        def unconfigured_reply(source: str, label: Optional[str] = None) -> str:
            log_unfulfilled("qa_question", f'"{question}" — {missing_requirement(source)}')
            return f"""
{label or _TOPIC_LABELS[source]}

{BriefingTemplates._note(source)}
"""

        # Weather questions
        if any(w in question_lower for w in ["weather", "forecast", "temperature", "rain", "sunny"]):
            return unconfigured_reply("weather")

        # Calendar/Schedule questions
        elif any(s in question_lower for s in ["calendar", "schedule", "event", "meeting", "appointment", "when"]):
            return unconfigured_reply("calendar")

        # Email questions
        elif any(e in question_lower for e in ["email", "mail", "inbox", "message"]):
            return unconfigured_reply("email")

        # Task questions — real data
        elif any(t in question_lower for t in ["task", "todo", "checklist", "assignment"]):
            open_tasks = tasks_db.get_open_tasks()
            in_progress = tasks_db.get_in_progress_tasks()
            return f"""
✅ YOUR TASKS

In progress ({len(in_progress)}):
{chr(10).join(f"  → {t['title']}" for t in in_progress) if in_progress else "  (none)"}

Open ({len(open_tasks)}):
{chr(10).join(f"  ◯ {t['title']}" + (f" (due {t['due_date']})" if t['due_date'] else "") for t in open_tasks[:5]) if open_tasks else "  (none)"}

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
            return unconfigured_reply("calendar", label="📅 TOMORROW'S PREVIEW")

        # Default response — genuinely don't understand the question
        else:
            log_unfulfilled("qa_question", f'"{question}" — not understood, no matching topic')
            return f"""
I don't have a real answer for: "{question}"

I can give you real data on:
• Tasks (open, in progress, due soon)

These need a data source connected before I can answer for real:
• Weather, calendar, email, commute, health, motorsports, news

Try asking about tasks — or check sunny-vault/log/requests.md, every question I can't answer for real gets logged there.
"""


class BriefingEngine:
    """Generate templated briefings with Q&A support."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        settings = get_settings()
        self.tasks_db = TaskDB(settings.project_root / "tasks.db")

    async def generate_morning_briefing(self) -> str:
        """Generate morning briefing."""
        self.logger.info("Generating morning briefing...")
        return BriefingTemplates.morning_briefing(self.tasks_db)

    async def generate_evening_briefing(self) -> str:
        """Generate evening briefing."""
        self.logger.info("Generating evening briefing...")
        return BriefingTemplates.evening_briefing(self.tasks_db)

    async def answer_question(self, question: str) -> str:
        """Answer a natural language question about today's data."""
        self.logger.info(f"Processing question: {question}")
        return BriefingTemplates.custom_briefing(question, self.tasks_db)
