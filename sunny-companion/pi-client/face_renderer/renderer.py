"""Face renderer prototype (Phase 4) -- standalone dev-machine demo.

Pygame, drawn straight to the display via SDL2 -- no browser, no image
assets, just a filled circle whose radius reacts to a live `amplitude`
value. This is the "does the rendering technique even work" step: prove
the shape + amplitude + hue-overlay approach runs smoothly before touching
real Pi 3 B hardware (Phase 4's own validation step) or wiring it to the
device client / server state events (Phase 4.5, separate work).

State machine matches what pi_companion.py actually emits over /ws/pi
(idle/thinking/searching/speaking, see sunny_code/components/pi_companion.py)
plus "listening", which is local-only and fires before any server
round-trip (see wake_word_listener.py). Not wired to that WebSocket here --
this file only proves the renderer standalone; Phase 4.5 does the wiring.

Amplitude sources, one per state, matching BUILD_PLAN.md Phase 4:
  - listening -- real mic RMS (sounddevice), same approach wake_word_listener.py uses
  - thinking / searching -- synthesized "breathing" (two detuned low-frequency
    sines summed), since there's no real audio to react to yet
  - speaking -- real TTS playback buffer RMS is the eventual source (Phase 4.5),
    not available standalone; mic RMS stands in here so the render path is
    exercised the same way it will be for real later

Run: pip install -r ../requirements.txt, then `python renderer.py`.
Keys: 1-5 switch state (idle/listening/thinking/searching/speaking),
e cycles the emotion-overlay hue (stub for the not-yet-built server-side
mood tag -- see README.md's "Emotion overlay (v2)"), Esc/Q quits.

On the Pi, SDL_VIDEODRIVER=kmsdrm gets set in the environment (not here --
that's Pi-specific and would break the dev-machine window) so pygame draws
straight to the framebuffer with no X11/Wayland compositor, matching the
no-compositor approach Phase 2 already proved out for the (now-abandoned)
browser-based renderer.
"""

from __future__ import annotations

import colorsys
import math
import sys
import time
from typing import Callable

import numpy as np
import pygame
import sounddevice as sd

SAMPLE_RATE = 16000
MIC_BLOCK_SAMPLES = 512  # 32ms @ 16kHz -- small enough to feel live

WINDOW_SIZE = (480, 480)
BASE_RADIUS = 80
MAX_RADIUS_BOOST = 140

STATES = ["idle", "listening", "thinking", "searching", "speaking"]

# hue in [0, 1); "neutral" is Sunny's base color, others are the emotion-overlay stub
EMOTIONS = {
    "neutral": 0.11,  # warm gold
    "happy": 0.14,  # brighter yellow
    "concerned": 0.58,  # cool blue
    "playful": 0.86,  # pink/magenta
    "apologetic": 0.62,  # muted blue-grey
}
EMOTION_ORDER = list(EMOTIONS)


class MicAmplitude:
    """Live mic RMS, normalized to roughly [0, 1] for typical speech levels."""

    def __init__(self) -> None:
        self._level = 0.0
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=MIC_BLOCK_SAMPLES,
            callback=self._on_audio,
        )
        self._stream.start()

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"mic input status: {status}", file=sys.stderr)
        samples = indata[:, 0].astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(samples**2)))
        self._level = min(1.0, rms * 6.0)  # typical speech RMS is well under 1/6 full scale

    def __call__(self) -> float:
        return self._level

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class BreathingAmplitude:
    """Synthesized idle motion -- two detuned low-frequency sines, summed."""

    def __init__(self, base_hz: float = 0.18, detune_hz: float = 0.05, level: float = 0.35) -> None:
        self._base_hz = base_hz
        self._detune_hz = detune_hz
        self._level = level
        self._start = time.monotonic()

    def __call__(self) -> float:
        t = time.monotonic() - self._start
        wave = math.sin(2 * math.pi * self._base_hz * t) + math.sin(
            2 * math.pi * (self._base_hz + self._detune_hz) * t
        )
        return self._level * (wave + 2) / 4  # normalize the [-2, 2] sum into [0, 1]


class ZeroAmplitude:
    def __call__(self) -> float:
        return 0.0


def _hue_to_rgb(hue: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Sunny face renderer prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)

    mic = MicAmplitude()
    sources: dict[str, Callable[[], float]] = {
        "idle": ZeroAmplitude(),
        "listening": mic,
        "thinking": BreathingAmplitude(),
        "searching": BreathingAmplitude(base_hz=0.32, detune_hz=0.09, level=0.45),
        "speaking": mic,  # stand-in for the real TTS playback buffer RMS (Phase 4.5)
    }

    state = "idle"
    emotion = "neutral"
    running = True
    frame_times: list[float] = []

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif pygame.K_1 <= event.key <= pygame.K_5:
                        state = STATES[event.key - pygame.K_1]
                    elif event.key == pygame.K_e:
                        emotion = EMOTION_ORDER[(EMOTION_ORDER.index(emotion) + 1) % len(EMOTION_ORDER)]

            amplitude = sources[state]()
            radius = int(BASE_RADIUS + amplitude * MAX_RADIUS_BOOST)
            color = _hue_to_rgb(EMOTIONS[emotion])

            screen.fill((18, 18, 24))
            pygame.draw.circle(screen, color, (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2), radius)

            frame_times.append(clock.get_time())
            if len(frame_times) > 60:
                frame_times.pop(0)
            avg_frame_ms = sum(frame_times) / len(frame_times) if frame_times else 0.0
            fps = 1000.0 / avg_frame_ms if avg_frame_ms else 0.0

            hud = f"state={state}  emotion={emotion}  amp={amplitude:.2f}  fps={fps:.0f}"
            screen.blit(font.render(hud, True, (200, 200, 200)), (10, 10))
            screen.blit(
                font.render("1-5 state  e emotion  esc quit", True, (120, 120, 120)),
                (10, WINDOW_SIZE[1] - 24),
            )

            pygame.display.flip()
            clock.tick(60)
    finally:
        mic.close()
        pygame.quit()


if __name__ == "__main__":
    main()
