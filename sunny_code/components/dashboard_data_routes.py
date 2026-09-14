"""Structured Calendar/Gmail read endpoints for external dashboards (e.g.
keaton.dev) that today only have the merged briefing text. Read-only, same
fail-quiet contract as google_calendar.py / google_gmail.py.
"""

import asyncio
import logging

from fastapi import APIRouter, Query

from sunny_code.components import google_calendar, google_gmail

logger = logging.getLogger(__name__)


def create_dashboard_data_router() -> APIRouter:
    """Create dashboard data API routes."""
    router = APIRouter()

    @router.get("/calendar/today")
    async def calendar_today():
        events = await asyncio.to_thread(google_calendar.get_events, 0)
        if events is None:
            return {"available": False, "events": []}
        return {
            "available": True,
            "events": [
                {"time": e["time"], "title": e["title"], "meta": e["location"] or ""} for e in events
            ],
        }

    @router.get("/gmail/flagged")
    async def gmail_flagged(limit: int = Query(5, ge=1, le=20)):
        flagged = await asyncio.to_thread(google_gmail.get_flagged, limit)
        if flagged is None:
            return {"available": False, "messages": []}
        return {"available": True, "messages": flagged}

    return router
