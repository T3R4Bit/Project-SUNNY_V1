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

WAKE_WORD_MODEL = "hey_jarvis"  # placeholder -- see module docstring
SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80ms @ 16kHz -- openWakeWord's recommended chunk size
DETECTION_THRESHOLD = 0.5


def listen(on_wake) -> None:
    """Blocks forever, calling on_wake() (no args) on each wake word trigger."""
    model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"audio input status: {status}", file=sys.stderr)
        audio_queue.put(indata[:, 0].copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
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
