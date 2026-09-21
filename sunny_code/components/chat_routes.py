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

from sunny_code.components import chat_store
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
    # The durable conversation this message belongs to. Omitted means
    # "start a new one" -- the id comes back on the `done` event so the
    # client can keep using it. Everything is persisted against this (see
    # chat_store), which is what makes a conversation survive a reload.
    conversation_id: Optional[str] = None
    # Kept for non-web callers (scripts, the Pi fallback) that want
    # in-memory continuity without a stored transcript. When
    # conversation_id is given, the session is derived from it instead,
    # so each conversation gets its own prompt context rather than all
    # of them sharing one.
    session_id: Optional[str] = None


class RenameRequest(BaseModel):
    title: str


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
        conversation_id = chat_store.ensure_conversation(body.conversation_id)
        session_id = body.session_id or f"web:{conversation_id}"

        # Replay recent turns into conversation_memory before handling, so
        # a conversation resumed after a restart actually resumes rather
        # than just looking like it did.
        chat_store.hydrate_memory(conversation_id, session_id)
        chat_store.add_message(conversation_id, "user", body.message)

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
                        session_id=session_id,
                        on_chunk=on_chunk,
                        on_search_start=on_search_start,
                    ),
                    timeout=_REPLY_TIMEOUT_SECONDS,
                )
                # Command replies never stream -- emit the whole thing as
                # one chunk so the client has a single code path.
                if reply and not streamed:
                    await queue.put(("chunk", {"text": reply}))
                # Persist after the reply is complete, not per chunk: a
                # half-written answer in the transcript would be worse
                # than none, and the write must not sit in the stream's
                # critical path.
                if reply:
                    await asyncio.to_thread(chat_store.add_message, conversation_id, "assistant", reply)
                await queue.put(("done", {"text": reply or "", "conversation_id": conversation_id}))
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
        conversation_id = chat_store.ensure_conversation(body.conversation_id)
        session_id = body.session_id or f"web:{conversation_id}"
        chat_store.hydrate_memory(conversation_id, session_id)
        chat_store.add_message(conversation_id, "user", body.message)
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
                    session_id=session_id,
                ),
                timeout=_REPLY_TIMEOUT_SECONDS,
            )
            if reply:
                chat_store.add_message(conversation_id, "assistant", reply)
            return {"ok": True, "reply": reply or "", "conversation_id": conversation_id}
        except asyncio.TimeoutError:
            return {"ok": False, "reply": "That took too long — try again.", "conversation_id": conversation_id}
        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            return {"ok": False, "reply": f"Something went wrong: {type(e).__name__}", "conversation_id": conversation_id}

    # --- conversations ----------------------------------------------------

    @router.get("/chat/conversations")
    async def list_conversations(limit: int = 50):
        """Sidebar list: newest first, with a preview of the last message."""
        return {"conversations": chat_store.list_conversations(limit=limit)}

    @router.get("/chat/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, limit: int = 500):
        """Full transcript, for rendering a conversation on page load."""
        return {
            "conversation_id": conversation_id,
            "messages": chat_store.get_messages(conversation_id, limit=limit),
        }

    @router.post("/chat/conversations")
    async def new_conversation():
        return {"conversation_id": chat_store.create_conversation()}

    @router.patch("/chat/conversations/{conversation_id}")
    async def rename_conversation(conversation_id: str, body: RenameRequest):
        return {"ok": chat_store.rename_conversation(conversation_id, body.title)}

    @router.delete("/chat/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str):
        """Also clears the in-memory context, so a new conversation that
        happens to reuse the session key cannot inherit deleted turns."""
        from sunny_code.components import conversation_memory

        conversation_memory._history.pop(f"web:{conversation_id}", None)
        conversation_memory._last_touched.pop(f"web:{conversation_id}", None)
        return {"ok": chat_store.delete_conversation(conversation_id)}

    return router
