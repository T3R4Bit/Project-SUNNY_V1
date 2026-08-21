"""Live voice-channel conversation: /join has the bot join the caller's
voice channel and listen; speech gets transcribed (stt.py, Vosk), routed
through the exact same assistant.handle_message() every other interface
uses, and the response is spoken back (tts.py, Piper). /leave ends it.

One session at a time, module-global state — mirrors this app's existing
single-guild assumption (see discord-bot.md) and tts.py's singleton
pattern. See sunny-vault/docs/architecture/voice-join.md.
"""

import asyncio
import difflib
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

WAKE_WORD = "sunny"
WAKE_MATCH_THRESHOLD = 0.6  # fuzzy match, not exact -- see _strip_wake_phrase
WAKE_SEARCH_WORDS = 4  # how many leading words to scan for the wake word
WAKE_WINDOW_SECONDS = 20  # how long a session stays "awake" after a wake
# word or a response, before requiring the wake word again — matches the
# "opens a window, doesn't need repeating every sentence" choice made
# 2026-08-20 (a real back-and-forth, not a walkie-talkie).
SILENCE_TIMEOUT = 1.2  # seconds with no incoming audio before forcing Vosk
# to finalize whatever it's buffered — Discord's voice transport doesn't
# send "quiet" packets during real silence, it just stops sending
# anything, so AcceptWaveform()'s own stream-based silence detection can
# never fire on its own; confirmed live, 2026-08-20 (see stt.finalize()).
SILENCE_WATCHDOG_INTERVAL = 0.3

_chime_pcm: Optional[bytes] = None


def _strip_wake_phrase(text: str) -> Optional[str]:
    """None if no word among the first few looks close enough to "sunny".
    Fuzzy, not exact — Vosk's small model reliably mis-hears "Hey Sunny"
    ("the sunny it up", "a sony what's the one", plain "sonny"/"sun"),
    confirmed against real /join transcripts on 2026-08-20; an exact
    prefix match meant the wake word essentially never fired for real
    speech. Doesn't require "hey"/"hello" to also match — Vosk garbles
    that lead-in unpredictably ("the", "a") in every real example seen,
    so the wake word itself, wherever it lands in the first few words,
    is the one reliable anchor. Returns the remaining command text after
    the matched word — "" if nothing follows yet."""
    words = text.split()
    for i, word in enumerate(words[:WAKE_SEARCH_WORDS]):
        cleaned = word.lower().strip(".,!?\"'")
        if difflib.SequenceMatcher(None, cleaned, WAKE_WORD).ratio() >= WAKE_MATCH_THRESHOLD:
            return " ".join(words[i + 1:]).strip()
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


def _patch_dave_decrypt() -> None:
    """DAVE (Discord's end-to-end voice encryption) became mandatory
    platform-wide in March 2026 — no server setting, no opt-out. A client
    without DAVE support gets flatly refused at connect time with voice
    close code 4017 ("this channel requires DAVE") — confirmed live,
    2026-08-20, after an earlier version of this patch tried disabling
    DAVE client-side to fix the "corrupted stream on every packet" issue
    below; that made /join fail to connect at all instead. DAVE has to
    stay on — `davey` must stay installed.

    That leaves the real problem: discord-ext-voice-recv 0.5.2a179 (the
    PyPI release) hands Opus-decode raw MLS ciphertext without decrypting
    it first, since it predates DAVE — every real voice frame decodes as
    "corrupted stream". No PyPI release fixes this, but there's a real,
    working fix: PR #58 on the project's GitHub (open, unmerged as of
    2026-08-20 — the author reports it's been running 24/7 in a
    production voice bot). Verified by installing that exact fork/branch
    locally and reading the real installed source via
    inspect.getsource() — not a summarized diff — then replicated here
    faithfully as a patch, same reasoning as the PacketRouter patch
    above: don't depend on an unofficial personal fork as a pip
    dependency for something this central.

    Decrypts each inbound frame with discord.py's own DaveSession
    (already maintained for the sending side) before Opus ever sees it.
    See sunny-vault/docs/architecture/voice-join.md."""
    try:
        import davey as _davey
    except ImportError:
        _davey = None

    from discord.ext.voice_recv import opus as _opus_mod

    def _dave_decrypt(self, packet) -> None:
        if _davey is None or not packet or not packet.decrypted_data:
            return
        if packet.is_silence():
            # Discord sends its own literal Opus-silence marker
            # (b'\xf8\xff\xfe', see rtp.py's OPUS_SILENCE) as a plain,
            # deliberately unencrypted RTPPacket regardless of DAVE state
            # — confirmed via voice_recv's own reader.py, which checks
            # is_silence() for an unrelated reason (dropping silence from
            # unmapped ssrcs) but proves these packets flow through the
            # exact same pipeline as real audio, reaching here too.
            # Feeding that 3-byte non-ciphertext buffer into
            # DaveSession.decrypt() -- which expects real MLS-framed
            # ciphertext, far longer than 3 bytes -- crashed the entire
            # process (glibc "free(): invalid size" / "free(): invalid
            # pointer", full abort), confirmed live 2026-08-20 in a burst
            # right as a speaker stopped talking, exactly when Discord
            # clients emit these. Skipping decrypt here leaves
            # decrypted_data as the real, valid, already-plaintext-by-
            # design silence bytes, which the Opus decoder handles fine
            # on its own -- no decryption was ever needed for these.
            return

        state = getattr(self.sink.voice_client, "_connection", None)
        session = getattr(state, "dave_session", None)
        if session is None or not session.ready or getattr(state, "dave_protocol_version", 0) == 0:
            return

        user_id = self._cached_id
        if user_id is None:
            # SSRC not mapped to a user yet — without the sender we can't
            # pick the right ratchet; leave the frame for normal handling.
            return

        try:
            packet.decrypted_data = session.decrypt(
                int(user_id), _davey.MediaType.audio, bytes(packet.decrypted_data)
            )
        except Exception as e:
            # Expected for passthrough (unencrypted) frames, e.g. silence/
            # keepalive — those arrive as plaintext and fall through
            # unchanged, decoding fine as-is.
            logger.debug(f"voice_session: DAVE decrypt skipped for ssrc {self.ssrc}: {e}")

    def _patched_process_packet(self, packet):
        pcm = None
        member = self._get_cached_member()
        if member is None:
            self._cached_id = self.sink.voice_client._get_id_from_ssrc(self.ssrc)
            member = self._get_cached_member()

        self._dave_decrypt(packet)

        if not self.sink.wants_opus():
            packet, pcm = self._decode_packet(packet)

        data = _opus_mod.VoiceData(packet, member, pcm=pcm)
        self._last_seq = packet.sequence
        self._last_ts = packet.timestamp
        return data

    _opus_mod.PacketDecoder._dave_decrypt = _dave_decrypt
    _opus_mod.PacketDecoder._process_packet = _patched_process_packet


_patch_voice_recv_packet_router()
_patch_dave_decrypt()

_voice_client: Optional[voice_recv.VoiceRecvClient] = None
_awake_until: float = 0.0
_connecting: bool = False  # guards the window between "checked is_active()"
# and "_voice_client actually assigned" — channel.connect()'s own retry loop
# can take 25+ seconds (5 attempts, increasing backoff) before returning, and
# is_active() alone doesn't catch a second /join fired during that window.


def is_active() -> bool:
    return _voice_client is not None


async def start(interaction, tasks_engine, briefing_engine, list_engine, scheduled_engine) -> str:
    """Joins the invoking user's current voice channel and starts
    listening. Fails with an honest message (not a crash) if the user
    isn't in a channel, a session (or connection attempt) is already in
    progress, or the connect/listen sequence itself fails (missing
    permissions, Discord voice server issues, etc.) — always returns a
    string, never lets an exception escape to the caller, since an
    uncaught exception here leaves Discord's "thinking..." indicator
    stuck forever (confirmed live, 2026-08-20: this exact gap left a
    real /join stuck when the connect "succeeded" but the connection
    wasn't actually usable and .listen() then raised)."""
    global _voice_client, _awake_until, _connecting

    if is_active():
        return "Already in a voice call — use /leave first."
    if _connecting:
        return "Already joining a voice call — give it a moment."

    voice_state = getattr(interaction.user, "voice", None)
    if voice_state is None or voice_state.channel is None:
        return "You need to be in a voice channel first."

    channel = voice_state.channel
    loop = asyncio.get_running_loop()
    recognizers = {}  # user_id -> {"rec": KaldiRecognizer, "chimed": bool}, one per speaker this session

    async def play_wake_chime():
        """Standalone so it can fire both from a fast partial-result match
        (on_audio, below) and from handle_utterance's own final-text check
        — whichever notices the wake word first."""
        if _voice_client is None or not _voice_client.is_connected():
            return
        try:
            if _voice_client.is_playing():
                _voice_client.stop()
            _voice_client.play(discord.PCMAudio(io.BytesIO(_get_chime_pcm())))
        except Exception as e:
            logger.error(f"voice_session: chime playback failed: {e}")

    async def handle_utterance(user, text, already_chimed=False):
        global _awake_until

        t_heard = time.monotonic()
        logger.info(f"voice_session: heard from {user}: {text!r}")
        if _voice_client is None or not _voice_client.is_connected():
            return

        now = time.monotonic()
        stripped = _strip_wake_phrase(text)
        if stripped is not None:
            command = stripped
            _awake_until = now + WAKE_WINDOW_SECONDS
            if not already_chimed:
                await play_wake_chime()
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
        t_route_start = time.monotonic()
        try:
            response = await handle_message(
                command, tasks_engine, briefing_engine, list_engine, scheduled_engine, session_id=session_id
            )
        except Exception as e:
            logger.error(f"voice_session: assistant router failed: {e}")
            return
        t_route_done = time.monotonic()
        if not response:
            return
        try:
            pcm = await asyncio.to_thread(tts.synthesize_discord_pcm, response)
        except Exception as e:
            logger.error(f"voice_session: TTS synthesis failed: {e}")
            return
        t_tts_done = time.monotonic()
        if _voice_client is None or not _voice_client.is_connected():
            return
        try:
            if _voice_client.is_playing():
                _voice_client.stop()
            _voice_client.play(discord.PCMAudio(io.BytesIO(pcm)))
        except Exception as e:
            logger.error(f"voice_session: response playback failed: {e}")
            return
        _awake_until = time.monotonic() + WAKE_WINDOW_SECONDS  # extend the window after responding
        logger.info(
            "voice_session: timing — route={:.2f}s tts={:.2f}s total(heard→playing)={:.2f}s".format(
                t_route_done - t_route_start, t_tts_done - t_route_done, time.monotonic() - t_heard
            )
        )

    def on_audio(user, data):
        """Sync callback — fires on voice_recv's own audio-decode thread,
        off the asyncio event loop (confirmed via the library's own
        source: this callback cannot be a coroutine). Never awaits
        directly; hands off to the loop via run_coroutine_threadsafe.

        Checks Vosk's in-progress partial hypothesis for the wake word
        and fires the chime immediately on a match, rather than waiting
        for the segment to fully finalize (AcceptWaveform() returning
        True needs real trailing silence — see the silence_watchdog
        coroutine below for why that alone isn't enough)."""
        if user is None or user.bot or not data.pcm:
            return
        try:
            state = recognizers.get(user.id)
            if state is None:
                state = {"rec": stt.new_recognizer(), "chimed": False, "pending": False}
                recognizers[user.id] = state
            state["user"] = user
            state["last_packet_at"] = time.monotonic()
            rec = state["rec"]

            text = stt.feed(rec, data.pcm)
            if text is None:
                state["pending"] = True  # there's buffered audio Vosk hasn't finalized yet
                if not state["chimed"]:
                    partial_text = stt.partial(rec)
                    if partial_text and _strip_wake_phrase(partial_text) is not None:
                        state["chimed"] = True
                        asyncio.run_coroutine_threadsafe(play_wake_chime(), loop)
                return
            state["pending"] = False
            already_chimed = state["chimed"]
            state["chimed"] = False  # reset for the next utterance
        except Exception as e:
            logger.error(f"voice_session: STT feed failed for {user}: {e}")
            return
        asyncio.run_coroutine_threadsafe(handle_utterance(user, text, already_chimed), loop)

    async def silence_watchdog():
        """Discord's voice transport doesn't send "quiet" audio packets
        during real silence, it just stops sending anything — so
        AcceptWaveform() may never return True on its own once someone
        stops talking (confirmed live, 2026-08-20: a real session never
        finalized a single utterance across 50+ seconds after the first
        sentence, because there was simply no more audio arriving to
        eventually trigger Vosk's internal silence detection). This polls
        for "no new packets in SILENCE_TIMEOUT" as the actual end-of-
        utterance signal instead, and force-finalizes via stt.finalize()."""
        while _voice_client is not None and _voice_client.is_connected():
            await asyncio.sleep(SILENCE_WATCHDOG_INTERVAL)
            now = time.monotonic()
            for state in list(recognizers.values()):
                if not state.get("pending"):
                    continue
                if now - state.get("last_packet_at", now) < SILENCE_TIMEOUT:
                    continue
                state["pending"] = False
                try:
                    text = stt.finalize(state["rec"])
                except Exception as e:
                    logger.error(f"voice_session: forced finalize failed: {e}")
                    continue
                if text:
                    already_chimed = state["chimed"]
                    state["chimed"] = False
                    await handle_utterance(state["user"], text, already_chimed)

    _awake_until = 0.0
    _connecting = True
    try:
        # Pre-warm the Vosk model in parallel with connecting, so it's
        # already loaded by the time real audio starts flowing — otherwise
        # the model load (a real, multi-second cost the first time this
        # process does it) happens lazily inside on_audio's sync callback,
        # blocking voice_recv's own audio-decode thread and delaying/
        # dropping whatever's said first.
        warm_task = asyncio.create_task(asyncio.to_thread(stt.new_recognizer))

        try:
            new_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        except Exception as e:
            logger.error(f"voice_session: failed to connect to {channel}: {e}")
            return "Couldn't join that voice channel — check my permissions, or Discord's voice servers may be having issues."

        try:
            new_client.listen(voice_recv.BasicSink(on_audio))
        except Exception as e:
            logger.error(f"voice_session: connected but failed to start listening: {e}")
            try:
                await new_client.disconnect()
            except Exception:
                pass
            return "Joined but couldn't start listening — try /join again."

        _voice_client = new_client
        logger.info(f"voice_session: joined #{channel.name} ({channel.id})")
        asyncio.create_task(silence_watchdog())

        try:
            await warm_task  # make sure the model's actually ready before returning
        except Exception as e:
            logger.error(f"voice_session: Vosk pre-warm failed (will retry lazily): {e}")

        return f'Joined {channel.name} — say "Hey Sunny" to start.'
    finally:
        _connecting = False


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
