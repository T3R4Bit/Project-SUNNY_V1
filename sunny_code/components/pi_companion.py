"""FastAPI router for the Sunny Companion hardware device.

The device (sunny-companion/pi-client/) is a thin client: local wake-word
detection and display only. This is where the actual "brain" work happens --
Vosk STT -> handle_message() -> Piper TTS -- bypassing Discord entirely.
Small JSON state events are interleaved with the audio replies so the
device's animated face can react (thinking/speaking/idle) in step with the
pipeline, instead of just looping a fixed animation blind to what's actually
happening.

Audio format: 16kHz mono 16-bit PCM, sent as raw WebSocket binary frames --
NOT stt.feed()'s 48kHz stereo (that's Discord's format specifically), so
this talks to the Vosk recognizer directly rather than through that wrapper.

Utterance end-of-speech: like voice_worker.py, Vosk's own AcceptWaveform()
endpointing is too slow/unreliable to rely on alone (see stt.feed()'s
docstring) -- the device is expected to do local silence detection and send
an explicit {"type": "utterance_end"} control message, mirroring
voice_session.py's silence watchdog calling stt.finalize().
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sunny_code.components import stt, tts
from sunny_code.components.assistant import handle_message
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.spotify_engine import SpotifyEngine
from sunny_code.components.calendar_engine import CalendarEngine
from sunny_code.components.tasks_engine import TaskEngine

logger = logging.getLogger(__name__)

PostFn = Callable[[str], Awaitable[None]]


class CrashReport(BaseModel):
    """Body for POST /api/pi/crash-report. The device has no Discord
    credentials of its own (kept server-side only, same posture as the
    Anthropic Admin API key -- see sunny-companion/README.md), so it can't
    post to Discord directly the way the main server's own crash notice
    does (see crash_check.py + discord_bot.py). Instead it detects its own
    dirty restart locally (a marker file, same technique) and reports it
    here; this endpoint relays it to the same #warnings channel."""

    device: str
    reason: str


def create_pi_companion_router(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    project_engine: ProjectEngine,
    spotify_engine: SpotifyEngine,
    calendar_engine: CalendarEngine,
    post_to_warnings: Optional[PostFn] = None,
) -> APIRouter:
    """Create the /ws/pi router. Takes the same shared engine instances as
    create_chatbot_router() so a change made from the device stays in sync
    with Discord/console state instead of forking a second copy of them.

    post_to_warnings mirrors main.py's health-check wiring (getattr(self.
    discord_bot, "post_to_health", None)) -- None whenever Discord isn't
    configured, so the crash-report endpoint below still accepts the report
    and logs it locally either way, same fail-open posture as post_to_health
    itself."""
    router = APIRouter()

    @router.post("/api/pi/crash-report")
    async def pi_crash_report(report: CrashReport) -> dict:
        message = f"Sunny Companion device '{report.device}' crashed and restarted. Reason: {report.reason}"
        logger.warning(message)
        if post_to_warnings is not None:
            await post_to_warnings(message)
        return {"ok": True}

    @router.websocket("/ws/pi")
    async def pi_companion_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        recognizer = stt.new_recognizer()
        session_id = "pi:companion"
        logger.info("Pi companion connected")

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                audio_chunk = message.get("bytes")
                if audio_chunk is not None:
                    finalized = _feed_pcm16_mono(recognizer, audio_chunk)
                    if finalized:
                        await _handle_utterance(
                            websocket,
                            finalized,
                            tasks_engine,
                            briefing_engine,
                            list_engine,
                            scheduled_engine,
                            project_engine,
                            spotify_engine,
                            calendar_engine,
                            session_id,
                        )
                    continue

                control_text = message.get("text")
                if control_text is not None:
                    control = json.loads(control_text)
                    if control.get("type") == "utterance_end":
                        finalized = stt.finalize(recognizer)
                        if finalized:
                            await _handle_utterance(
                                websocket,
                                finalized,
                                tasks_engine,
                                briefing_engine,
                                list_engine,
                                scheduled_engine,
                                project_engine,
                                spotify_engine,
                                calendar_engine,
                                session_id,
                            )
        except WebSocketDisconnect:
            pass
        finally:
            logger.info("Pi companion disconnected")

    return router


def _feed_pcm16_mono(recognizer, chunk: bytes) -> Optional[str]:
    """Like stt.feed(), but for the Pi's native 16kHz mono PCM -- stt.feed()
    hardcodes a resample from Discord's 48kHz stereo format, which the Pi
    never produces in the first place (it captures 16kHz mono directly)."""
    if recognizer.AcceptWaveform(chunk):
        result = json.loads(recognizer.Result())
        text = result.get("text", "").strip()
        return text or None
    return None


async def _handle_utterance(
    websocket: WebSocket,
    text: str,
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    project_engine: ProjectEngine,
    spotify_engine: SpotifyEngine,
    calendar_engine: CalendarEngine,
    session_id: str,
) -> None:
    await websocket.send_json({"state": "thinking"})
    chunk_sent = False

    async def on_chunk(sentence: str) -> None:
        nonlocal chunk_sent
        chunk_sent = True
        await _speak(websocket, sentence)

    async def on_search_start() -> None:
        # A distinct state event (not just "thinking") so the device's
        # face can show something more specific for the extra gap a real
        # web search adds -- see llm_client.ask_claude_stream's
        # on_search_start and voice_worker.py's audio equivalent.
        await websocket.send_json({"state": "searching"})

    reply = await handle_message(
        text,
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
    )

    # on_chunk only fires for the LLM Q&A fallback path (see assistant.py) --
    # short-circuit command replies (tasks, lists, etc.) return the full
    # text directly instead, so speak it here if nothing was streamed above.
    if reply and not chunk_sent:
        await _speak(websocket, reply)

    await websocket.send_json({"state": "idle"})


async def _speak(websocket: WebSocket, sentence: str) -> None:
    wav_bytes = await asyncio.to_thread(tts.synthesize_wav_bytes, sentence)
    await websocket.send_json({"state": "speaking"})
    await websocket.send_bytes(wav_bytes)
