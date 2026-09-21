"""HTTP chat with streaming replies -- the web/PWA equivalent of the
Discord bot and the Pi's WebSocket.

Routes through assistant.handle_message() exactly like every other
interface, so a task created here is the same task created by saying it
in Discord. This file owns transport and nothing else; any behavior
difference between interfaces would be a bug.

WHY SSE AND NOT A WEBSOCKET
---------------------------
The Pi uses a WebSocket because it streams binary audio both ways.
Browser chat is one request in, a stream of text out -- which is exactly
what Server-Sent Events are for. SSE survives proxies that mangle
WebSocket upgrades (this is served through `tailscale serve`), reconnects
on its own, and needs no connection state on either end.

STREAMING SHAPE
---------------
on_chunk only fires on the open-ended LLM path. Command replies (tasks,
lists, alarms, briefings) are computed synchronously and returned whole --
see pi_companion.py, which handles the same split. So a client cannot
assume chunks will arrive, and this normalizes the two: if the handler
finishes without having streamed anything, the full reply is emitted as a
single chunk before `done`. The client therefore only ever implements one
path.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sunny_code.components.assistant import handle_message
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.calendar_engine import CalendarEngine
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.spotify_engine import SpotifyEngine
from sunny_code.components.tasks_engine import TaskEngine

logger = logging.getLogger(__name__)

# Long enough for a slow Claude call with a web search in it, short enough
# that a wedged handler can't hold a connection open forever.
_REPLY_TIMEOUT_SECONDS = 180


class ChatMessage(BaseModel):
    message: str
    # One conversation per session id. Defaults to a single shared web
    # session rather than a random one per request, so follow-ups
    # ("why?", "the second one") resolve -- conversation_memory is keyed
    # on this. A per-request id would silently disable memory while
    # looking like it worked.
    session_id: str = "web:chat"


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def create_chat_router(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    project_engine: ProjectEngine,
    spotify_engine: SpotifyEngine,
    calendar_engine: CalendarEngine,
) -> APIRouter:
    """Takes the same shared engine instances as the Discord bot and the Pi
    router, so state stays in sync across interfaces rather than forking."""
    router = APIRouter()

    @router.post("/chat/stream")
    async def chat_stream(body: ChatMessage):
        queue: asyncio.Queue = asyncio.Queue()
        streamed = False

        async def on_chunk(sentence: str) -> None:
            nonlocal streamed
            streamed = True
            await queue.put(("chunk", {"text": sentence}))

        async def on_search_start() -> None:
            await queue.put(("state", {"state": "searching"}))

        async def run() -> None:
            try:
                reply = await asyncio.wait_for(
                    handle_message(
                        body.message,
                        tasks_engine,
                        briefing_engine,
                        list_engine,
                        scheduled_engine,
                        project_engine,
                        spotify_engine,
                        calendar_engine,
                        session_id=body.session_id,
                        on_chunk=on_chunk,
                        on_search_start=on_search_start,
                    ),
                    timeout=_REPLY_TIMEOUT_SECONDS,
                )
                # Command replies never stream -- emit the whole thing as
                # one chunk so the client has a single code path.
                if reply and not streamed:
                    await queue.put(("chunk", {"text": reply}))
                await queue.put(("done", {"text": reply or ""}))
            except asyncio.TimeoutError:
                logger.error(f"Chat timed out after {_REPLY_TIMEOUT_SECONDS}s: {body.message[:80]!r}")
                await queue.put(("error", {"text": "That took too long — try again."}))
            except Exception as e:
                # The transport must fail visibly rather than hanging the
                # browser on a stream that never closes.
                logger.error(f"Chat failed: {e}", exc_info=True)
                await queue.put(("error", {"text": f"Something went wrong: {type(e).__name__}"}))
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())

        async def events():
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    event, payload = item
                    yield _sse(event, payload)
            finally:
                # Browser navigated away mid-reply: stop the work rather
                # than leaving an orphaned Claude call running.
                if not task.done():
                    task.cancel()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Defensive: some proxies buffer streamed responses into a
                # single delivery, which turns streaming into a long wait
                # with no visible difference from a hang.
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/chat")
    async def chat_once(body: ChatMessage):
        """Non-streaming equivalent, for callers that just want the reply
        (scripts, the Pi's fallback, a client that can't do SSE)."""
        try:
            reply = await asyncio.wait_for(
                handle_message(
                    body.message,
                    tasks_engine,
                    briefing_engine,
                    list_engine,
                    scheduled_engine,
                    project_engine,
                    spotify_engine,
                    calendar_engine,
                    session_id=body.session_id,
                ),
                timeout=_REPLY_TIMEOUT_SECONDS,
            )
            return {"ok": True, "reply": reply or "", "session_id": body.session_id}
        except asyncio.TimeoutError:
            return {"ok": False, "reply": "That took too long — try again.", "session_id": body.session_id}
        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            return {"ok": False, "reply": f"Something went wrong: {type(e).__name__}", "session_id": body.session_id}

    return router
