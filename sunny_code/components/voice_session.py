"""Live voice-channel conversation: /join spawns an isolated child
process (sunny_code/voice_worker.py) that owns the entire real-time
audio pipeline — Discord voice connect, DAVE encrypt/decrypt, Opus
decode, Vosk STT, wake-word detection, chime, Piper TTS playback —
communicating over two multiprocessing.Queues. /leave ends it.

Why a separate process, not a function call in this one: this pipeline
crashed the *entire* bot process four separate times in one evening
(2026-08-20) — two distinct native heap-corruption aborts, two distinct
segfaults. The verified root cause (a data race on DaveSession, called
from multiple OS threads with zero synchronization anywhere in
discord.py or this codebase) is now fixed — see voice_worker.py's
_patch_dave_encrypt_lock(). But davey 0.1.6 and discord-ext-voice-recv
0.5.2-alpha are both young/unofficial enough that no fix here can
*prove* no other native crash trigger exists. Running the pipeline in
its own OS process means a crash there can only end that one /join
session — the rest of the bot (Discord text commands, the web
dashboard, tasks, alarms) is structurally unaffected, a guarantee from
real process isolation rather than another hopeful patch. See
sunny-vault/docs/architecture/voice-join.md.

Routing stays here in the parent (handle_message() needs the live
tasks_engine/briefing_engine/list_engine/scheduled_engine objects, which
only exist here) — only recognized command text crosses into the
worker's process boundary, and the spoken-reply text crosses back out.

One session at a time, module-global state — mirrors this app's existing
single-guild assumption (see discord-bot.md) and tts.py's singleton
pattern.
"""

import asyncio
import logging
import multiprocessing
import queue as queue_module
from typing import Awaitable, Callable, Optional

from sunny_code.components.assistant import handle_message
from sunny_code.config import get_settings
from sunny_code.voice_worker import run_worker

logger = logging.getLogger(__name__)

JOIN_TIMEOUT = 30  # seconds to wait for the worker's own "joined"/
# "join_failed" signal before giving up -- generous relative to a normal
# ~1-2s connect, since a first-ever run also has to download the Vosk
# model (a few seconds even on a fast connection).
QUEUE_POLL_TIMEOUT = 1.0
LEAVE_GRACE_SECONDS = 5.0

_worker: Optional[multiprocessing.Process] = None
_to_worker: Optional["multiprocessing.Queue"] = None
_connecting: bool = False  # guards the window between "checked is_active()"
# and "_worker actually assigned" — spawning + connecting can take a real
# few seconds, and is_active() alone doesn't catch a second /join fired
# during that window.
_stopping: bool = False  # True only while stop() is intentionally tearing
# the worker down -- lets _watch_worker tell an expected exit from a
# crash apart.


def is_active() -> bool:
    return _worker is not None and _worker.is_alive()


async def start(
    interaction,
    tasks_engine,
    briefing_engine,
    list_engine,
    scheduled_engine,
    project_engine,
    spotify_engine,
    calendar_engine,
    notify_fn: Optional[Callable[[str], Awaitable[None]]] = None,
) -> str:
    """Joins the invoking user's current voice channel by spawning an
    isolated worker process and starts relaying between it and the
    shared assistant router. Fails with an honest message (not a crash)
    if the user isn't in a channel, a session (or connection attempt) is
    already in progress, or the worker itself fails to join — always
    returns a string, never lets an exception escape to the caller.

    notify_fn, if given, is called with a short message if the worker
    later dies unexpectedly (a crash) — this is how a mid-session native
    crash still becomes visible in Discord without taking the rest of
    the bot down with it (contrast crash_check.py, which only learns
    about a whole-process crash on the *next* startup — this parent is
    alive the whole time a /join session runs and finds out instantly)."""
    global _worker, _to_worker, _connecting

    if is_active():
        return "Already in a voice call — use /leave first."
    if _connecting:
        return "Already joining a voice call — give it a moment."

    voice_state = getattr(interaction.user, "voice", None)
    if voice_state is None or voice_state.channel is None:
        return "You need to be in a voice channel first."

    channel = voice_state.channel
    settings = get_settings()

    to_worker: multiprocessing.Queue = multiprocessing.Queue()
    from_worker: multiprocessing.Queue = multiprocessing.Queue()

    _connecting = True
    try:
        process = multiprocessing.Process(
            target=run_worker,
            args=(to_worker, from_worker, settings.discord_bot_token, channel.guild.id, channel.id),
            daemon=True,  # never outlives the parent bot process
        )
        process.start()

        try:
            msg = await asyncio.wait_for(asyncio.to_thread(from_worker.get), timeout=JOIN_TIMEOUT)
        except asyncio.TimeoutError:
            process.terminate()
            return "Joining timed out — try /join again."

        if msg.get("type") != "joined":
            process.terminate()
            reason = msg.get("reason", "unknown error")
            return f"Couldn't join that voice channel: {reason}"

        _worker = process
        _to_worker = to_worker
        asyncio.create_task(
            _relay_from_worker(
                process, from_worker, to_worker, tasks_engine, briefing_engine, list_engine,
                scheduled_engine, project_engine, spotify_engine, calendar_engine
            )
        )
        asyncio.create_task(_watch_worker(process, notify_fn))

        return f'Joined {msg.get("channel_name", channel.name)} — say "Hey Sunny" to start.'
    finally:
        _connecting = False


async def _relay_from_worker(
    process, from_worker, to_worker, tasks_engine, briefing_engine, list_engine, scheduled_engine, project_engine,
    spotify_engine, calendar_engine,
) -> None:
    """Reads utterance events from the worker for the lifetime of one
    /join session, routes each through the same handle_message() every
    other interface uses, and sends the reply back for the worker to
    speak. Exits once the worker reports it left, or dies. Polls with a
    timeout rather than blocking forever on the queue, so a dead worker
    doesn't leave this parked on an empty queue for good — this task
    itself must never be the thing that crashes the parent, so every
    step is wrapped defensively."""
    while process.is_alive():
        try:
            msg = await asyncio.to_thread(from_worker.get, True, QUEUE_POLL_TIMEOUT)
        except queue_module.Empty:
            continue
        except Exception as e:
            logger.error(f"voice_session: reading from worker failed, ending relay: {e}")
            return

        msg_type = msg.get("type")
        if msg_type == "left":
            return
        if msg_type != "utterance":
            continue

        session_id = f"voice:{msg['user_id']}"
        generation = msg.get("generation")
        streamed_any = False

        async def on_chunk(sentence: str) -> None:
            # Freshly rebound every loop iteration (this closure captures
            # the CURRENT to_worker/streamed_any/generation, not a stale
            # one from an earlier utterance) -- see handle_message()'s
            # on_chunk contract in assistant.py/briefing.py: called only
            # when routing falls through to the LLM Q&A fallback, one
            # sentence at a time, as Claude generates them. Lets the
            # worker start speaking the first sentence immediately
            # instead of waiting for the whole reply -- the real latency
            # win from ask_claude_stream(), see the 2026-08-21 latency
            # chart. generation is echoed straight back from the
            # "utterance" message so the worker's barge-in logic
            # (play_wake_chime()) can tell this chunk apart from a reply
            # to a request that's since been talked over.
            nonlocal streamed_any
            streamed_any = True
            try:
                to_worker.put({"type": "speak_chunk", "text": sentence, "generation": generation})
            except Exception as e:
                logger.error(f"voice_session: failed to relay chunk to worker: {e}")

        async def on_search_start() -> None:
            # Fires the instant Claude starts a web search (see
            # llm_client.ask_claude_stream) -- a real, otherwise-unexplained
            # extra gap on top of the LLM's own thinking time. Same
            # generation-tagging as on_chunk, so a stale search cue from an
            # already-barged-in-on request gets dropped by the worker
            # instead of playing over whatever's current.
            try:
                to_worker.put({"type": "searching", "generation": generation})
            except Exception as e:
                logger.error(f"voice_session: failed to relay search cue to worker: {e}")

        try:
            response = await handle_message(
                msg["text"],
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
        except Exception as e:
            logger.error(f"voice_session: assistant router failed: {e}")
            continue

        if streamed_any:
            # Already fully delivered sentence-by-sentence above -- don't
            # also send the complete response as a second, redundant
            # "speak", just tell the worker no more chunks are coming so
            # it knows to stop waiting and finish playback.
            try:
                to_worker.put({"type": "speak_chunk_done"})
            except Exception as e:
                logger.error(f"voice_session: failed to signal stream end to worker: {e}")
            continue

        if not response:
            continue
        try:
            to_worker.put({"type": "speak", "text": response, "generation": generation})
        except Exception as e:
            logger.error(f"voice_session: failed to relay response to worker: {e}")


async def _watch_worker(process, notify_fn: Optional[Callable[[str], Awaitable[None]]]) -> None:
    """Waits for the worker process to actually exit and, if that wasn't
    because stop() intentionally tore it down, treats it as a crash: logs
    it and reports it via notify_fn right away. This is the sole caller
    of process.join() for a given worker — stop() below only ever polls
    the cheap, safe-from-multiple-callers is_alive()/terminate(), so two
    places never race to reap the same process. Always clears session
    state either way, so /join works again immediately whether this was
    a clean /leave or a crash."""
    global _worker, _to_worker, _stopping

    await asyncio.to_thread(process.join)

    was_intentional = _stopping
    if process is _worker:
        _worker = None
        _to_worker = None
    _stopping = False

    if was_intentional:
        return

    exitcode = process.exitcode
    logger.warning(f"voice_session: worker process ended unexpectedly (exitcode={exitcode})")
    if notify_fn is not None:
        try:
            await notify_fn(
                f"Voice session ended unexpectedly (worker crashed, exit code {exitcode}) — try /join again."
            )
        except Exception as e:
            logger.error(f"voice_session: failed to send crash notice: {e}")


async def stop() -> str:
    """Tells the worker to leave and waits briefly for it to exit
    cleanly, force-terminating if it doesn't. Safe to call even if
    nothing is active."""
    global _stopping

    if not is_active():
        return "Not in a voice call."

    _stopping = True
    process = _worker
    to_worker = _to_worker
    try:
        if to_worker is not None:
            to_worker.put({"type": "leave"})
    except Exception as e:
        logger.error(f"voice_session: failed to send leave command: {e}")

    elapsed = 0.0
    step = 0.25
    while process.is_alive() and elapsed < LEAVE_GRACE_SECONDS:
        await asyncio.sleep(step)
        elapsed += step

    if process.is_alive():
        logger.warning("voice_session: worker didn't exit after leave, terminating")
        process.terminate()

    return "Left the voice call."
