"""API routes for briefing engine."""

import logging
from fastapi import APIRouter, Query
from sunny.components.briefing import BriefingEngine

logger = logging.getLogger(__name__)


def create_briefing_router() -> APIRouter:
    """Create briefing API routes."""
    router = APIRouter(prefix="/briefing")
    engine = BriefingEngine()

    @router.get("/morning")
    async def get_morning_briefing():
        """Get full morning briefing."""
        briefing = await engine.generate_morning_briefing()
        return {
            "type": "morning",
            "timestamp": "2026-08-18T08:00:00Z",
            "content": briefing,
        }

    @router.get("/evening")
    async def get_evening_briefing():
        """Get full evening briefing."""
        briefing = await engine.generate_evening_briefing()
        return {
            "type": "evening",
            "timestamp": "2026-08-18T20:00:00Z",
            "content": briefing,
        }

    @router.get("/ask")
    async def ask_question(q: str = Query(..., description="Question about your day")):
        """Ask the briefing engine a question."""
        response = await engine.answer_question(q)
        return {
            "question": q,
            "response": response,
        }

    @router.post("/test")
    async def test_briefing(question: str):
        """Test endpoint for POST requests."""
        response = await engine.answer_question(question)
        return {
            "question": question,
            "response": response,
        }

    return router
