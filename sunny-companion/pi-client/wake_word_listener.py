"""Local wake-word listener prototype (Phase 5).

Continuously listens on the default microphone at low CPU cost and calls
`on_wake()` whenever the wake word's score crosses the threshold. This is
the "always listening" front end that lets the device avoid running full
STT locally -- only after a detection should real audio get streamed to
the server's /ws/pi endpoint (sunny_code/components/pi_companion.py), which
is not wired up here yet; this script only proves the local trigger works.

Placeholder wake word: no pretrained "hey sunny" model exists yet.
openWakeWord ships a handful of pretrained wake words (alexa, hey_mycroft,
hey_jarvis, hey_rhasspy) but nothing custom -- training one requires
generating synthetic speech data via openWakeWord's own training notebooks
(https://github.com/dscripka/openWakeWord#training-new-models), which is
real, separate follow-up work. This uses "hey_jarvis" as a stand-in so the
actual mechanism (continuous low-compute local listening -> trigger) can
be tested with a real voice right now; swap WAKE_WORD_MODEL once a real
"hey sunny" model is trained.

Verified so far (silence/noise smoke test, not a live voice test): the
model loads, processes real int16 audio frames, and stays near-zero on
non-speech input. Actually saying the wake word out loud to confirm
detection needs a live run -- that's on whoever runs this script.
"""

from __future__ import annotations

import queue
import sys

import numpy as np
import sounddevice as sd
from openwakeword.model import Model
from scipy.signal import decimate

# Match the mic by name substring, not a hardcoded PortAudio/ALSA index --
# USB enumeration order can shift across reboots (other USB devices, hub
# order), which is exactly the risk BUILD_PLAN.md's Phase 3 flags.
MIC_NAME_HINT = "USB PnP Sound Device"


def _resolve_mic_device() -> int:
    for i, dev in enumerate(sd.query_devices()):
        if MIC_NAME_HINT in dev["name"] and dev["max_input_channels"] > 0:
            return i
    raise RuntimeError(f"No input device matching {MIC_NAME_HINT!r} found")


WAKE_WORD_MODEL = "hey_jarvis"  # placeholder -- see module docstring
SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80ms @ 16kHz -- openWakeWord's recommended chunk size
DETECTION_THRESHOLD = 0.5

# Validated on real Pi 3B hardware (2026-08-28): the SunFounder USB mic's raw
# ALSA hw device only supports 44100/48000 Hz, not the 16kHz openWakeWord
# needs (opening the stream at 16kHz directly fails outright, PaErrorCode
# -9997 "Invalid sample rate"). ALSA's "plug" conversion layer would fix this
# for command-line tools like `arecord -D plughw:...`, but sounddevice/
# PortAudio's device matching only sees the raw "hw:X,Y" nodes it enumerates,
# not arbitrary plughw device strings -- so capture at the mic's native rate
# and downsample to 16kHz here instead. 48000 is an exact 3x multiple of
# 16000, so decimate(..., 3) is a clean, anti-aliased downsample with no
# resampling artifacts from a non-integer ratio.
NATIVE_SAMPLE_RATE = 48000
DECIMATION_FACTOR = NATIVE_SAMPLE_RATE // SAMPLE_RATE
NATIVE_FRAME_SAMPLES = FRAME_SAMPLES * DECIMATION_FACTOR

# Validated on real Pi 3B hardware with the SunFounder USB mic (2026-08-28):
# even with ALSA capture gain maxed out (amixer -c <card> sset Mic 16, the
# top of its 0-16 range), close-range voice peaks ~18x quieter than the same
# mic's response to a physical tap on the capsule -- the capsule itself is
# fine, it's just acoustically insensitive. 8x digital gain brought a
# barely-audible recording up to clear with zero sample clipping.
MIC_GAIN = 8


def listen(on_wake) -> None:
    """Blocks forever, calling on_wake() (no args) on each wake word trigger."""
    model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"audio input status: {status}", file=sys.stderr)
        downsampled = decimate(indata[:, 0], DECIMATION_FACTOR, ftype="fir")
        boosted = np.clip(downsampled.astype(np.int32) * MIC_GAIN, -32768, 32767)
        audio_queue.put(boosted.astype(np.int16))

    with sd.InputStream(
        device=_resolve_mic_device(),
        samplerate=NATIVE_SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=NATIVE_FRAME_SAMPLES,
        callback=audio_callback,
    ):
        print(f"Listening for '{WAKE_WORD_MODEL}'... (Ctrl+C to stop)")
        triggered = False
        while True:
            frame = audio_queue.get()
            scores = model.predict(frame)
            score = scores[WAKE_WORD_MODEL]

            if score > DETECTION_THRESHOLD and not triggered:
                triggered = True
                on_wake()
            elif score <= DETECTION_THRESHOLD:
                triggered = False


if __name__ == "__main__":

    def _print_detection():
        print(">>> wake word detected <<<")

    listen(_print_detection)
