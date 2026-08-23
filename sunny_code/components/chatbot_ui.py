"""Chat message API, shared by the console UI (/console) and the Discord bot.

The chat page itself lives in console_stats.py — this module used to also serve
a standalone /chatbot page, but that's been folded into /console as one surface.
/chatbot and / both just redirect there now for old bookmarks/links.
"""

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
import logging

from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.spotify_engine import SpotifyEngine
from sunny_code.components.assistant import handle_message

logger = logging.getLogger(__name__)


def create_chatbot_router(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    project_engine: ProjectEngine,
    spotify_engine: SpotifyEngine,
) -> APIRouter:
    """Create chatbot routes: the message API plus redirects to /console.

    Takes shared engine instances (same ones the REST API and Discord bot use) so
    a change made here triggers the same on_change effects everywhere else.
    """
    router = APIRouter(prefix="")

    @router.get("/")
    async def root():
        """Redirect root to the console (chat + system status)."""
        return RedirectResponse(url="/console")

    @router.get("/chatbot")
    async def chatbot_redirect():
        """Old standalone chat page — now part of /console."""
        return RedirectResponse(url="/console")

    @router.post("/api/assistant/message")
    async def assistant_message(
        text: str = Query(..., description="Free-text message from the chatbot"),
        session: str = Query("web-default", description="Per-browser session ID, for follow-up questions"),
    ):
        """Single entry point for the chatbot — routing lives in sunny_code.components.assistant
        so the web chatbot and the Discord bot behave identically."""
        response = await handle_message(
            text, tasks_engine, briefing_engine, list_engine, scheduled_engine,
            project_engine, spotify_engine, session_id=f"web:{session}"
        )
        return {"response": response}

    return router
