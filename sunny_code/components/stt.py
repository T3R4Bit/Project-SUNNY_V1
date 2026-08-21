"""Speech-to-text via Vosk (https://alphacephei.com/vosk/) — free, fully
local, no per-call API cost. Feeds live Discord voice audio into a
per-session KaldiRecognizer; Vosk handles utterance-boundary detection
internally (AcceptWaveform() returns True when a segment finalizes), so
no custom silence-timeout logic is needed here.

See sunny-vault/docs/architecture/voice-join.md.
"""

import audioop
import json
import logging
import os
import threading
import time
from typing import Optional

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()  # new_recognizer() can be called concurrently
# (the /join pre-warm task and voice_recv's own audio-decode thread both call
# it) — without this, both could see _model is None at once and each build a
# separate Model, which is exactly what happened the first time this ran live
# (two "Vosk model ready" log lines, back to back).

DISCORD_SAMPLE_RATE = 48000
VOSK_SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit PCM, both Discord and Vosk


def _get_model():
    """Lazily loads and caches the Vosk Model for the process lifetime —
    same "load once, cache in a module global" idea as tts.py's PiperVoice
    cache. Model(lang=...) auto-downloads if not already in
    settings.vosk_model_dir (confirmed via reading vosk.Model's own source
    — no custom download step needed here, unlike Piper)."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            settings = get_settings()
            settings.vosk_model_dir.mkdir(parents=True, exist_ok=True)
            os.environ["VOSK_MODEL_PATH"] = str(settings.vosk_model_dir)

            from vosk import Model, SetLogLevel

            SetLogLevel(-1)  # Vosk's own C-level logging is noisy; this app has its own
            logger.info(f"Loading Vosk model (lang={settings.vosk_lang}), downloading if needed...")
            t0 = time.monotonic()
            _model = Model(lang=settings.vosk_lang)
            logger.info(f"Vosk model ready in {time.monotonic() - t0:.2f}s")
    return _model


def new_recognizer():
    """A fresh recognizer for one listening session (e.g. one speaker in a
    /join call). Blocking on first-ever call only (model load/download) —
    callers on an event loop should run this via asyncio.to_thread. Keep
    feeding the same recognizer instance across multiple audio chunks —
    Vosk handles segmenting one utterance from the next internally, no
    need to create a new one per utterance."""
    from vosk import KaldiRecognizer

    model = _get_model()
    return KaldiRecognizer(model, VOSK_SAMPLE_RATE)


def resample_to_16k_mono(pcm_48k_stereo: bytes) -> bytes:
    """Discord's receive format (48kHz stereo 16-bit) -> Vosk's expected
    format (16kHz mono 16-bit). Resample state isn't carried across calls
    (fresh per chunk) — a minor discontinuity at chunk boundaries, judged
    fine for speech recognition given Discord audio is already lossy
    Opus-decoded speech; revisit with stateful resampling if accuracy
    ever seems to suffer from it."""
    mono = audioop.tomono(pcm_48k_stereo, SAMPLE_WIDTH, 0.5, 0.5)
    resampled, _ = audioop.ratecv(mono, SAMPLE_WIDTH, 1, DISCORD_SAMPLE_RATE, VOSK_SAMPLE_RATE, None)
    return resampled


def feed(recognizer, pcm_48k_stereo_chunk: bytes) -> Optional[str]:
    """Resamples and feeds one chunk of raw Discord PCM into `recognizer`.
    Returns the finalized transcript text once Vosk's own silence-based
    endpointing completes a segment, else None (still buffering — caller
    just keeps calling this with the same recognizer as more audio
    arrives). Empty/silent segments resolve to None too, not "".

    Finalizing a segment this way is slow in practice — confirmed live,
    2026-08-20: multiple seconds between one utterance finishing and the
    next being "heard", well past the ~2s the actual response pipeline
    (route+TTS+play) takes once text is in hand. Vosk's simple Python API
    doesn't expose a tunable endpoint/silence-timeout (checked directly:
    KaldiRecognizer has no such method), so that finalization delay can't
    be shortened here — see partial() below for the actual mitigation
    (early wake-word detection from in-progress hypotheses, not waiting
    on this)."""
    chunk = resample_to_16k_mono(pcm_48k_stereo_chunk)
    if recognizer.AcceptWaveform(chunk):
        result = json.loads(recognizer.Result())
        text = result.get("text", "").strip()
        return text or None
    return None


def partial(recognizer) -> str:
    """The recognizer's current in-progress hypothesis — updates fast,
    well before AcceptWaveform() finalizes a segment. Cheap: just reads
    the decoder's current best guess, no new decode work. Used for early
    wake-word detection (play the confirmation chime as soon as "sunny"
    is heard, without waiting for the whole utterance — including the
    trailing silence Vosk wants — to finish)."""
    return json.loads(recognizer.PartialResult()).get("partial", "").strip()


def finalize(recognizer) -> Optional[str]:
    """Forces whatever's been buffered so far to finalize, without
    feeding more audio. Needed because AcceptWaveform() may never return
    True on its own: Discord's voice transport doesn't send "quiet" audio
    packets during real silence, it simply stops sending packets — so
    Vosk's own stream-based silence detection never sees the silence it
    needs to finalize (confirmed live, 2026-08-20: a real session never
    finalized a single utterance across 50+ seconds once the speaker
    paused after their first sentence). voice_session.py's silence
    watchdog calls this once no new packets have arrived for a while,
    using the *absence* of packets as the actual end-of-utterance signal
    instead."""
    result = json.loads(recognizer.FinalResult())
    text = result.get("text", "").strip()
    return text or None
