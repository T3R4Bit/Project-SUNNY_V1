"""Isolated child process owning /join's entire live voice pipeline —
Discord voice connect, DAVE encrypt/decrypt, Opus decode, Vosk STT,
wake-word detection, chime, Piper TTS playback. Runs as its own OS
process (see sunny_code/components/voice_session.py, the parent-side
coordinator that spawns this via multiprocessing.Process).

Why a separate process: this pipeline crashed the *entire* bot process
repeatedly in one evening (2026-08-20) — native heap-corruption aborts
and segfaults, most root-caused to real bugs (see _patch_dave_decrypt and
_patch_dave_session_locking below) but not all fully explained yet even
after those fixes. davey 0.1.6 and discord-ext-voice-recv 0.5.2-alpha are
both young/unofficial enough that no fix can *prove* no other native
crash trigger exists. Running this in its own OS process means a native
crash here can only end this one /join session — the rest of the bot
(Discord text commands, the web dashboard, tasks, alarms) is
structurally unaffected, a guarantee from real process isolation rather
than another hopeful patch. See sunny-vault/docs/architecture/voice-join.md.

Routing stays in the parent process (handle_message() needs the live
tasks_engine/briefing_engine/list_engine/scheduled_engine objects, which
only exist there) — only recognized command text crosses the process
boundary via the two multiprocessing.Queues passed into run_worker(),
and the spoken-reply text crosses back.
"""

import asyncio
import difflib
import faulthandler
import io
import logging
import math
import queue as queue_module
import struct
import sys
import threading
import time
from typing import Optional

import discord
from discord.ext import voice_recv

from sunny_code.components import stt, tts

# A native crash here (SIGSEGV/SIGABRT) has, every time so far, left
# zero preceding Python-level warning -- nothing raised, nothing logged,
# just gone. faulthandler is the standard tool for exactly this: it
# installs a signal handler that dumps every thread's Python-level stack
# trace to stderr in the instant before a fatal signal actually kills
# the process, which a plain try/except can never do (there's no
# exception to catch). Zero overhead during normal operation -- it only
# does anything at the moment of a fatal signal. This is what should
# finally show *which* thread was doing *what* the next time this
# happens, instead of guessing from silence.
faulthandler.enable(file=sys.stderr, all_threads=True)

logger = logging.getLogger(__name__)

WAKE_WORD = "sunny"
WAKE_MATCH_THRESHOLD = 0.6  # fuzzy match, not exact -- see _strip_wake_phrase
WAKE_SEARCH_WORDS = 4  # how many leading words to scan for the wake word
# No listening window — the wake word is required before every single
# utterance, not just to open a back-and-forth window (that was the
# original 2026-08-20 design; reverted 2026-08-21 per direct request:
# every request needs its own "Hey Sunny").
SILENCE_TIMEOUT = 0.3  # seconds with no incoming audio before forcing Vosk
# to finalize whatever it's buffered — Discord's voice transport doesn't
# send "quiet" packets during real silence, it just stops sending
# anything, so AcceptWaveform()'s own stream-based silence detection can
# never fire on its own; confirmed live, 2026-08-20 (see stt.finalize()).
# Lowered from 1.2s to hit a sub-0.3s post-speech target, 2026-08-21 --
# this is the actual dominant cost in the pipeline's real, live latency
# (measured: ~0.8s of raw Vosk compute per utterance is mostly hidden,
# overlapped with the user still talking; this wait, which only starts
# once they stop, was not). Real tradeoff, not a free win: 0.3s of true
# silence is short enough that a natural mid-sentence pause (a breath,
# an "um", thinking of a word) can plausibly get finalized as the end of
# the utterance. If that starts happening in practice, raise this back
# toward 0.5-0.6s (a more typical "fast" threshold for production voice
# assistants) rather than all the way back to 1.2s.
SILENCE_WATCHDOG_INTERVAL = 0.05  # polling granularity -- kept tight so
# it doesn't stack meaningfully on top of SILENCE_TIMEOUT itself (worst
# case wait is SILENCE_TIMEOUT + this, not just SILENCE_TIMEOUT alone).
# Cheap: a dict iteration + a few time comparisons, 20x/sec is negligible
# CPU cost.
COMMAND_POLL_TIMEOUT = 1.0  # how often command_reader wakes to check for
# shutdown even with no message waiting -- keeps the process from ever
# blocking forever on an empty queue.

_chime_pcm: Optional[bytes] = None
_dave_lock = threading.Lock()  # see _patch_dave_session_locking — the
# actual root cause behind most of the crashes this pipeline has had.
_dave_active = [0]  # temporary overlap-detection instrumentation, see
# _patch_dave_session_locking — should never exceed 1.
_dave_call_guard = threading.Lock()


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
    applied at import time so every worker process gets it automatically,
    without depending on an unofficial fork/branch as a pip dependency.
    See sunny-vault/docs/architecture/voice-join.md."""
    from discord.ext.voice_recv import router as _router_mod

    def _patched_do_run(self):
        while not self._end_thread.is_set():
            self.waiter.wait()
            with self._lock:
                for decoder in self.waiter.items:
                    try:
                        data = decoder.pop_data()
                    except Exception:
                        logger.warning("voice_worker: skipped a corrupted/undecodable audio packet")
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

        # _decode_packet's FEC branch (patched below) reads a packet's
        # decrypted_data straight from the jitter buffer via peek_next(),
        # bypassing _process_packet (and this decrypt call) entirely on
        # the normal path -- so the same packet object can legitimately
        # reach here twice: once early via that FEC peek, once later when
        # it's actually popped and processed for real. DAVE decryption
        # isn't idempotent (it's a real AEAD cipher over a ratcheting
        # key) -- decrypting already-decrypted plaintext a second time
        # produces garbage, not a no-op. Track recently-decrypted
        # sequence numbers per decoder (RTPPacket/FakePacket both use
        # __slots__ with no spare attribute to mark on the packet object
        # itself) and skip the second attempt. Bounded and cleared well
        # before RTP's 16-bit sequence number could ever wrap back
        # around to a value still being tracked.
        seen = getattr(self, "_dave_decrypted_seqs", None)
        if seen is None:
            seen = set()
            self._dave_decrypted_seqs = seen
        if packet.sequence in seen:
            return

        user_id = self._cached_id
        if user_id is None:
            # SSRC not mapped to a user yet — without the sender we can't
            # pick the right ratchet; leave the frame for normal handling.
            return

        if len(seen) > 64:
            seen.clear()
        seen.add(packet.sequence)

        # session.decrypt() itself is thread-safety-locked at the source
        # by _patch_dave_session_locking() below (every native
        # DaveSession method is, not just this one) -- no lock needed
        # here too, and adding one would self-deadlock against it.
        try:
            packet.decrypted_data = session.decrypt(
                int(user_id), _davey.MediaType.audio, bytes(packet.decrypted_data)
            )
        except Exception as e:
            # Expected for passthrough (unencrypted) frames, e.g.
            # keepalive — those arrive as plaintext and fall through
            # unchanged, decoding fine as-is.
            logger.debug(f"voice_worker: DAVE decrypt skipped for ssrc {self.ssrc}: {e}")

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

    def _patched_decode_packet(self, packet):
        assert self._decoder is not None

        if packet:
            pcm = self._decoder.decode(packet.decrypted_data, fec=False)
            return packet, pcm

        # Fake packet (a known single-packet gap) — recover it via Opus
        # FEC data embedded in the *next* buffered packet. That next
        # packet is read straight out of the jitter buffer here, without
        # ever passing through _process_packet/_dave_decrypt above —
        # confirmed live, 2026-08-20: this was still-DAVE-encrypted
        # ciphertext being handed to opus_decode() as if it were real
        # Opus data, on every real packet-loss event. Crashed the whole
        # process (a clean segfault, not the heap-corruption abort from
        # the silence-packet bug) with zero preceding Python-level
        # warning, since nothing here ever raised — libopus was simply
        # reading a native buffer whose declared frame size (from
        # ciphertext bytes it misread as an Opus TOC byte) didn't match
        # its actual contents.
        next_packet = self._buffer.peek_next()

        if next_packet is not None:
            self._dave_decrypt(next_packet)
            nextdata: bytes = next_packet.decrypted_data  # type: ignore

            logger.debug(
                "Generating fec packet: fake=%s, fec=%s",
                packet.sequence,
                next_packet.sequence,
            )
            pcm = self._decoder.decode(nextdata, fec=True)

        # Need to drop a packet
        else:
            pcm = self._decoder.decode(None, fec=False)

        return packet, pcm

    _opus_mod.PacketDecoder._dave_decrypt = _dave_decrypt
    _opus_mod.PacketDecoder._process_packet = _patched_process_packet
    _opus_mod.PacketDecoder._decode_packet = _patched_decode_packet


def _patch_dave_session_locking() -> None:
    """The actual root cause behind all four native crashes this
    pipeline had by the end of 2026-08-20 (two glibc heap-corruption
    aborts, two segfaults — see sunny-vault/docs/architecture/voice-join.md
    for the full history), and — a crucial correction found on the FIFTH
    crash, after an earlier version of this patch only locked
    encrypt/decrypt and still wasn't enough: DaveSession (the `davey`
    package, v0.1.6, a young pre-1.0 third-party Rust extension) is
    touched by far more than just those two calls, all with zero
    internal synchronization anywhere in discord.py or this codebase —
      1. discord.player.AudioPlayer, discord.py's own dedicated
         threading.Thread for outgoing audio, calls
         dave_session.encrypt_opus() for every packet sent.
      2. voice_recv's own packet-processing thread calls
         dave_session.decrypt() for every incoming packet — added
         entirely by _patch_dave_decrypt above; discord.py's own
         official code never calls .decrypt() anywhere, confirmed via
         grep, since voice receive isn't an officially supported
         feature yet.
      3. **The asyncio event loop thread does far more than "manage
         lifecycle"** — confirmed via grep of discord/gateway.py:
         set_external_sender(), process_proposals(), process_commit(),
         and process_welcome() are the actual MLS protocol handlers for
         incoming key-rotation/commit messages from Discord's voice
         gateway, called every time the group's cryptographic state
         updates — which happens periodically during a normal call, not
         just at connect. reinit()/reset()/set_passthrough_mode() in
         discord/voice_state.py run on this same thread. The first
         version of this fix only wrapped encrypt_opus/decrypt and
         missed all of this entirely — confirmed live: a session still
         segfaulted a few seconds in, with zero preceding warning, well
         after that first (incomplete) lock was already deployed.
    Rather than keep enumerating individual call sites scattered across
    two discord.py files (exactly how the FEC-peek bug and now this one
    both slipped through), this locks the shared object itself: every
    real (non-property) method on DaveSession is wrapped to hold
    _dave_lock for its duration, so it is now structurally impossible
    for this native object to be entered by two threads at once,
    regardless of which discord.py code path calls it or whether a
    future discord.py version adds more call sites. Deliberately
    excludes plain attribute reads (ready, status, epoch, ... —
    getset_descriptor in davey.DaveSession's own type, confirmed via
    inspecting the class dict directly, not method_descriptor like the
    real methods below) since those aren't callables and wrapping them
    would break every existing `session.ready`-style read in both
    discord.py and this file."""
    try:
        import davey as _davey
    except ImportError:
        return

    # Rare methods (only fire on real key-rotation/session-lifecycle
    # events, not per-packet) are always worth knowing about by name if
    # they run near a crash -- cheap to log every time, unlike
    # encrypt_opus/decrypt which fire ~50x/sec each.
    _rare_methods = {
        "process_commit", "process_proposals", "process_welcome",
        "set_external_sender", "reinit", "reset", "set_passthrough_mode",
    }

    for name, attr in list(vars(_davey.DaveSession).items()):
        if name.startswith("_") or type(attr).__name__ != "method_descriptor":
            continue

        def _make_locked(original, method_name):
            def _locked(self, *args, **kwargs):
                if method_name in _rare_methods:
                    logger.info(f"voice_worker: DaveSession.{method_name}() starting (thread={threading.get_ident()})")
                # Overlap detector: proves (or disproves) that the lock
                # is actually excluding concurrent entry in the real,
                # deployed process -- not just in an isolated local test.
                # Should never fire; if it does, that's the smoking gun
                # this whole investigation has been missing.
                with _dave_call_guard:
                    _dave_active[0] += 1
                    if _dave_active[0] > 1:
                        logger.critical(
                            f"voice_worker: DAVE LOCK OVERLAP DETECTED calling {method_name} "
                            f"(active={_dave_active[0]}, thread={threading.get_ident()})"
                        )
                try:
                    with _dave_lock:
                        return original(self, *args, **kwargs)
                finally:
                    with _dave_call_guard:
                        _dave_active[0] -= 1
                    if method_name in _rare_methods:
                        logger.info(f"voice_worker: DaveSession.{method_name}() finished")

            return _locked

        setattr(_davey.DaveSession, name, _make_locked(attr, name))


_patch_voice_recv_packet_router()
_patch_dave_decrypt()
_patch_dave_session_locking()


def run_worker(to_worker, from_worker, token: str, guild_id: int, channel_id: int) -> None:
    """Entry point for the isolated child process — see voice_session.py's
    start(), which spawns this via multiprocessing.Process(target=
    run_worker, ...). Blocks for the lifetime of one /join session: until
    a "leave" command arrives from the parent, the voice connection ends
    on Discord's side, or (the entire point of running this in its own
    process) a native crash kills this process outright, which the parent
    detects from the outside via the process's exit code — never anything
    this function itself needs to handle."""
    try:
        asyncio.run(_async_main(to_worker, from_worker, token, guild_id, channel_id))
    except Exception as e:
        logger.error(f"voice_worker: fatal error: {e}")
        try:
            from_worker.put({"type": "join_failed", "reason": str(e)})
        except Exception:
            pass


async def _async_main(to_worker, from_worker, token: str, guild_id: int, channel_id: int) -> None:
    loop = asyncio.get_running_loop()
    intents = discord.Intents.default()  # matches discord_bot.py's main
    # client exactly (plus message_content there, irrelevant here) — the
    # existing /join already resolves speaking members fine on this
    # intent set in the single-process design, so there's no new risk in
    # reusing it for this second, voice-only client.
    client = discord.Client(intents=intents)

    voice_client: Optional[voice_recv.VoiceRecvClient] = None
    recognizers = {}  # user_id -> {"rec": KaldiRecognizer, "chimed": bool, "pending": bool}
    stop_event = asyncio.Event()

    async def play_wake_chime():
        if voice_client is None or not voice_client.is_connected():
            return
        logger.info(f"voice_worker: playing wake chime (thread={threading.get_ident()})")
        try:
            if voice_client.is_playing():
                voice_client.stop()
            voice_client.play(discord.PCMAudio(io.BytesIO(_get_chime_pcm())))
        except Exception as e:
            logger.error(f"voice_worker: chime playback failed: {e}")
        logger.info("voice_worker: wake chime play() call returned")

    async def handle_utterance(user, text, already_chimed=False):
        t_heard = time.monotonic()
        logger.info(f"voice_worker: heard from {user}: {text!r}")

        command = _strip_wake_phrase(text)
        if command is None:
            logger.info("voice_worker: ignored (no wake word)")
            return
        if not already_chimed:
            await play_wake_chime()

        if not command:
            # Wake word alone, nothing after it yet — nothing to do. The
            # *next* utterance needs its own wake word too, same as this one.
            return

        from_worker.put({
            "type": "utterance",
            "user_id": user.id,
            "user_name": str(user),
            "text": command,
            "t_heard": t_heard,
        })

    async def speak(text: str) -> None:
        if voice_client is None or not voice_client.is_connected():
            return
        try:
            pcm = await asyncio.to_thread(tts.synthesize_discord_pcm, text)
        except Exception as e:
            logger.error(f"voice_worker: TTS synthesis failed: {e}")
            return
        try:
            if voice_client.is_playing():
                voice_client.stop()
            voice_client.play(discord.PCMAudio(io.BytesIO(pcm)))
        except Exception as e:
            logger.error(f"voice_worker: response playback failed: {e}")
            return

    def on_audio(user, data):
        """Sync callback — fires on voice_recv's own audio-decode thread,
        off the asyncio event loop (confirmed via the library's own
        source: this callback cannot be a coroutine). Never awaits
        directly; hands off to the loop via run_coroutine_threadsafe.

        Checks Vosk's in-progress partial hypothesis for the wake word
        and fires the chime immediately on a match, rather than waiting
        for the segment to fully finalize (AcceptWaveform() returning
        True needs real trailing silence — see silence_watchdog below for
        why that alone isn't enough)."""
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
                        logger.info(
                            f"voice_worker: wake word matched in partial {partial_text!r}, "
                            f"scheduling chime (thread={threading.get_ident()})"
                        )
                        asyncio.run_coroutine_threadsafe(play_wake_chime(), loop)
                return
            state["pending"] = False
            already_chimed = state["chimed"]
            state["chimed"] = False  # reset for the next utterance
        except Exception as e:
            logger.error(f"voice_worker: STT feed failed for {user}: {e}")
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
        utterance signal instead, and force-finalizes via stt.finalize().
        Also doubles as the loop that notices the voice connection
        itself ending (Discord-side disconnect/kick, not a /leave
        command) and signals shutdown either way."""
        while voice_client is not None and voice_client.is_connected():
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
                    logger.error(f"voice_worker: forced finalize failed: {e}")
                    continue
                if text:
                    already_chimed = state["chimed"]
                    state["chimed"] = False
                    await handle_utterance(state["user"], text, already_chimed)
        stop_event.set()

    async def command_reader():
        """Relays "speak"/"leave" commands from the parent. Polls with a
        timeout rather than blocking forever on the queue so this task
        (and the process) can always notice stop_event being set some
        other way (e.g. silence_watchdog noticing a Discord-side
        disconnect) instead of leaking a thread blocked on an empty
        queue for the rest of the process's life."""
        while not stop_event.is_set():
            try:
                msg = await asyncio.to_thread(to_worker.get, True, COMMAND_POLL_TIMEOUT)
            except queue_module.Empty:
                continue
            msg_type = msg.get("type")
            if msg_type == "speak":
                await speak(msg["text"])
            elif msg_type == "leave":
                stop_event.set()

    @client.event
    async def on_ready():
        nonlocal voice_client
        guild = client.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild is not None else None
        if channel is None:
            from_worker.put({"type": "join_failed", "reason": "voice channel not found"})
            stop_event.set()
            return

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
            logger.error(f"voice_worker: failed to connect to {channel}: {e}")
            from_worker.put({"type": "join_failed", "reason": "couldn't join — check permissions or try again"})
            stop_event.set()
            return

        try:
            new_client.listen(voice_recv.BasicSink(on_audio))
        except Exception as e:
            logger.error(f"voice_worker: connected but failed to start listening: {e}")
            try:
                await new_client.disconnect()
            except Exception:
                pass
            from_worker.put({"type": "join_failed", "reason": "joined but couldn't start listening"})
            stop_event.set()
            return

        voice_client = new_client
        logger.info(f"voice_worker: joined #{channel.name} ({channel.id})")
        asyncio.create_task(silence_watchdog())
        asyncio.create_task(command_reader())

        try:
            await warm_task  # make sure the model's actually ready before returning
        except Exception as e:
            logger.error(f"voice_worker: Vosk pre-warm failed (will retry lazily): {e}")

        from_worker.put({"type": "joined", "channel_name": channel.name})

    client_task = asyncio.create_task(client.start(token))
    stop_wait_task = asyncio.create_task(stop_event.wait())
    done, _pending = await asyncio.wait({client_task, stop_wait_task}, return_when=asyncio.FIRST_COMPLETED)

    if client_task in done and not stop_event.is_set():
        # client.start() ended on its own (a login failure, or some other
        # fatal gateway error) before on_ready ever got a chance to
        # report success or failure itself -- nothing else will report
        # this, so do it here. Confirmed live during testing, 2026-08-20:
        # without this, a bad/rejected token left the whole worker
        # process hanging forever on stop_event.wait(), since
        # client.start() was only ever awaited as a background task
        # whose exception nothing was watching for.
        exc = client_task.exception() if client_task.done() else None
        reason = str(exc) if exc else "Discord connection ended unexpectedly"
        logger.error(f"voice_worker: client.start() ended early: {reason}")
        from_worker.put({"type": "join_failed", "reason": reason})
        stop_event.set()

    if not stop_wait_task.done():
        stop_wait_task.cancel()

    if voice_client is not None:
        try:
            await voice_client.disconnect()
        except Exception as e:
            logger.error(f"voice_worker: error disconnecting: {e}")
    try:
        await client.close()
    except Exception:
        pass
    from_worker.put({"type": "left"})

    if not client_task.done():
        try:
            await asyncio.wait_for(client_task, timeout=5)
        except Exception:
            pass
