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
import math
import struct
import time
from typing import Optional

import discord
from discord.ext import voice_recv

from sunny_code.components import stt, tts
from sunny_code.components.assistant import handle_message

logger = logging.getLogger(__name__)

WAKE_PHRASES = ("hey sunny", "hello sunny", "sunny")
WAKE_WINDOW_SECONDS = 20  # how long a session stays "awake" after a wake
# word or a response, before requiring the wake word again — matches the
# "opens a window, doesn't need repeating every sentence" choice made
# 2026-08-20 (a real back-and-forth, not a walkie-talkie).

_chime_pcm: Optional[bytes] = None


def _strip_wake_phrase(text: str) -> Optional[str]:
    """None if `text` doesn't start with a wake phrase. Otherwise the
    remaining command text with the phrase stripped — "" if it was just
    the wake word alone with nothing after it yet."""
    lowered = text.lower().strip()
    for phrase in WAKE_PHRASES:
        if lowered == phrase:
            return ""
        if lowered.startswith(phrase + " "):
            return text[len(phrase):].strip()
    return None


def _get_chime_pcm() -> bytes:
    """A short two-tone ascending chime (~200ms), played the instant the
    wake word is heard — the same "I heard you" confirmation an Alexa/
    Google Home gives, so there's audible feedback even before a spoken
    reply is ready. Generated on the fly (a couple sine waves), not a
    shipped audio file — no asset/licensing question, no new dependency.
    Cached after the first call; the maths is cheap but there's no reason
    to redo it every wake word."""
    global _chime_pcm
    if _chime_pcm is not None:
        return _chime_pcm

    from discord.opus import Encoder as OpusEncoder

    rate = 48000
    notes = [(880, 0.09), (1318, 0.11)]  # A5 then E6 — a short rising "ding"
    fade_samples = int(rate * 0.01)  # 10ms fade in/out per note, avoids clicks
    frames = bytearray()
    for freq, duration in notes:
        n = int(rate * duration)
        for i in range(n):
            fade = min(i / fade_samples, (n - i) / fade_samples, 1.0)
            value = math.sin(2 * math.pi * freq * i / rate) * fade * 0.3
            sample = int(value * 32767)
            frames += struct.pack("<hh", sample, sample)  # mono value -> stereo frame

    pad = (-len(frames)) % OpusEncoder.FRAME_SIZE
    if pad:
        frames += b"\x00" * pad

    _chime_pcm = bytes(frames)
    return _chime_pcm


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


def _disable_dave() -> None:
    """Force discord.py to negotiate classic (pre-DAVE) voice encryption
    instead of Discord's newer end-to-end DAVE protocol. Whether DAVE gets
    used is decided entirely client-side, by whether the `davey` package
    is importable (see discord/voice_state.py's `has_dave` and
    `max_dave_protocol_version`, and gateway.py, which sends that value
    straight to Discord as part of the voice-connect handshake).

    discord-ext-voice-recv's decode path predates DAVE and can't decrypt
    DAVE-encrypted frames before handing them to the Opus decoder — with
    DAVE active, every single incoming packet failed with "corrupted
    stream" (confirmed live, 2026-08-20 — not occasional loss, 100% of
    packets). `davey` only got installed in the first place as part of
    `discord.py[voice]` while fixing a separate libopus issue.

    Uninstalling the `davey` package doesn't stick: discord-ext-voice-recv
    itself declares `discord.py[voice]>=2.5` as its own dependency, so any
    full `pip install -r requirements.txt` (which run.sh does on every
    start) reinstalls it regardless of what this project's own
    requirements.txt says. This patches the actual flag discord.py checks
    instead — robust regardless of whether davey happens to be
    importable. See sunny-vault/docs/architecture/voice-join.md."""
    import discord.voice_state as _voice_state_mod

    _voice_state_mod.has_dave = False


_patch_voice_recv_packet_router()
_disable_dave()

_voice_client: Optional[voice_recv.VoiceRecvClient] = None
_awake_until: float = 0.0


def is_active() -> bool:
    return _voice_client is not None


async def start(interaction, tasks_engine, briefing_engine, list_engine, scheduled_engine) -> str:
    """Joins the invoking user's current voice channel and starts
    listening. Fails with an honest message (not a crash) if the user
    isn't in a channel, a session is already active, or the connect
    itself fails (missing permissions, etc.)."""
    global _voice_client, _awake_until

    if is_active():
        return "Already in a voice call — use /leave first."

    voice_state = getattr(interaction.user, "voice", None)
    if voice_state is None or voice_state.channel is None:
        return "You need to be in a voice channel first."

    channel = voice_state.channel
    loop = asyncio.get_running_loop()
    recognizers = {}  # user_id -> KaldiRecognizer, one per speaker this session

    async def handle_utterance(user, text):
        global _awake_until

        logger.info(f"voice_session: heard from {user}: {text!r}")
        if _voice_client is None or not _voice_client.is_connected():
            return

        now = time.monotonic()
        stripped = _strip_wake_phrase(text)
        if stripped is not None:
            command = stripped
            _awake_until = now + WAKE_WINDOW_SECONDS
            try:
                if _voice_client.is_playing():
                    _voice_client.stop()
                _voice_client.play(discord.PCMAudio(io.BytesIO(_get_chime_pcm())))
            except Exception as e:
                logger.error(f"voice_session: chime playback failed: {e}")
        elif now < _awake_until:
            command = text
        else:
            logger.info("voice_session: ignored (no wake word, outside listening window)")
            return

        if not command:
            # Wake word alone, nothing after it yet — stay armed, wait for
            # the actual command on a later utterance.
            return

        session_id = f"voice:{channel.guild.id}:{user.id}"
        try:
            response = await handle_message(
                command, tasks_engine, briefing_engine, list_engine, scheduled_engine, session_id=session_id
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
        _awake_until = time.monotonic() + WAKE_WINDOW_SECONDS  # extend the window after responding

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

    _awake_until = 0.0
    try:
        _voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
    except Exception as e:
        logger.error(f"voice_session: failed to connect to {channel}: {e}")
        return "Couldn't join that voice channel — check my permissions."

    _voice_client.listen(voice_recv.BasicSink(on_audio))
    logger.info(f"voice_session: joined #{channel.name} ({channel.id})")
    return f'Joined {channel.name} — say "Hey Sunny" to start.'


async def stop() -> str:
    """Disconnects and clears session state. Safe to call even if nothing
    is active."""
    global _voice_client, _awake_until

    if not is_active():
        return "Not in a voice call."

    voice_client = _voice_client
    _voice_client = None
    _awake_until = 0.0
    try:
        await voice_client.disconnect()
    except Exception as e:
        logger.error(f"voice_session: error disconnecting: {e}")
    return "Left the voice call."
