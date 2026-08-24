"""Manual dev-only demo: plays real Piper-synthesized speech and drives the
"speaking" state from the actual TTS playback buffer's RMS, instead of the
mic standing in for it (renderer.py's default -- there's no real TTS audio
in the standalone prototype, since real TTS-on-the-device wiring is Phase
4.5's job, streamed from the server over the network, not local synthesis
like this).

This deliberately imports sunny_code.components.tts, from OUTSIDE the
pi-client package -- fine for a same-machine manual test tool, but this
script itself never ships to the Pi (not referenced by Dockerfile.test or
requirements.txt) and renderer.py itself stays Pi-appropriate/import-light.
Needs a couple of packages beyond pi-client/requirements.txt in this venv:
piper-tts, pydantic, pydantic-settings (sunny_code.config's dependencies) --
deliberately not added to requirements.txt itself, since that file is what
ships to the Pi and has no reason to carry server-side deps for a dev tool
that never runs there.

Run: python sunny-companion/pi-client/face_renderer/tts_demo.py

Keys: same as renderer.py (1-5 state, e emotion, esc/q quit), plus:
    t -- synthesize and speak a random test phrase, auto-switches to
         "speaking" for real TTS-driven visuals, then returns to idle
"""

from __future__ import annotations

import io
import queue
import random
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pygame
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for sunny_code
from sunny_code.components import tts  # noqa: E402

import renderer  # noqa: E402

PHRASES = [
    "Hello, I'm Sunny.",
    "Good morning. Here's what's on your schedule today.",
    "I've finished processing that request.",
    "Would you like me to continue?",
]


class TTSPlaybackAmplitude:
    """Plays real Piper-synthesized audio through the speakers and reports
    the RMS of whatever chunk is currently being output, so "speaking"
    reacts to actual TTS audio instead of the mic standing in for it. Same
    shape as renderer.MicAmplitude, but for output instead of input."""

    def __init__(self, samples: np.ndarray, samplerate: int) -> None:
        self._samples = samples.astype(np.float32) / 32768.0
        self._pos = 0
        self._level = 0.0
        self.finished = False
        self._stream = sd.OutputStream(
            samplerate=samplerate,
            channels=1,
            dtype="float32",
            blocksize=renderer.MIC_BLOCK_SAMPLES,
            callback=self._on_output,
            finished_callback=self._on_stream_finished,
        )
        self._stream.start()

    def _on_output(self, outdata, frames, time_info, status) -> None:
        remaining = len(self._samples) - self._pos
        n = min(frames, remaining)
        chunk = self._samples[self._pos : self._pos + n]
        outdata[:n, 0] = chunk
        if n < frames:
            outdata[n:, 0] = 0.0
        self._pos += n
        rms = float(np.sqrt(np.mean(chunk**2))) if n > 0 else 0.0
        self._level = min(1.0, rms * 6.0)
        if remaining <= frames:
            raise sd.CallbackStop()

    def _on_stream_finished(self) -> None:
        self.finished = True
        self._level = 0.0

    def __call__(self) -> float:
        return self._level

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def _decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        rate = wf.getframerate()
        channels = wf.getnchannels()
    samples = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return samples, rate


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode(renderer.WINDOW_SIZE)
    pygame.display.set_caption("Sunny face renderer -- real TTS demo")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    glow_surface = pygame.Surface(renderer.WINDOW_SIZE, pygame.SRCALPHA)
    effect_surface = pygame.Surface(renderer.WINDOW_SIZE, pygame.SRCALPHA)

    mic = renderer.MicAmplitude()
    tts_ready: queue.Queue = queue.Queue()
    synthesizing = False
    tts_amp: TTSPlaybackAmplitude | None = None

    def _synthesize_and_queue(text: str) -> None:
        try:
            wav_bytes = tts.synthesize_wav_bytes(text)
            tts_ready.put(_decode_wav(wav_bytes))
        except Exception as exc:  # noqa: BLE001 -- surfaced via the queue, not swallowed
            tts_ready.put(exc)

    sources = {
        "idle": renderer.ZeroAmplitude(),
        "listening": mic,
        "thinking": renderer.BreathingAmplitude(),
        "searching": renderer.BreathingAmplitude(base_hz=0.32, detune_hz=0.09, level=0.45),
        "speaking": mic,  # replaced with a real TTSPlaybackAmplitude while a clip plays
    }

    state = "idle"
    prev_state: str | None = None
    state_change_time = -renderer.TRANSITION_SECONDS
    emotion = "neutral"
    running = True
    frame_times: list[float] = []
    scan_angle = mid_dash_angle = thinking_dash_angle = tick_rotation = 0.0
    start_time = time.monotonic()
    smoothed_radius = float(renderer.BASE_RADIUS)
    smoothed_color = list(renderer._hue_to_rgb(renderer.EMOTIONS[emotion], value=renderer.IDLE_BRIGHTNESS))

    def _switch_state(new_state: str) -> None:
        nonlocal state, prev_state, state_change_time
        if new_state != state:
            prev_state = state
            state = new_state
            state_change_time = time.monotonic() - start_time

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif pygame.K_1 <= event.key <= pygame.K_5:
                        _switch_state(renderer.STATES[event.key - pygame.K_1])
                    elif event.key == pygame.K_e:
                        emotion = renderer.EMOTION_ORDER[
                            (renderer.EMOTION_ORDER.index(emotion) + 1) % len(renderer.EMOTION_ORDER)
                        ]
                    elif event.key == pygame.K_t and not synthesizing:
                        synthesizing = True
                        threading.Thread(
                            target=_synthesize_and_queue, args=(random.choice(PHRASES),), daemon=True
                        ).start()

            try:
                result = tts_ready.get_nowait()
            except queue.Empty:
                pass
            else:
                synthesizing = False
                if isinstance(result, Exception):
                    print(f"TTS synthesis failed: {result}", file=sys.stderr)
                else:
                    samples, rate = result
                    if tts_amp is not None:
                        tts_amp.close()
                    tts_amp = TTSPlaybackAmplitude(samples, rate)
                    sources["speaking"] = tts_amp
                    _switch_state("speaking")

            if tts_amp is not None and tts_amp.finished:
                sources["speaking"] = mic
                tts_amp.close()
                tts_amp = None
                if state == "speaking":
                    _switch_state("idle")

            amplitude = sources[state]()
            target_radius = renderer.BASE_RADIUS + amplitude * renderer.MAX_RADIUS_BOOST
            target_color = renderer._hue_to_rgb(
                renderer.EMOTIONS[emotion], value=renderer.IDLE_BRIGHTNESS if state == "idle" else 0.95
            )
            t = time.monotonic() - start_time

            dt = clock.get_time() / 1000.0
            smoothed_radius = renderer._ease(smoothed_radius, target_radius, renderer.RADIUS_SMOOTHING_HZ, dt)
            for i in range(3):
                smoothed_color[i] = renderer._ease(smoothed_color[i], target_color[i], renderer.COLOR_SMOOTHING_HZ, dt)
            core_radius = int(smoothed_radius)
            color = (int(smoothed_color[0]), int(smoothed_color[1]), int(smoothed_color[2]))
            transition_blend = min(1.0, (t - state_change_time) / renderer.TRANSITION_SECONDS)

            scan_angle = (
                scan_angle
                + (renderer.SCAN_BASE_DEGREES_PER_SEC + amplitude * renderer.SCAN_AMPLITUDE_DEGREES_PER_SEC) * dt
            ) % 360
            mid_dash_angle = (mid_dash_angle + renderer.MID_DASH_DEGREES_PER_SEC * dt) % 360
            thinking_dash_angle = (thinking_dash_angle + renderer.THINKING_DASH_DEGREES_PER_SEC * dt) % 360
            tick_rotation = (tick_rotation + renderer.TICK_DEGREES_PER_SEC * dt) % 360

            screen.fill((18, 18, 24))
            renderer._draw_face(
                screen, glow_surface, effect_surface, state, prev_state, transition_blend,
                core_radius, color, amplitude, t,
                scan_angle, mid_dash_angle, thinking_dash_angle, tick_rotation,
            )

            frame_times.append(clock.get_time())
            if len(frame_times) > 60:
                frame_times.pop(0)
            avg_frame_ms = sum(frame_times) / len(frame_times) if frame_times else 0.0
            fps = 1000.0 / avg_frame_ms if avg_frame_ms else 0.0

            hud = f"state={state}  emotion={emotion}  amp={amplitude:.2f}  fps={fps:.0f}"
            screen.blit(font.render(hud, True, (200, 200, 200)), (10, 10))
            tail = "synthesizing..." if synthesizing else "t = speak a real test phrase"
            screen.blit(
                font.render(f"1-5 state  e emotion  {tail}  esc quit", True, (120, 120, 120)),
                (10, renderer.WINDOW_SIZE[1] - 24),
            )

            pygame.display.flip()
            clock.tick(60)
    finally:
        mic.close()
        if tts_amp is not None:
            tts_amp.close()
        pygame.quit()


if __name__ == "__main__":
    main()
