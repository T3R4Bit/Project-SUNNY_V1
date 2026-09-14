"""API routes for briefing engine."""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components import suggestion_tracker

logger = logging.getLogger(__name__)


class BriefFeedback(BaseModel):
    suggestion_id: str
    outcome: str  # "helpful" | "not_helpful"


def create_briefing_router() -> APIRouter:
    """Create briefing API routes."""
    router = APIRouter(prefix="/briefing")
    engine = BriefingEngine()

    @router.get("/morning")
    async def get_morning_briefing():
        """Get full morning briefing."""
        briefing = await engine.generate_morning_briefing()
        suggestion_id = suggestion_tracker.record_suggestion("morning_brief", briefing)
        return {
            "type": "morning",
            "timestamp": "2026-08-18T08:00:00Z",
            "content": briefing,
            "suggestion_id": suggestion_id,
        }

    @router.get("/evening")
    async def get_evening_briefing():
        """Get full evening briefing."""
        briefing = await engine.generate_evening_briefing()
        suggestion_id = suggestion_tracker.record_suggestion("evening_brief", briefing)
        return {
            "type": "evening",
            "timestamp": "2026-08-18T20:00:00Z",
            "content": briefing,
            "suggestion_id": suggestion_id,
        }

    @router.post("/feedback")
    async def briefing_feedback(body: BriefFeedback):
        """Records whether a morning/evening briefing was helpful, keyed by
        the suggestion_id returned alongside it — feeds suggestion_tracker's
        acceptance_rate() for these kinds."""
        if body.outcome not in ("helpful", "not_helpful"):
            raise HTTPException(status_code=400, detail="outcome must be 'helpful' or 'not_helpful'")
        mapped = "accepted" if body.outcome == "helpful" else "rejected"
        suggestion_tracker.record_outcome(body.suggestion_id, mapped)
        return {"status": "recorded"}

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
