"""Face renderer prototype (Phase 4) -- standalone dev-machine demo.

Pygame, drawn straight to the display via SDL2 -- no browser, no image
assets. A sci-fi HUD ring: two concentric ring outlines, a slowly-drifting
ring of radial tick marks, and a filled core whose radius reacts to a live
`amplitude` value, all always drawn. Every active state (everything but
idle) adds exactly one thing that makes it visually distinct at a glance,
not just amplitude-reactive -- see _draw_face's docstring for the full
per-state breakdown (halo/spinner/sweep/bars). All still "cheap primitives"
per BUILD_PLAN.md Phase 4 (circle/arc/line draws, no per-pixel shader work,
no particle field), unlike a fully organic dense hologram, which would
risk blowing Pi 3 B's CPU budget -- the exact failure mode this restart
exists to avoid repeating. A soft glow (one alpha-blended pass behind the
crisp shapes, on a single reused SRCALPHA surface) sells the "holographic"
look cheaply: a handful of extra draws and one blit per frame, not real
per-pixel bloom.

This is the "does the rendering technique even work" step: prove the
shape + amplitude + hue-overlay approach runs smoothly before touching
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
CENTER = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)

# core (amplitude-reactive filled circle)
BASE_RADIUS = 60
MAX_RADIUS_BOOST = 50

# static ring geometry
MID_RING_RADIUS = 140
OUTER_RING_RADIUS = 185
RING_WIDTH = 2

# tick marks around the outer ring -- slow constant drift, independent of
# everything else spinning, so no two rotating elements are ever in sync
TICK_COUNT = 24
TICK_INNER_RADIUS = OUTER_RING_RADIUS + 6
TICK_OUTER_RADIUS = OUTER_RING_RADIUS + 20
TICK_DEGREES_PER_SEC = 6

# outer scan arc -- fast, amplitude-reactive, clockwise
SCAN_ARC_DEGREES = 50
SCAN_ARC_WIDTH = 4
SCAN_BASE_DEGREES_PER_SEC = 25  # idle rotation speed
SCAN_AMPLITUDE_DEGREES_PER_SEC = 200  # extra speed, scaled by amplitude

# mid-ring dash arcs (listening/searching default) -- a handful of short arcs
# spaced evenly around the mid ring, rotating together, counter-clockwise and
# slower than the outer scan
MID_DASH_COUNT = 3
MID_DASH_DEGREES = 20
MID_DASH_WIDTH = 3
MID_DASH_DEGREES_PER_SEC = -40

# thinking -- more/shorter/faster dashes read as a loading spinner, distinct
# from listening/searching's slower 3-dash pattern
THINKING_DASH_COUNT = 8
THINKING_DASH_DEGREES = 12
THINKING_DASH_WIDTH = 3
THINKING_DASH_DEGREES_PER_SEC = -160

# listening -- a halo ring outside the outer ring that grows with live mic
# amplitude, on top of the normal scan arc/mid dashes
HALO_BASE_RADIUS = OUTER_RING_RADIUS + 15
HALO_AMPLITUDE_BOOST = 40
HALO_WIDTH = 1

# searching -- the outer arc sweeps back and forth like a radar beam instead
# of rotating all the way around, replacing the normal scan arc for this state
SEARCH_ARC_DEGREES = 35
SEARCH_ARC_WIDTH = 4
SEARCH_SWEEP_RANGE_DEGREES = 70
SEARCH_SWEEP_PERIOD_SEC = 1.6

# speaking -- the mid ring becomes amplitude-reactive radial bars (like an
# equalizer) instead of rotating dashes, replacing the normal mid dashes
SPEAK_BAR_COUNT = 16
SPEAK_BAR_BASE_LEN = 6
SPEAK_BAR_AMPLITUDE_BOOST = 34
SPEAK_BAR_WAVE_HZ = 3.0
SPEAK_BAR_WIDTH = 3

GLOW_ALPHA = 70
GLOW_WIDTH_BOOST = 5

# idle is dimmer than every active state -- another cheap, glance-readable
# distinguishing cue on top of "no scan arc, no mid-ring motion"
IDLE_BRIGHTNESS = 0.55

# smoothing/transitions -- switching states or emotions used to pop instantly;
# these ease it. *_SMOOTHING_HZ are exponential decay rates (higher = snappier,
# see main()'s lerp), TRANSITION_SECONDS is the extras crossfade window
RADIUS_SMOOTHING_HZ = 10.0
COLOR_SMOOTHING_HZ = 8.0
TRANSITION_SECONDS = 0.35

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


def _hue_to_rgb(hue: float, value: float = 0.95) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, value)
    return int(r * 255), int(g * 255), int(b * 255)


def _tick_lines(rotation_deg: float) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Endpoints for the ring of radial tick marks at a given rotation --
    recomputed each frame (TICK_COUNT is small, well under Pi 3 B's budget)
    since the whole ring now drifts slowly instead of sitting static."""
    lines = []
    for i in range(TICK_COUNT):
        angle = math.radians(rotation_deg + 360 * i / TICK_COUNT)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        inner = (CENTER[0] + TICK_INNER_RADIUS * cos_a, CENTER[1] + TICK_INNER_RADIUS * sin_a)
        outer = (CENTER[0] + TICK_OUTER_RADIUS * cos_a, CENTER[1] + TICK_OUTER_RADIUS * sin_a)
        lines.append((inner, outer))
    return lines


def _arc_pairs(angle_deg: float, count: int, arc_degrees: float) -> list[tuple[float, float]]:
    """count evenly-spaced (start, end) angle pairs in radians, rotated together from angle_deg."""
    return [
        (math.radians(angle_deg + i * 360 / count), math.radians(angle_deg + i * 360 / count + arc_degrees))
        for i in range(count)
    ]


class _StateEffects:
    """The per-state "extra" visual layer, as plain geometry -- no drawing,
    no surface, just what _draw_effects needs. Kept as one small object so
    it's cheap to compute twice (outgoing + incoming state) during a
    transition crossfade."""

    __slots__ = ("scan_arcs", "mid_arcs", "bars", "halo_radius", "dash_width", "scan_width")

    def __init__(self) -> None:
        self.scan_arcs: list[tuple[float, float]] = []
        self.mid_arcs: list[tuple[float, float]] = []
        self.bars: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.halo_radius: float | None = None
        self.dash_width = MID_DASH_WIDTH
        self.scan_width = SCAN_ARC_WIDTH


def _state_effects(
    state: str,
    t: float,
    amplitude: float,
    scan_angle_deg: float,
    mid_dash_angle_deg: float,
    thinking_dash_angle_deg: float,
) -> _StateEffects:
    """Every active state adds exactly one thing that makes it, not just its
    amplitude source, visually distinct -- `idle` stops at the always-drawn
    base (rings/ticks/core), everything else adds one of:
      - listening -- normal scan arc + 3 mid dashes, plus a halo ring outside
        everything that grows with live mic amplitude
      - thinking -- normal scan arc, but the mid dashes become an 8-dash
        fast spinner instead of the normal 3-dash pattern
      - searching -- the scan arc sweeps back and forth (a radar ping)
        instead of rotating all the way around; mid dashes stay normal
      - speaking -- normal scan arc, but the mid ring becomes amplitude-
        reactive radial bars (an equalizer) instead of rotating dashes
    A pure function of (state, ...) -- not just the live current state --
    so _draw_face can call it for both the outgoing and incoming state and
    crossfade between them during a transition."""
    fx = _StateEffects()
    if state == "idle":
        return fx

    if state == "searching":
        sweep_center = SEARCH_SWEEP_RANGE_DEGREES * math.sin(2 * math.pi * t / SEARCH_SWEEP_PERIOD_SEC)
        fx.scan_arcs = [(math.radians(sweep_center), math.radians(sweep_center + SEARCH_ARC_DEGREES))]
        fx.scan_width = SEARCH_ARC_WIDTH
    else:
        fx.scan_arcs = [(math.radians(scan_angle_deg), math.radians(scan_angle_deg + SCAN_ARC_DEGREES))]

    if state == "thinking":
        fx.mid_arcs = _arc_pairs(thinking_dash_angle_deg, THINKING_DASH_COUNT, THINKING_DASH_DEGREES)
        fx.dash_width = THINKING_DASH_WIDTH
    elif state == "speaking":
        for i in range(SPEAK_BAR_COUNT):
            angle = math.radians(i * 360 / SPEAK_BAR_COUNT)
            wave = 0.4 + 0.6 * abs(math.sin(2 * math.pi * SPEAK_BAR_WAVE_HZ * t + i * 0.7))
            bar_len = SPEAK_BAR_BASE_LEN + amplitude * SPEAK_BAR_AMPLITUDE_BOOST * wave
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            inner = (CENTER[0] + MID_RING_RADIUS * cos_a, CENTER[1] + MID_RING_RADIUS * sin_a)
            outer = (CENTER[0] + (MID_RING_RADIUS + bar_len) * cos_a, CENTER[1] + (MID_RING_RADIUS + bar_len) * sin_a)
            fx.bars.append((inner, outer))
    else:
        fx.mid_arcs = _arc_pairs(mid_dash_angle_deg, MID_DASH_COUNT, MID_DASH_DEGREES)

    if state == "listening":
        fx.halo_radius = HALO_BASE_RADIUS + amplitude * HALO_AMPLITUDE_BOOST

    return fx


def _draw_effects(
    surface: pygame.Surface,
    fx: _StateEffects,
    outer_rect: pygame.Rect,
    mid_rect: pygame.Rect,
    color: tuple[int, int, int],
    alpha: int,
    extra_width: int = 0,
) -> None:
    """Draws one _StateEffects' geometry onto `surface` at a given alpha --
    `surface` must support per-pixel alpha (SRCALPHA) whenever alpha < 255."""
    if alpha <= 0:
        return
    c = (*color, alpha)
    for start, end in fx.scan_arcs:
        pygame.draw.arc(surface, c, outer_rect, start, end, fx.scan_width + extra_width)
    for start, end in fx.mid_arcs:
        pygame.draw.arc(surface, c, mid_rect, start, end, fx.dash_width + extra_width)
    for inner, outer in fx.bars:
        pygame.draw.line(surface, c, inner, outer, SPEAK_BAR_WIDTH + extra_width)
    if fx.halo_radius is not None:
        pygame.draw.circle(surface, c, CENTER, int(fx.halo_radius), HALO_WIDTH + extra_width)


def _draw_face(
    screen: pygame.Surface,
    glow_surface: pygame.Surface,
    effect_surface: pygame.Surface,
    state: str,
    prev_state: str | None,
    transition_blend: float,
    core_radius: int,
    color: tuple[int, int, int],
    amplitude: float,
    t: float,
    scan_angle_deg: float,
    mid_dash_angle_deg: float,
    thinking_dash_angle_deg: float,
    tick_rotation_deg: float,
) -> None:
    """One HUD-ring frame. Always drawn: two ring outlines, a slowly-drifting
    tick ring, and an amplitude-reactive filled core -- all cheap primitives
    (circle/arc/line draws), plus one soft glow pass on a reused alpha
    surface for the holographic look. See module docstring for the overall
    design constraint (cheap primitives only, no per-pixel/particle work)
    and _state_effects for what makes each state visually distinct.

    transition_blend < 1.0 means a state switch happened less than
    TRANSITION_SECONDS ago -- both prev_state's and state's extras get drawn
    together, crossfading via alpha on `effect_surface` (a second reused
    SRCALPHA surface), so switching states eases instead of popping. Once
    settled (blend >= 1, the common case) this skips the extra surface
    entirely and draws straight to `screen`, same cost as before."""
    outer_rect = pygame.Rect(0, 0, OUTER_RING_RADIUS * 2, OUTER_RING_RADIUS * 2)
    outer_rect.center = CENTER
    mid_rect = pygame.Rect(0, 0, MID_RING_RADIUS * 2, MID_RING_RADIUS * 2)
    mid_rect.center = CENTER
    tick_lines = _tick_lines(tick_rotation_deg)
    cur_fx = _state_effects(state, t, amplitude, scan_angle_deg, mid_dash_angle_deg, thinking_dash_angle_deg)

    glow_surface.fill((0, 0, 0, 0))
    glow_color = (*color, GLOW_ALPHA)
    pygame.draw.circle(glow_surface, glow_color, CENTER, core_radius + GLOW_WIDTH_BOOST)
    pygame.draw.circle(glow_surface, glow_color, CENTER, MID_RING_RADIUS, RING_WIDTH + GLOW_WIDTH_BOOST)
    pygame.draw.circle(glow_surface, glow_color, CENTER, OUTER_RING_RADIUS, RING_WIDTH + GLOW_WIDTH_BOOST)

    if transition_blend >= 1.0:
        _draw_effects(glow_surface, cur_fx, outer_rect, mid_rect, color, GLOW_ALPHA, GLOW_WIDTH_BOOST)
        screen.blit(glow_surface, (0, 0))

        dim_color = _scale_rgb(color, 0.35)
        for inner, outer in tick_lines:
            pygame.draw.line(screen, dim_color, inner, outer, 1)
        pygame.draw.circle(screen, color, CENTER, MID_RING_RADIUS, RING_WIDTH)
        pygame.draw.circle(screen, color, CENTER, OUTER_RING_RADIUS, RING_WIDTH)
        _draw_effects(screen, cur_fx, outer_rect, mid_rect, color, 255)
    else:
        prev_fx = _state_effects(prev_state, t, amplitude, scan_angle_deg, mid_dash_angle_deg, thinking_dash_angle_deg)
        _draw_effects(glow_surface, prev_fx, outer_rect, mid_rect, color, int(GLOW_ALPHA * (1 - transition_blend)), GLOW_WIDTH_BOOST)
        _draw_effects(glow_surface, cur_fx, outer_rect, mid_rect, color, int(GLOW_ALPHA * transition_blend), GLOW_WIDTH_BOOST)
        screen.blit(glow_surface, (0, 0))

        dim_color = _scale_rgb(color, 0.35)
        for inner, outer in tick_lines:
            pygame.draw.line(screen, dim_color, inner, outer, 1)
        pygame.draw.circle(screen, color, CENTER, MID_RING_RADIUS, RING_WIDTH)
        pygame.draw.circle(screen, color, CENTER, OUTER_RING_RADIUS, RING_WIDTH)

        effect_surface.fill((0, 0, 0, 0))
        _draw_effects(effect_surface, prev_fx, outer_rect, mid_rect, color, int(255 * (1 - transition_blend)))
        _draw_effects(effect_surface, cur_fx, outer_rect, mid_rect, color, int(255 * transition_blend))
        screen.blit(effect_surface, (0, 0))

    pygame.draw.circle(screen, color, CENTER, core_radius)
    pygame.draw.circle(screen, (18, 18, 24), CENTER, 4)  # small dark center dot, crosshair-style


def _scale_rgb(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(int(c * factor) for c in color)


def _ease(current: float, target: float, rate_hz: float, dt: float) -> float:
    """Exponential ease toward target -- used for both core_radius and color
    so amplitude/state/emotion changes ease in over a few frames instead of
    snapping. rate_hz higher = snappier; see RADIUS_SMOOTHING_HZ/COLOR_SMOOTHING_HZ."""
    return current + (target - current) * min(1.0, rate_hz * dt)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Sunny face renderer prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    glow_surface = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
    effect_surface = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)

    mic = MicAmplitude()
    sources: dict[str, Callable[[], float]] = {
        "idle": ZeroAmplitude(),
        "listening": mic,
        "thinking": BreathingAmplitude(),
        "searching": BreathingAmplitude(base_hz=0.32, detune_hz=0.09, level=0.45),
        "speaking": mic,  # stand-in for the real TTS playback buffer RMS (Phase 4.5)
    }

    state = "idle"
    prev_state: str | None = None
    state_change_time = -TRANSITION_SECONDS  # settled from frame one
    emotion = "neutral"
    running = True
    frame_times: list[float] = []
    scan_angle = 0.0
    mid_dash_angle = 0.0
    thinking_dash_angle = 0.0
    tick_rotation = 0.0
    start_time = time.monotonic()
    smoothed_radius = float(BASE_RADIUS)
    smoothed_color = list(_hue_to_rgb(EMOTIONS[emotion], value=IDLE_BRIGHTNESS))

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif pygame.K_1 <= event.key <= pygame.K_5:
                        new_state = STATES[event.key - pygame.K_1]
                        if new_state != state:
                            prev_state = state
                            state = new_state
                            state_change_time = time.monotonic() - start_time
                    elif event.key == pygame.K_e:
                        emotion = EMOTION_ORDER[(EMOTION_ORDER.index(emotion) + 1) % len(EMOTION_ORDER)]

            amplitude = sources[state]()
            target_radius = BASE_RADIUS + amplitude * MAX_RADIUS_BOOST
            target_color = _hue_to_rgb(EMOTIONS[emotion], value=IDLE_BRIGHTNESS if state == "idle" else 0.95)
            t = time.monotonic() - start_time

            dt = clock.get_time() / 1000.0
            smoothed_radius = _ease(smoothed_radius, target_radius, RADIUS_SMOOTHING_HZ, dt)
            for i in range(3):
                smoothed_color[i] = _ease(smoothed_color[i], target_color[i], COLOR_SMOOTHING_HZ, dt)
            core_radius = int(smoothed_radius)
            color = (int(smoothed_color[0]), int(smoothed_color[1]), int(smoothed_color[2]))
            transition_blend = min(1.0, (t - state_change_time) / TRANSITION_SECONDS)

            scan_angle = (scan_angle + (SCAN_BASE_DEGREES_PER_SEC + amplitude * SCAN_AMPLITUDE_DEGREES_PER_SEC) * dt) % 360
            mid_dash_angle = (mid_dash_angle + MID_DASH_DEGREES_PER_SEC * dt) % 360
            thinking_dash_angle = (thinking_dash_angle + THINKING_DASH_DEGREES_PER_SEC * dt) % 360
            tick_rotation = (tick_rotation + TICK_DEGREES_PER_SEC * dt) % 360

            screen.fill((18, 18, 24))
            _draw_face(
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
