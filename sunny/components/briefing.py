"""Briefing engine with comprehensive hardcoded templates and Q&A support."""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from sunny.components.briefing_data import (
    MockWeatherData,
    MockCalendarData,
    MockEmailData,
    MockTaskData,
    MockTrafficData,
    MockHealthData,
    MockNewsData,
    MockMotorsportsData,
)


logger = logging.getLogger(__name__)


class BriefingTemplates:
    """Comprehensive hardcoded briefing templates."""

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
    def morning_briefing() -> str:
        """Comprehensive morning briefing."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        day_of_week = now.strftime("%A")

        weather = MockWeatherData.get_forecast()
        events = MockCalendarData.get_today_events()
        emails = MockEmailData.get_summary()
        tasks = MockTaskData.get_today()
        commute = MockTrafficData.get_commute()
        health = MockHealthData.get_stats()
        news = MockNewsData.get_headlines()

        # Format email summary
        email_str = f"{emails['urgent']} urgent, {emails['action_items']} action items, {emails['fyi']} for your information"

        # Format tasks
        pending = [t for t in tasks if t["status"] == "pending"]
        in_progress = [t for t in tasks if t["status"] == "in_progress"]
        task_count = len(pending) + len(in_progress)
        task_str = f"{len(in_progress)} in progress, {len(pending)} pending — {task_count} total today"

        # Format commute
        commute_str = (
            f"{commute['route']}: normally {commute['normal']}, "
            f"currently {commute['current']} ({commute['status']})"
        )

        briefing = f"""
=== PROJECT SUNNY — MORNING BRIEFING ===

Good morning, Keaton! Here's your day at a glance.

📅 TODAY: {date_str}

🌤️  WEATHER
   Current: {weather['temp']}°F, {weather['condition']}
   High: {weather['high']}°F | Low: {weather['low']}°F
   Humidity: {weather['humidity']}% | Wind: {weather['wind_speed']} mph
   UV Index: {weather['uv_index']} | Sunrise: {weather['sunrise']} | Sunset: {weather['sunset']}

📍 COMMUTE
   {commute_str}

📅 TODAY'S SCHEDULE ({len(events)} events)
{BriefingTemplates.format_time_list(events)}

📧 EMAIL ({emails['total']} new)
   {email_str}

✅ TASKS ({task_count} total)
   {task_str}
   Top priority: {in_progress[0]['title'] if in_progress else pending[0]['title'] if pending else 'None'}

❤️  WELLNESS
   Sleep last night: {health['sleep_last_night']} ({health['sleep_quality']})
   Steps: {health['steps_today']} of {health['steps_goal']}
   Water: {health['water_intake']}
   Mood: {health['mood']}

📰 HEADLINES (selected for you)
{chr(10).join(f"   • {h}" for h in news[:3])}

🏁 MOTORSPORTS
{chr(10).join(f"   • {u.get('headline', u.get('event'))}" for u in MockMotorsportsData.get_updates()[:2])}

🎯 YOUR DAY AHEAD
   1. Focus on {in_progress[0]['title'] if in_progress else pending[0]['title'] if pending else 'your tasks'}
   2. Attend {events[0]['title'] if events else 'your first meeting'} at {events[0]['time'] if events else '9 AM'}
   3. Keep an eye on email ({emails['urgent']} urgent items need response)
   4. Hydration reminder: {health['water_intake']}
   5. Exercise planned: {health['exercise']}

Have a productive day! ☀️
"""
        return briefing

    @staticmethod
    def evening_briefing() -> str:
        """Comprehensive evening briefing."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")

        completed = MockTaskData.get_completed()
        tasks = MockTaskData.get_today()
        tomorrow_events = MockCalendarData.get_tomorrow_events()
        weather = MockWeatherData.get_forecast()
        health = MockHealthData.get_stats()

        pending = [t for t in tasks if t["status"] == "pending"]
        completed_count = len(completed)

        briefing = f"""
=== PROJECT SUNNY — EVENING BRIEFING ===

Good evening, Keaton. Here's your day recap.

📅 TODAY: {date_str}

🎉 WHAT YOU ACCOMPLISHED
   • {completed_count} tasks completed today
{chr(10).join(f"   ✓ {c}" for c in completed[:5])}

📋 WHAT'S STILL PENDING ({len(pending)} items)
{chr(10).join(f"   ◯ {t['title']}" for t in pending[:5])}

⏰ TOMORROW AT A GLANCE ({len(tomorrow_events)} events)
{BriefingTemplates.format_time_list(tomorrow_events) if tomorrow_events else "   Rest day scheduled"}

🌤️  TOMORROW'S WEATHER
   Current forecast: {weather['temp']}°F, {weather['condition']}
   High: {weather['high']}°F | Low: {weather['low']}°F
   Plan accordingly!

❤️  TODAY'S WELLNESS
   Sleep quality last night: {health['sleep_quality']}
   Steps taken: {health['steps_today']} of {health['steps_goal']}
   Water intake: {health['water_intake']}
   Overall mood: {health['mood']}

🎯 EVENING GOALS
   1. ✅ Review {completed_count} tasks completed
   2. 📝 Plan tomorrow: {len(tomorrow_events)} events confirmed
   3. 🌙 Wind down routine at 10:30 PM
   4. 💤 Aim for 8 hours of sleep
   5. 📱 Device off 30 min before bed

✨ REFLECTION
   You had a solid day with {completed_count} tasks completed.
   {len(pending)} items remain—prioritize these for tomorrow.
   Great work on staying active with {health['steps_today']} steps!

Sleep well and rest up for tomorrow! 🌙
"""
        return briefing

    @staticmethod
    def custom_briefing(question: str) -> str:
        """Generate response to a custom question."""
        question_lower = question.lower().strip()

        # Weather questions
        if any(w in question_lower for w in ["weather", "forecast", "temperature", "rain", "sunny"]):
            weather = MockWeatherData.get_forecast()
            return f"""
🌤️  WEATHER FORECAST

Current conditions:
• Temperature: {weather['temp']}°F ({weather['condition']})
• High/Low: {weather['high']}°F / {weather['low']}°F
• Humidity: {weather['humidity']}%
• Wind: {weather['wind_speed']} mph
• UV Index: {weather['uv_index']}
• Sunrise: {weather['sunrise']} | Sunset: {weather['sunset']}

Recommendation: {"Bring an umbrella" if "rain" in weather['condition'].lower() else "No rain expected today"}
"""

        # Calendar/Schedule questions
        elif any(s in question_lower for s in ["calendar", "schedule", "event", "meeting", "appointment", "when"]):
            events = MockCalendarData.get_today_events()
            return f"""
📅 YOUR SCHEDULE

Today's events ({len(events)} total):
{BriefingTemplates.format_time_list(events)}

Next event: {events[0]['title'] if events else 'No events scheduled'} at {events[0]['time'] if events else 'N/A'}
"""

        # Email questions
        elif any(e in question_lower for e in ["email", "mail", "inbox", "message"]):
            emails = MockEmailData.get_summary()
            details = MockEmailData.get_details()
            return f"""
📧 EMAIL SUMMARY

New emails: {emails['total']}
• Urgent: {emails['urgent']} messages
• Action items: {emails['action_items']} messages
• For your information: {emails['fyi']} messages

Urgent emails from:
{chr(10).join(f"  • {e['sender']}: {e['subject']}" for e in details['urgent'][:2])}

Action items:
{chr(10).join(f"  • {e['sender']}: {e['subject']}" for e in details['action_items'][:2])}
"""

        # Task questions
        elif any(t in question_lower for t in ["task", "todo", "checklist", "assignment"]):
            tasks = MockTaskData.get_today()
            pending = [t for t in tasks if t["status"] == "pending"]
            in_progress = [t for t in tasks if t["status"] == "in_progress"]
            return f"""
✅ YOUR TASKS

In progress ({len(in_progress)}):
{chr(10).join(f"  → {t['title']}" for t in in_progress)}

Pending ({len(pending)}):
{chr(10).join(f"  ◯ {t['title']} (due {t['due']})" for t in pending[:5])}

Total: {len(tasks)} tasks today
"""

        # Commute/Traffic questions
        elif any(c in question_lower for c in ["traffic", "commute", "drive", "route", "travel"]):
            commute = MockTrafficData.get_commute()
            return f"""
🚗 COMMUTE INFORMATION

Route: {commute['route']}
Normal travel time: {commute['normal']}
Current travel time: {commute['current']}
Status: {commute['status']}

Recommendation: {"Leave now if you haven't started" if "Heavy" in commute['status'] else "You have time to go"}
"""

        # Health/Wellness questions
        elif any(h in question_lower for h in ["health", "wellness", "sleep", "exercise", "step", "mood"]):
            health = MockHealthData.get_stats()
            return f"""
❤️  WELLNESS STATUS

Sleep: {health['sleep_last_night']} ({health['sleep_quality']})
Activity: {health['steps_today']} steps (goal: {health['steps_goal']})
Hydration: {health['water_intake']}
Exercise: {health['exercise']}
Mood: {health['mood']}

Wellness tip: Keep up the hydration and you're on pace for your daily steps!
"""

        # Motorsports questions
        elif any(m in question_lower for m in ["motorsport", "racing", "formula", "motogp", "f1", "nascar"]):
            updates = MockMotorsportsData.get_updates()
            return f"""
🏁 MOTORSPORTS UPDATE

{chr(10).join(f"  • {u.get('headline', u.get('event', 'Racing update'))}" for u in updates)}

Stay tuned for the next race weekend!
"""

        # News questions
        elif any(n in question_lower for n in ["news", "headline", "update"]):
            news = MockNewsData.get_headlines()
            return f"""
📰 TODAY'S HEADLINES

{chr(10).join(f"  • {h}" for h in news)}

Curated for your interests.
"""

        # Tomorrow questions
        elif "tomorrow" in question_lower:
            tomorrow_events = MockCalendarData.get_tomorrow_events()
            return f"""
📅 TOMORROW'S PREVIEW

Tomorrow's schedule ({len(tomorrow_events)} events):
{BriefingTemplates.format_time_list(tomorrow_events)}

Weather: {MockWeatherData.get_forecast()['temp']}°F and {MockWeatherData.get_forecast()['condition'].lower()}

Prepare: Get good sleep tonight!
"""

        # Default response
        else:
            return f"""
I understood your question: "{question}"

Available topics I can brief you on:
• Weather & forecast
• Your calendar & schedule
• Email & messages
• Tasks & to-do list
• Commute & traffic
• Health & wellness
• Motorsports news
• General headlines
• Tomorrow's preview

Try asking: "What's the weather?" or "Tell me about my schedule"
"""


class BriefingEngine:
    """Generate templated briefings with Q&A support."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def generate_morning_briefing(self) -> str:
        """Generate comprehensive morning briefing."""
        self.logger.info("Generating morning briefing...")
        return BriefingTemplates.morning_briefing()

    async def generate_evening_briefing(self) -> str:
        """Generate comprehensive evening briefing."""
        self.logger.info("Generating evening briefing...")
        return BriefingTemplates.evening_briefing()

    async def answer_question(self, question: str) -> str:
        """Answer a natural language question about today's data."""
        self.logger.info(f"Processing question: {question}")
        return BriefingTemplates.custom_briefing(question)
