"""Persistent voice-channel presence: start() spawns an isolated child
process (sunny_code/voice_worker.py) that owns the entire real-time
audio pipeline — Discord voice connect, DAVE encrypt/decrypt, Opus
decode, Vosk STT, wake-word detection, chime, Piper TTS playback —
communicating over two multiprocessing.Queues. stop() ends it.

Not triggered by a slash command -- discord_bot.py's voice-presence loop
calls start()/stop() based on DISCORD_VOICE_CHANNEL_ID being configured
and the "voice_join" service being enabled (service_registry.py),
reconnecting automatically after a drop or a crash. "Hey Sunny" is still
required before each request once connected -- this only removes the
per-use /join, not the wake-word gate. See sunny-vault/docs/architecture/
voice-join.md.

Why a separate process, not a function call in this one: this pipeline
crashed the *entire* bot process four separate times in one evening
(2026-08-20) — two distinct native heap-corruption aborts, two distinct
segfaults. The verified root cause (a data race on DaveSession, called
from multiple OS threads with zero synchronization anywhere in
discord.py or this codebase) is now fixed — see voice_worker.py's
_patch_dave_encrypt_lock(). But davey 0.1.6 and discord-ext-voice-recv
0.5.2-alpha are both young/unofficial enough that no fix here can
*prove* no other native crash trigger exists. Running the pipeline in
its own OS process means a crash there can only end that one voice
session — the rest of the bot (Discord text commands, the web
dashboard, tasks, alarms) is structurally unaffected, a guarantee from
real process isolation rather than another hopeful patch.

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
    channel,
    tasks_engine,
    briefing_engine,
    list_engine,
    scheduled_engine,
    project_engine,
    spotify_engine,
    calendar_engine,
    notify_fn: Optional[Callable[[str], Awaitable[None]]] = None,
) -> str:
    """Joins `channel` (a discord.VoiceChannel) by spawning an isolated
    worker process and starts relaying between it and the shared assistant
    router. Fails with an honest message (not a crash) if a session (or
    connection attempt) is already in progress, or the worker itself fails
    to join — always returns a string, never lets an exception escape to
    the caller. Caller resolves `channel` itself (see discord_bot.py's
    voice-presence loop) -- this module has no Discord-interaction
    dependency, since nothing here is triggered by a slash command anymore
    (voice presence is persistent, driven by DISCORD_VOICE_CHANNEL_ID +
    the "voice_join" service toggle, not a per-use /join).

    notify_fn, if given, is called with a short message if the worker
    later dies unexpectedly (a crash) — this is how a mid-session native
    crash still becomes visible in Discord without taking the rest of
    the bot down with it (contrast crash_check.py, which only learns
    about a whole-process crash on the *next* startup — this parent is
    alive the whole time a session runs and finds out instantly). The
    voice-presence loop notices is_active() went False on its next tick
    and reconnects automatically -- no manual action needed after a crash."""
    global _worker, _to_worker, _connecting

    if is_active():
        return "Already in a voice call."
    if _connecting:
        return "Already joining a voice call — give it a moment."

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
            _close_queues(to_worker, from_worker)
            return "Joining timed out — will retry automatically."

        if msg.get("type") != "joined":
            process.terminate()
            reason = msg.get("reason", "unknown error")
            _close_queues(to_worker, from_worker)
            return f"Couldn't join that voice channel: {reason}"

        _worker = process
        _to_worker = to_worker
        relay_task = asyncio.create_task(
            _relay_from_worker(
                process, from_worker, to_worker, tasks_engine, briefing_engine, list_engine,
                scheduled_engine, project_engine, spotify_engine, calendar_engine
            )
        )
        asyncio.create_task(_watch_worker(process, from_worker, to_worker, relay_task, notify_fn))

        return f'Joined {msg.get("channel_name", channel.name)} — say "Hey Sunny" to start.'
    finally:
        _connecting = False


def _close_queues(*queues: "multiprocessing.Queue") -> None:
    """Releases the pipe fds and semaphore locks backing each queue.
    Without this, every start() call (successful or not) leaks a
    semaphore + pipe pair that outlives the queue's Python references --
    over enough reconnect attempts (voice_presence_loop retries every
    30s) this exhausts the process's open-file limit and takes down
    unrelated background tasks with OSError: Too many open files
    (see incident 2026-09-01)."""
    for q in queues:
        try:
            q.close()
            q.join_thread()
        except Exception as e:
            logger.error(f"voice_session: failed to close queue: {e}")


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


async def _watch_worker(
    process, from_worker, to_worker, relay_task: "asyncio.Task",
    notify_fn: Optional[Callable[[str], Awaitable[None]]],
) -> None:
    """Waits for the worker process to actually exit and, if that wasn't
    because stop() intentionally tore it down, treats it as a crash: logs
    it and reports it via notify_fn right away. This is the sole caller
    of process.join() for a given worker — stop() below only ever polls
    the cheap, safe-from-multiple-callers is_alive()/terminate(), so two
    places never race to reap the same process. Always clears session
    state either way, so the voice-presence loop's next tick can
    reconnect immediately whether this was an intentional stop() or a
    crash.

    Also the sole closer of this session's queues, once relay_task (the
    only other thing touching them) has had its own chance to notice the
    process is gone and stop reading -- closing out from under a live
    read risks tripping up the read instead of just ending it cleanly.
    Skipping this close is what leaked a semaphore + pipe pair per
    session and eventually exhausted the process's open-file limit (see
    incident 2026-09-01)."""
    global _worker, _to_worker, _stopping

    await asyncio.to_thread(process.join)

    was_intentional = _stopping
    if process is _worker:
        _worker = None
        _to_worker = None
    _stopping = False

    try:
        await relay_task
    except Exception:
        pass
    _close_queues(to_worker, from_worker)

    if was_intentional:
        return

    exitcode = process.exitcode
    logger.warning(f"voice_session: worker process ended unexpectedly (exitcode={exitcode})")
    if notify_fn is not None:
        try:
            await notify_fn(
                f"Voice session ended unexpectedly (worker crashed, exit code {exitcode}) — reconnecting automatically."
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
