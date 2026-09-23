#!/usr/bin/env python3
"""Touch calibration for the Waveshare 4inch HDMI LCD.

WHY THIS EXISTS
---------------
Video reaches this panel over HDMI and touch arrives separately over SPI
from an ADS7846. Nothing makes the two agree about orientation. On this
Pi they demonstrably do not: config.txt drives the panel with
`hdmi_timings=480 ... 800 ...`, i.e. 480x800 portrait, while the glass
itself is 800x480 landscape, and the device-tree overlay has
`swapxy = <0x00>`. So the touch axes and the framebuffer axes are related
by some rotation/flip, and there are eight possible answers.

Rather than guess one and ask someone to keep re-testing, this measures
it. Four targets appear one at a time; tap each. Every one of the eight
orientations is then scored against what was actually tapped, and the
best one is printed along with its error, so a wrong answer is visible as
a large number rather than shipping silently.

USAGE
-----
    systemctl --user stop sunny-face
    cd ~/Project-SUNNY/sunny-companion/pi-client
    python3 calibrate.py
    systemctl --user start sunny-face

It needs the screen to itself, hence stopping the service first.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

import pygame

# Targets as a fraction of the PANEL (not the rotated canvas). Inset from
# the corners: a resistive panel is least accurate at its extreme edges,
# and a target in the very corner is also awkward to hit squarely.
TARGETS = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]

BG = (8, 8, 10)
TARGET_COLOR = (247, 209, 1)
DONE_COLOR = (37, 150, 190)
TEXT = (240, 240, 240)


def orientations():
    """The eight ways a touch panel can be mounted relative to a
    framebuffer: axes swapped or not, times each axis flipped or not."""
    for swap in (False, True):
        for flip_x in (False, True):
            for flip_y in (False, True):
                yield swap, flip_x, flip_y


def apply(orientation, nx, ny):
    """Map a normalized touch reading to normalized panel position."""
    swap, flip_x, flip_y = orientation
    if swap:
        nx, ny = ny, nx
    if flip_x:
        nx = 1.0 - nx
    if flip_y:
        ny = 1.0 - ny
    return nx, ny


def describe(orientation):
    swap, flip_x, flip_y = orientation
    parts = []
    parts.append("swap axes" if swap else "no swap")
    if flip_x:
        parts.append("flip X")
    if flip_y:
        parts.append("flip Y")
    return ", ".join(parts)


def main() -> int:
    pygame.init()
    pygame.mouse.set_visible(False)
    info = pygame.display.Info()
    panel = (info.current_w, info.current_h)
    screen = pygame.display.set_mode(panel, pygame.FULLSCREEN)
    font = pygame.font.Font(None, max(18, int(min(panel) * 0.055)))
    small = pygame.font.Font(None, max(14, int(min(panel) * 0.040)))

    print(f"panel: {panel[0]}x{panel[1]}")
    print("Tap each target. Press ESC to abort.\n")

    samples = []
    for index, (fx, fy) in enumerate(TARGETS):
        target_px = (int(fx * panel[0]), int(fy * panel[1]))
        captured = None

        while captured is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return 1
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return 1
                if event.type == pygame.FINGERDOWN:
                    captured = ("finger", event.x, event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # Normalize so both sources are comparable.
                    captured = ("mouse", event.pos[0] / panel[0], event.pos[1] / panel[1])

            screen.fill(BG)
            for done_index in range(index):
                dfx, dfy = TARGETS[done_index]
                pygame.draw.circle(screen, DONE_COLOR,
                                   (int(dfx * panel[0]), int(dfy * panel[1])), 10, 2)

            radius = int(min(panel) * 0.09)
            pygame.draw.circle(screen, TARGET_COLOR, target_px, radius, 3)
            pygame.draw.circle(screen, TARGET_COLOR, target_px, 4)
            pygame.draw.line(screen, TARGET_COLOR,
                             (target_px[0] - radius - 12, target_px[1]),
                             (target_px[0] + radius + 12, target_px[1]), 1)
            pygame.draw.line(screen, TARGET_COLOR,
                             (target_px[0], target_px[1] - radius - 12),
                             (target_px[0], target_px[1] + radius + 12), 1)

            label = font.render(f"Tap target {index + 1} of {len(TARGETS)}", True, TEXT)
            screen.blit(label, label.get_rect(center=(panel[0] // 2, int(panel[1] * 0.06))))
            hint = small.render("press firmly - resistive panel", True, (120, 120, 120))
            screen.blit(hint, hint.get_rect(center=(panel[0] // 2, int(panel[1] * 0.94))))
            pygame.display.flip()
            pygame.time.wait(16)

        source, nx, ny = captured
        samples.append(((fx, fy), (nx, ny)))
        print(f"  target {index + 1} at ({fx:.1f},{fy:.1f}) -> {source} reading "
              f"({nx:.3f},{ny:.3f})")
        # Swallow the release so it can't count as the next target's tap.
        pygame.time.wait(350)
        pygame.event.clear()

    pygame.quit()

    print("\nScoring all eight orientations (lower error is better):\n")
    scored = []
    for orientation in orientations():
        total = 0.0
        for (fx, fy), (nx, ny) in samples:
            mx, my = apply(orientation, nx, ny)
            total += ((mx - fx) ** 2 + (my - fy) ** 2) ** 0.5
        scored.append((total / len(samples), orientation))

    scored.sort()
    for error, orientation in scored:
        print(f"  {error:6.3f}   {describe(orientation)}")

    best_error, best = scored[0]
    runner_up = scored[1][0]
    print(f"\nBEST: {describe(best)}   (mean error {best_error:.3f})")
    print(f"      swap={best[0]} flip_x={best[1]} flip_y={best[2]}")

    if best_error > 0.15:
        print("\nWARNING: even the best fit is poor. Readings may be noisy or the")
        print("panel may need its xmin/xmax/ymin/ymax retuned in config.txt.")
    elif runner_up - best_error < 0.05:
        print("\nWARNING: the top two orientations score almost the same, so this")
        print("result is not trustworthy. Re-run and tap the targets more precisely.")
    else:
        print("\nClear winner. Put this in the service environment:")
        print(f"    TOUCH_SWAP={int(best[0])}  TOUCH_FLIP_X={int(best[1])}  TOUCH_FLIP_Y={int(best[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
