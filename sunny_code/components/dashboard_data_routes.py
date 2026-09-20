"""Structured Calendar/Gmail read endpoints for external dashboards (e.g.
keaton.dev) that today only have the merged briefing text. Read-only, same
fail-quiet contract as google_calendar.py / google_gmail.py.
"""

import asyncio
import logging

from fastapi import APIRouter, Query

from sunny_code.components import google_auth, google_calendar, google_gmail

logger = logging.getLogger(__name__)


def _google_connected() -> bool:
    """Whether stored Google credentials exist and still load. Distinguishes
    "never connected" from "connected but the call failed" for the callers
    below -- a distinction the dashboard needs and could not previously make."""
    try:
        return google_auth.get_credentials() is not None
    except Exception as e:
        logger.warning(f"Google credential check failed: {type(e).__name__}: {e}")
        return False


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
            # get_flagged() returns None for two very different situations:
            # Google was never connected, or it is connected and the call
            # failed (expired refresh token, a scope granted before Gmail
            # was added, an API error). Both used to render as the same
            # bland "not connected" placeholder, which is why Gmail could
            # look broken on the dashboard with no way to tell what was
            # actually wrong -- especially since /auth/google/status checks
            # credentials rather than scopes and would happily report
            # "OK · your@email" alongside it.
            connected = await asyncio.to_thread(_google_connected)
            return {
                "available": False,
                "messages": [],
                "reason": "call_failed" if connected else "not_connected",
                "detail": (
                    "Google is connected but the Gmail call failed — the token may be "
                    "expired, or was granted before the gmail.readonly scope was added. "
                    "Reconnect at /auth/google/login. See sunny.log for the API error."
                    if connected
                    else "Google isn't connected — sign in at /auth/google/login."
                ),
            }
        return {"available": True, "messages": flagged, "reason": None, "detail": None}

    return router
