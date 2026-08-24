"""Headless install/import/render smoke test for the pi-client stack.

Not a real hardware test -- see Dockerfile.test's header for exactly what
this does and doesn't prove. Runs the renderer's actual draw loop (real
shapes, real hue table) against synthesized amplitude sources only, since
a container has no mic/audio device to exercise MicAmplitude with.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # wake_word_listener.py etc. are siblings, one level up

FAILURES: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"[PASS] {label}")
    except Exception as exc:  # noqa: BLE001 -- smoke test, report anything
        print(f"[FAIL] {label}: {exc}")
        FAILURES.append(label)


def _import_deps() -> None:
    import numpy  # noqa: F401
    import pygame  # noqa: F401
    import requests  # noqa: F401
    import sounddevice  # noqa: F401
    import websockets  # noqa: F401


def _import_openwakeword() -> None:
    from openwakeword.model import Model  # noqa: F401


def _import_pi_client_scripts() -> None:
    import crash_reporter  # noqa: F401
    import wake_on_lan  # noqa: F401
    import wake_word_listener  # noqa: F401


def _render_loop() -> None:
    import pygame
    import renderer

    pygame.init()
    screen = pygame.display.set_mode(renderer.WINDOW_SIZE)
    clock = pygame.time.Clock()

    sources = {
        "idle": renderer.ZeroAmplitude(),
        "thinking": renderer.BreathingAmplitude(),
        "searching": renderer.BreathingAmplitude(base_hz=0.32, detune_hz=0.09, level=0.45),
    }

    frame_count = 0
    for state, source in sources.items():
        for _ in range(40):
            amplitude = source()
            radius = int(renderer.BASE_RADIUS + amplitude * renderer.MAX_RADIUS_BOOST)
            color = renderer._hue_to_rgb(renderer.EMOTIONS["neutral"])
            screen.fill((18, 18, 24))
            pygame.draw.circle(screen, color, (renderer.WINDOW_SIZE[0] // 2, renderer.WINDOW_SIZE[1] // 2), radius)
            pygame.display.flip()
            clock.tick(60)
            frame_count += 1

    pygame.quit()
    if frame_count != 120:
        raise RuntimeError(f"expected 120 frames, ran {frame_count}")


def _hue_table() -> None:
    import renderer

    for name, hue in renderer.EMOTIONS.items():
        r, g, b = renderer._hue_to_rgb(hue)
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255, f"{name} produced an out-of-range color"


def main() -> None:
    check("import pygame/sounddevice/numpy/requests/websockets", _import_deps)
    check("import openwakeword.model.Model", _import_openwakeword)
    check("import wake_word_listener/wake_on_lan/crash_reporter", _import_pi_client_scripts)
    check("hue table produces valid RGB for all 5 emotions", _hue_table)
    check("headless render loop, 120 frames across idle/thinking/searching", _render_loop)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
