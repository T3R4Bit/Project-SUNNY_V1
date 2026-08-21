"""Live voice-channel conversation: /join has the bot join the caller's
voice channel and listen; speech gets transcribed (stt.py, Vosk), routed
through the exact same assistant.handle_message() every other interface
uses, and the response is spoken back (tts.py, Piper). /leave ends it.

One session at a time, module-global state — mirrors this app's existing
single-guild assumption (see discord-bot.md) and tts.py's singleton
pattern. See sunny-vault/docs/architecture/voice-join.md.
"""

import asyncio
import io
import logging
from typing import Optional

import discord
from discord.ext import voice_recv

from sunny_code.components import stt, tts
from sunny_code.components.assistant import handle_message

logger = logging.getLogger(__name__)


def _patch_voice_recv_packet_router() -> None:
    """discord-ext-voice-recv 0.5.2a179 has a real, unreleased-fix bug:
    PacketRouter._do_run() lets ANY single decode error (a corrupted or
    lost packet — routine on real UDP voice traffic, not a sign of an
    actual problem) propagate out of its loop entirely; PacketRouter.run()
    then calls voice_client.stop_listening() in a finally block, silently
    and permanently ending the whole /join session after the very first
    bad packet. Confirmed live on 2026-08-20 — a real user's first /join
    test went unresponsive after exactly one `OpusError: corrupted stream`.
    No PyPI release fixes this yet; there's a matching *open, unmerged*
    upstream PR (#57, "catch OpusError in PacketRouter to prevent thread
    crash") — this patches the exact same one method the same way,
    applied at import time so every voice_session.py caller gets it
    automatically, without depending on an unofficial fork/branch as a
    pip dependency. See sunny-vault/docs/architecture/voice-join.md."""
    from discord.ext.voice_recv import router as _router_mod

    def _patched_do_run(self):
        while not self._end_thread.is_set():
            self.waiter.wait()
            with self._lock:
                for decoder in self.waiter.items:
                    try:
                        data = decoder.pop_data()
                    except Exception:
                        logger.warning("voice_session: skipped a corrupted/undecodable audio packet")
                        continue
                    if data is not None:
                        self.sink.write(data.source, data)

    _router_mod.PacketRouter._do_run = _patched_do_run


_patch_voice_recv_packet_router()

_voice_client: Optional[voice_recv.VoiceRecvClient] = None


def is_active() -> bool:
    return _voice_client is not None


async def start(interaction, tasks_engine, briefing_engine, list_engine, scheduled_engine) -> str:
    """Joins the invoking user's current voice channel and starts
    listening. Fails with an honest message (not a crash) if the user
    isn't in a channel, a session is already active, or the connect
    itself fails (missing permissions, etc.)."""
    global _voice_client

    if is_active():
        return "Already in a voice call — use /leave first."

    voice_state = getattr(interaction.user, "voice", None)
    if voice_state is None or voice_state.channel is None:
        return "You need to be in a voice channel first."

    channel = voice_state.channel
    loop = asyncio.get_running_loop()
    recognizers = {}  # user_id -> KaldiRecognizer, one per speaker this session

    async def handle_utterance(user, text):
        logger.info(f"voice_session: heard from {user}: {text!r}")
        if _voice_client is None or not _voice_client.is_connected():
            return
        session_id = f"voice:{channel.guild.id}:{user.id}"
        try:
            response = await handle_message(
                text, tasks_engine, briefing_engine, list_engine, scheduled_engine, session_id=session_id
            )
        except Exception as e:
            logger.error(f"voice_session: assistant router failed: {e}")
            return
        if not response:
            return
        try:
            pcm = await asyncio.to_thread(tts.synthesize_discord_pcm, response)
        except Exception as e:
            logger.error(f"voice_session: TTS synthesis failed: {e}")
            return
        if _voice_client is None or not _voice_client.is_connected():
            return
        if _voice_client.is_playing():
            _voice_client.stop()
        _voice_client.play(discord.PCMAudio(io.BytesIO(pcm)))

    def on_audio(user, data):
        """Sync callback — fires on voice_recv's own audio-decode thread,
        off the asyncio event loop (confirmed via the library's own
        source: this callback cannot be a coroutine). Never awaits
        directly; hands off to the loop via run_coroutine_threadsafe."""
        if user is None or user.bot or not data.pcm:
            return
        try:
            rec = recognizers.get(user.id)
            if rec is None:
                rec = stt.new_recognizer()
                recognizers[user.id] = rec
            text = stt.feed(rec, data.pcm)
        except Exception as e:
            logger.error(f"voice_session: STT feed failed for {user}: {e}")
            return
        if text:
            asyncio.run_coroutine_threadsafe(handle_utterance(user, text), loop)

    try:
        _voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
    except Exception as e:
        logger.error(f"voice_session: failed to connect to {channel}: {e}")
        return "Couldn't join that voice channel — check my permissions."

    _voice_client.listen(voice_recv.BasicSink(on_audio))
    logger.info(f"voice_session: joined #{channel.name} ({channel.id})")
    return f"Joined {channel.name} — go ahead and talk."


async def stop() -> str:
    """Disconnects and clears session state. Safe to call even if nothing
    is active."""
    global _voice_client

    if not is_active():
        return "Not in a voice call."

    voice_client = _voice_client
    _voice_client = None
    try:
        await voice_client.disconnect()
    except Exception as e:
        logger.error(f"voice_session: error disconnecting: {e}")
    return "Left the voice call."
