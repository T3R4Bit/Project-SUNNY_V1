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
import re
import subprocess
import sys
import threading

import numpy as np
from openwakeword.model import Model
from scipy.signal import decimate

# Match the mic by name substring, not a hardcoded ALSA card index -- USB
# enumeration order can shift across reboots (other USB devices, hub order),
# which is exactly the risk BUILD_PLAN.md's Phase 3 flags.
MIC_NAME_HINT = "USB PnP Sound Device"


def _resolve_alsa_device() -> str:
    """Returns an ALSA device string like 'hw:2,0' for the mic, by name.

    Validated on real Pi 3B hardware (2026-08-28): capture goes through
    `arecord` directly (see _capture_thread below), not sounddevice/
    PortAudio -- PortAudio's ALSA backend was dropping frames continuously
    ("input overflow" on nearly every callback) even with a callback doing
    zero work, while plain `arecord` at the same rate ran gapless for 8s+.
    This looks like a PortAudio<->ALSA period/buffer negotiation bug
    specific to this device, not a real-time CPU or USB bandwidth problem
    (ruled out separately). `arecord -l`'s raw hw device is what was proven
    reliable, so that's what gets used here instead of chasing PortAudio's
    stream parameters further.
    """
    output = subprocess.run(["arecord", "-l"], capture_output=True, text=True, check=True).stdout
    for line in output.splitlines():
        m = re.match(r"card (\d+): .*\[(.*?)\].*device (\d+):", line)
        if m and MIC_NAME_HINT in m.group(2):
            return f"hw:{m.group(1)},{m.group(3)}"
    raise RuntimeError(f"No ALSA capture device matching {MIC_NAME_HINT!r} found in `arecord -l`")


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


def _capture_thread(
    device: str,
    audio_queue: "queue.Queue[np.ndarray]",
    stop_event: threading.Event,
) -> None:
    """Reads raw PCM from `arecord` and pushes native-rate int16 chunks onto the queue."""
    chunk_bytes = NATIVE_FRAME_SAMPLES * 2  # int16 = 2 bytes/sample
    proc = subprocess.Popen(
        [
            "arecord", "-D", device, "-f", "S16_LE", "-r", str(NATIVE_SAMPLE_RATE),
            "-c", "1", "-t", "raw", "-q", "-",
        ],
        stdout=subprocess.PIPE,
    )
    try:
        while not stop_event.is_set():
            raw = proc.stdout.read(chunk_bytes)
            if len(raw) < chunk_bytes:
                print("arecord capture ended unexpectedly", file=sys.stderr)
                break
            audio_queue.put(np.frombuffer(raw, dtype=np.int16).copy())
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def listen(on_wake) -> None:
    """Blocks forever, calling on_wake() (no args) on each wake word trigger."""
    # ncpu=2: openWakeWord's own default (ncpu=1, single-threaded ONNX
    # sessions) measured at ~70ms/block on real Pi 3B hardware (2026-08-28)
    # -- 87.5% of the 80ms budget. ncpu=2 measured at ~44ms/block: parallelizing
    # across 2 of the Pi's 4 cores is faster than 1, while still leaving 2 cores
    # free (unlike ncpu=4/"auto", which measured *slower* at ~58ms -- likely
    # thread-contention overhead on this many-core-but-slow-per-core ARM chip).
    model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx", ncpu=2)
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()
    stop_event = threading.Event()

    device = _resolve_alsa_device()
    threading.Thread(
        target=_capture_thread, args=(device, audio_queue, stop_event), daemon=True
    ).start()

    print(f"Listening for '{WAKE_WORD_MODEL}' via {device}... (Ctrl+C to stop)")
    triggered = False
    try:
        while True:
            raw = audio_queue.get()
            while not audio_queue.empty():
                raw = audio_queue.get_nowait()  # drop backlog, keep only the newest

            downsampled = decimate(raw, DECIMATION_FACTOR, ftype="fir")
            boosted = np.clip(downsampled.astype(np.int32) * MIC_GAIN, -32768, 32767)
            scores = model.predict(boosted.astype(np.int16))
            score = scores[WAKE_WORD_MODEL]

            if score > DETECTION_THRESHOLD and not triggered:
                triggered = True
                on_wake()
            elif score <= DETECTION_THRESHOLD:
                triggered = False
    finally:
        stop_event.set()


if __name__ == "__main__":

    def _print_detection():
        print(">>> wake word detected <<<")

    listen(_print_detection)
