#!/usr/bin/env python3
"""Does a tap land where the finger actually pressed?

This is the one part of the touch menu that cannot be checked by looking
at it. Everything else is visible on the panel; a rotation inverse that
is subtly wrong still draws a perfect menu and simply activates the wrong
button, and on a 4-button row the wrong button is often a plausible one.

The test does NOT re-derive the mapping and compare it against
Display.to_canvas -- that would only prove two copies of the same
arithmetic agree. Instead it puts a uniquely coloured pixel on the canvas,
runs the REAL pygame.transform.rotate that present() uses, finds where
that pixel physically landed, and asserts to_canvas maps it back to where
it started. If present() and to_canvas ever disagree, this fails.

Run on any machine: pure Surface operations, no display or panel needed.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from display.app import Display

FAILURES = []
MARKER = (255, 0, 255)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


class FakeDisplay:
    """Just enough Display to exercise to_canvas, without SDL video."""

    def __init__(self, panel, rotate):
        self.rotate = rotate
        self.physical = pygame.Surface(panel)
        self.size = (panel[1], panel[0]) if rotate in (90, 270) else panel
        self.canvas = pygame.Surface(self.size)

    to_canvas = Display.to_canvas
    touch_point = Display.touch_point


def present_like(display):
    """Byte-for-byte what Display.present() does to get canvas onto panel."""
    if display.rotate:
        display.physical.blit(pygame.transform.rotate(display.canvas, display.rotate), (0, 0))
    else:
        display.physical.blit(display.canvas, (0, 0))


def find_marker(surface):
    width, height = surface.get_size()
    for x in range(width):
        for y in range(height):
            if surface.get_at((x, y))[:3] == MARKER:
                return (x, y)
    return None


def round_trip(rotate, panel=(480, 800)):
    """For every corner and the centre: draw at a canvas point, rotate,
    locate the pixel on the panel, map it back, and require it to return
    to the point it started from."""
    display = FakeDisplay(panel, rotate)
    cw, ch = display.size
    points = [(0, 0), (cw - 1, 0), (0, ch - 1), (cw - 1, ch - 1), (cw // 2, ch // 3)]

    worst = 0
    for canvas_point in points:
        display.canvas.fill((0, 0, 0))
        display.physical.fill((0, 0, 0))
        display.canvas.set_at(canvas_point, MARKER)
        present_like(display)

        panel_point = find_marker(display.physical)
        if panel_point is None:
            check(f"rotate {rotate}: marker at {canvas_point} reached the panel", False)
            continue

        mapped = display.to_canvas(*panel_point)
        drift = max(abs(mapped[0] - canvas_point[0]), abs(mapped[1] - canvas_point[1]))
        worst = max(worst, drift)

    check(f"rotate {rotate}: every point maps back exactly (worst drift {worst}px)", worst == 0)


def test_all_rotations():
    print("\n-- round trip through the real rotation --")
    for rotate in (0, 90, 180, 270):
        round_trip(rotate)


def test_orientation_is_not_accidentally_symmetric():
    """A square panel would let a wrong axis order pass unnoticed, and
    mapping that is right only on a square is exactly the bug that ships.
    The real panel is 480x800, so assert the axes genuinely swap."""
    print("\n-- axes actually swap --")
    display = FakeDisplay((480, 800), 90)
    check("logical canvas is landscape", display.size == (800, 480))

    # A touch near the panel's top edge is near the canvas RIGHT edge at 90.
    x, _ = display.to_canvas(240, 2)
    check("a tap at the top of the panel lands at the right of the canvas", x > 700)

    x, _ = display.to_canvas(240, 797)
    check("a tap at the bottom of the panel lands at the left of the canvas", x < 100)


def test_clamping():
    print("\n-- out-of-range readings --")
    display = FakeDisplay((480, 800), 90)
    cw, ch = display.size
    for px, py in [(-5, -5), (10000, 10000), (-1, 400)]:
        x, y = display.to_canvas(px, py)
        if not (0 <= x < cw and 0 <= y < ch):
            check(f"panel reading {px},{py} clamped into the canvas", False)
            break
    else:
        check("out-of-range panel readings clamp instead of escaping", True)


def test_finger_events_are_normalized():
    print("\n-- FINGERDOWN normalization --")
    display = FakeDisplay((480, 800), 90)

    class Event:
        type = pygame.FINGERDOWN
        x = 0.5
        y = 0.0

    centre_top = display.touch_point(Event())
    # Normalized (0.5, 0.0) is the middle of the panel's top edge, which at
    # 90 degrees is the middle of the canvas's right edge.
    check("finger coords scale to the panel", centre_top is not None)
    check("normalized top-centre maps to canvas right edge",
          centre_top[0] > 700 and 200 < centre_top[1] < 280)

    class Ignored:
        type = pygame.KEYDOWN

    check("non-touch events yield no point", display.touch_point(Ignored()) is None)


if __name__ == "__main__":
    pygame.init()
    test_all_rotations()
    test_orientation_is_not_accidentally_symmetric()
    test_clamping()
    test_finger_events_are_normalized()
    pygame.quit()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("Touch mapping verified against the real rotation.")
