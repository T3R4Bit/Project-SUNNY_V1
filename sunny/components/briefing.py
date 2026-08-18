"""Briefing engine for morning/evening summaries."""

import logging
from datetime import datetime
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class BriefingTemplate:
    """Hardcoded briefing templates."""

    MORNING_TEMPLATE = """
Good morning, Keaton.

Today is {date}.

**Calendar**: {calendar_summary}

**Weather**: {weather_summary}

**Traffic**: {traffic_summary}

**Email**: {email_summary}

**Tasks**: {task_summary}

Have a great day.
    """

    EVENING_TEMPLATE = """
Good evening, Keaton.

Here's your day recap.

**Completed**: {completed_tasks}

**Pending**: {pending_tasks}

**Tomorrow**: {tomorrow_preview}

Sleep well.
    """


class BriefingEngine:
    """Generate templated briefings from API data."""

    def __init__(self):
        self.template = BriefingTemplate()
        self.logger = logging.getLogger(__name__)

    async def generate_morning_briefing(self) -> str:
        """Generate morning briefing with real data."""
        self.logger.info("Generating morning briefing...")

        # Placeholder data (will integrate APIs in Phase 2)
        briefing_data = {
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "calendar_summary": "3 events today",
            "weather_summary": "72°F, partly cloudy",
            "traffic_summary": "Light traffic on your commute",
            "email_summary": "5 new emails, 2 urgent",
            "task_summary": "6 tasks today",
        }

        briefing = self.template.MORNING_TEMPLATE.format(**briefing_data)
        self.logger.info("Morning briefing generated")
        return briefing

    async def generate_evening_briefing(self) -> str:
        """Generate evening briefing with day recap."""
        self.logger.info("Generating evening briefing...")

        briefing_data = {
            "completed_tasks": "4 tasks finished",
            "pending_tasks": "2 tasks remaining",
            "tomorrow_preview": "2 meetings, good weather",
        }

        briefing = self.template.EVENING_TEMPLATE.format(**briefing_data)
        self.logger.info("Evening briefing generated")
        return briefing
