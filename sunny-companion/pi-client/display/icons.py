"""Vector icons for the touch menu.

Drawn as geometry, same reasoning as graphics.py: nothing to ship, nothing
to keep in sync with the repo, and a Pi 3B drawing a dozen lines costs
nothing next to decoding sprites. It also means an icon scales to any
button size without a second asset.

Every icon draws inside a square box of side `size` centred on `center`,
so the menu can lay buttons out without knowing which icon is in one.
Line widths scale with size rather than being fixed, or icons look
hairline at 64px and clumsy at 24px.

The set is deliberately small and literal. On a 4in panel read at arm's
length, a clever glyph is just a smudge -- these are the shapes people
already recognise without a legend.
"""

import math
from typing import Tuple

import pygame


def _stroke(size: int) -> int:
    return max(2, int(size * 0.09))


def check(surface, center: Tuple[int, int], size: int, color) -> None:
    """Tick. Yes."""
    cx, cy = center
    w = _stroke(size)
    half = size / 2
    points = [
        (cx - half * 0.75, cy),
        (cx - half * 0.15, cy + half * 0.58),
        (cx + half * 0.8, cy - half * 0.62),
    ]
    pygame.draw.lines(surface, color, False, [(int(x), int(y)) for x, y in points], w)


def cross(surface, center: Tuple[int, int], size: int, color) -> None:
    """X. No."""
    cx, cy = center
    w = _stroke(size)
    half = size * 0.36
    pygame.draw.line(surface, color, (int(cx - half), int(cy - half)),
                     (int(cx + half), int(cy + half)), w)
    pygame.draw.line(surface, color, (int(cx + half), int(cy - half)),
                     (int(cx - half), int(cy + half)), w)


def calendar(surface, center: Tuple[int, int], size: int, color) -> None:
    cx, cy = center
    w = max(2, int(size * 0.07))
    box = pygame.Rect(0, 0, int(size * 0.82), int(size * 0.74))
    box.center = (cx, cy + int(size * 0.05))
    pygame.draw.rect(surface, color, box, width=w, border_radius=max(2, int(size * 0.1)))
    # Header bar, so it reads as a calendar rather than a plain window.
    pygame.draw.line(surface, color, (box.left + w, box.top + int(size * 0.22)),
                     (box.right - w, box.top + int(size * 0.22)), w)
    # Two hanging rings.
    for offset in (-0.22, 0.22):
        x = int(cx + size * offset)
        pygame.draw.line(surface, color, (x, box.top - int(size * 0.11)),
                         (x, box.top + int(size * 0.04)), w)


def cloud(surface, center: Tuple[int, int], size: int, color) -> None:
    """Weather. FILLED, unlike the line icons around it.

    A cloud is a silhouette, and drawn as an outline at this size it came
    out as three disconnected rings that read as nothing at all. Filling
    it gives one continuous shape, which is what makes a cloud legible
    from across a desk. Same for the heart below; everything else here is
    genuinely line art and stays outlined.
    """
    cx, cy = center
    # Sun peeking out behind the top-left, drawn first so the cloud
    # overlaps it.
    pygame.draw.circle(surface, color, (int(cx - size * 0.24), int(cy - size * 0.26)),
                       int(size * 0.15))

    base_y = int(cy + size * 0.14)
    puffs = [
        (cx - size * 0.20, base_y - size * 0.02, size * 0.17),
        (cx + size * 0.02, base_y - size * 0.13, size * 0.21),
        (cx + size * 0.24, base_y - size * 0.01, size * 0.16),
    ]
    for px, py, r in puffs:
        pygame.draw.circle(surface, color, (int(px), int(py)), int(r))
    # Flat underside joining the puffs into one mass.
    base = pygame.Rect(int(cx - size * 0.37), base_y - int(size * 0.02),
                       int(size * 0.74), int(size * 0.19))
    pygame.draw.rect(surface, color, base, border_radius=int(size * 0.09))


def checklist(surface, center: Tuple[int, int], size: int, color) -> None:
    """Tasks. Three rows, each with a tick."""
    cx, cy = center
    w = max(2, int(size * 0.07))
    for i, offset in enumerate((-0.28, 0.0, 0.28)):
        y = int(cy + size * offset)
        tick_x = int(cx - size * 0.34)
        pygame.draw.lines(surface, color, False, [
            (tick_x, y),
            (tick_x + int(size * 0.08), y + int(size * 0.08)),
            (tick_x + int(size * 0.22), y - int(size * 0.1)),
        ], w)
        pygame.draw.line(surface, color, (int(cx + size * 0.02), y),
                         (int(cx + size * 0.38), y), w)


def heart(surface, center: Tuple[int, int], size: int, color) -> None:
    """Health. Filled, for the same reason as the cloud."""
    cx, cy = center
    r = size * 0.23
    top = cy - size * 0.12
    pygame.draw.circle(surface, color, (int(cx - r * 0.88), int(top)), int(r))
    pygame.draw.circle(surface, color, (int(cx + r * 0.88), int(top)), int(r))
    pygame.draw.polygon(surface, color, [
        (int(cx - r * 1.78), int(top + r * 0.15)),
        (int(cx + r * 1.78), int(top + r * 0.15)),
        (int(cx), int(cy + size * 0.42)),
    ])


def refresh(surface, center: Tuple[int, int], size: int, color) -> None:
    """Circular arrow. Drawn as a run of dots for the same reason
    graphics.arc_gauge does -- pygame.draw.arc is thin and aliased and
    looks broken at this size."""
    cx, cy = center
    radius = size * 0.34
    w = max(2, int(size * 0.08))
    # Leave a gap at the top right for the arrowhead.
    start, end = math.radians(-40), math.radians(280)
    steps = max(14, int(size))
    for i in range(steps):
        angle = start + (end - start) * (i / (steps - 1))
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        pygame.draw.circle(surface, color, (int(x), int(y)), max(1, w // 2))
    # Arrowhead as a FILLED triangle. Drawn as three strokes it was a
    # couple of hairlines at the end of the arc and simply disappeared,
    # leaving what looked like a broken circle.
    ax = cx + radius * math.cos(start)
    ay = cy + radius * math.sin(start)
    head = size * 0.20
    # Perpendicular to the arc at the opening, so the head points along
    # the direction of travel rather than at a fixed angle.
    tangent = start + math.pi / 2
    tx, ty = math.cos(tangent), math.sin(tangent)
    nx, ny = math.cos(start), math.sin(start)
    pygame.draw.polygon(surface, color, [
        (int(ax + tx * head), int(ay + ty * head)),
        (int(ax - tx * head * 0.35 + nx * head * 0.85),
         int(ay - ty * head * 0.35 + ny * head * 0.85)),
        (int(ax - tx * head * 0.35 - nx * head * 0.85),
         int(ay - ty * head * 0.35 - ny * head * 0.85)),
    ])


def question(surface, center: Tuple[int, int], size: int, color) -> None:
    """Check-in. A question mark.

    Needed its own glyph because the check-in button was reusing the
    checklist icon, which Tasks also uses -- two buttons with identical
    icons in one grid is worse than no icons, since it actively suggests
    they do the same thing.

    The hook is a run of dots for the same reason arcs are everywhere
    else here: pygame.draw.arc is thin and aliased at this size.
    """
    cx, cy = center
    w = max(2, int(size * 0.1))
    radius = size * 0.22
    hook_cy = cy - size * 0.16

    # Open arc from lower-left, over the top, round to the right.
    start, end = math.radians(160), math.radians(370)
    steps = max(12, int(size * 0.7))
    for i in range(steps):
        angle = start + (end - start) * (i / (steps - 1))
        pygame.draw.circle(
            surface, color,
            (int(cx + radius * math.cos(angle)), int(hook_cy + radius * math.sin(angle))),
            max(1, w // 2))

    # Stem down from where the arc ends, into the centre.
    tail_x = cx + radius * math.cos(end)
    tail_y = hook_cy + radius * math.sin(end)
    pygame.draw.line(surface, color, (int(tail_x), int(tail_y)),
                     (int(cx), int(cy + size * 0.14)), w)
    # The dot.
    pygame.draw.circle(surface, color, (int(cx), int(cy + size * 0.36)),
                       max(2, int(w * 0.72)))


def back(surface, center: Tuple[int, int], size: int, color) -> None:
    """Close / dismiss. A left chevron reads as "out of here" better than
    another X, which would collide with the No button."""
    cx, cy = center
    w = _stroke(size)
    half = size * 0.3
    pygame.draw.lines(surface, color, False, [
        (int(cx + half * 0.6), int(cy - half)),
        (int(cx - half * 0.5), int(cy)),
        (int(cx + half * 0.6), int(cy + half)),
    ], w)


def dot(surface, center: Tuple[int, int], size: int, color) -> None:
    """Fallback for an item with no icon of its own."""
    pygame.draw.circle(surface, color, center, max(3, int(size * 0.18)),
                       max(2, int(size * 0.08)))


# Name -> drawing function. Menu items carry the NAME, so a caller never
# imports a function and the set stays swappable.
ICONS = {
    "check": check,
    "cross": cross,
    "calendar": calendar,
    "cloud": cloud,
    "checklist": checklist,
    "heart": heart,
    "refresh": refresh,
    "question": question,
    "back": back,
    "dot": dot,
}


def draw(name: str, surface, center: Tuple[int, int], size: int, color) -> None:
    ICONS.get(name, dot)(surface, center, size, color)
