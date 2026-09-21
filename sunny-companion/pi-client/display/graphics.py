"""Simple drawn graphics for the companion panes.

Everything here is geometry -- no image assets, no fonts beyond what the
display already loads. Two reasons: there is nothing to ship or keep in
sync with the repo, and a Pi 3B redrawing a handful of circles costs
essentially nothing next to decoding and blitting sprites.

Arcs are drawn as a run of filled circles along the path rather than with
pygame.draw.arc, which produces a thin aliased line that looks broken at
this size. Circles give a rounded cap for free and read cleanly on a small
panel from across a desk.
"""

import math
from typing import Optional, Tuple

import pygame

DIM = (120, 120, 120)
TRACK = (38, 38, 38)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def arc_gauge(
    surface: pygame.Surface,
    center: Tuple[int, int],
    radius: int,
    fraction: float,
    color,
    thickness: Optional[int] = None,
    track_color=TRACK,
    start_deg: float = 135.0,
    sweep_deg: float = 270.0,
) -> None:
    """A circular progress gauge, open at the bottom.

    Starts bottom-left and sweeps 270 degrees clockwise, leaving a gap at
    the bottom -- the gap is what makes it read as a gauge rather than a
    pie chart, and it leaves room for a value in the middle.
    """
    thickness = thickness or max(4, radius // 6)
    fraction = _clamp01(fraction)
    cx, cy = center

    # Step by arc length rather than a fixed count, so a big gauge does
    # not end up with visible gaps between the dots.
    steps = max(24, int(sweep_deg * radius / 90))

    def plot(upto: float, paint):
        drawn = int(steps * upto)
        for i in range(drawn + 1):
            angle = math.radians(start_deg + (sweep_deg * i / steps))
            x = cx + radius * math.cos(angle)
            y = cy - radius * math.sin(angle)
            pygame.draw.circle(surface, paint, (int(x), int(y)), thickness // 2)

    plot(1.0, track_color)
    if fraction > 0:
        plot(fraction, color)


def bar(
    surface: pygame.Surface,
    rect: Tuple[int, int, int, int],
    fraction: float,
    color,
    track_color=TRACK,
) -> None:
    """A horizontal progress bar. Always draws the track, so an empty bar
    still shows the scale rather than disappearing."""
    x, y, w, h = rect
    fraction = _clamp01(fraction)
    pygame.draw.rect(surface, track_color, (x, y, w, h), border_radius=h // 2)
    if fraction > 0:
        pygame.draw.rect(
            surface, color,
            (x, y, max(h, int(w * fraction)), h),
            border_radius=h // 2,
        )


def sparkline(
    surface: pygame.Surface,
    rect: Tuple[int, int, int, int],
    values,
    color,
    width: int = 3,
) -> None:
    """A trend line. Silent on fewer than two points -- a one-point
    sparkline is a dot that implies a trend it cannot show."""
    x, y, w, h = rect
    points = [v for v in values if v is not None]
    if len(points) < 2:
        return

    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    step = w / (len(points) - 1)
    coords = [
        (int(x + i * step), int(y + h - ((v - lo) / span) * h))
        for i, v in enumerate(points)
    ]
    pygame.draw.lines(surface, color, False, coords, width)


def weather_glyph(surface: pygame.Surface, center, size: int, condition: str, color) -> None:
    """A sun, cloud, rain or storm mark chosen from the condition text.

    Matching on keywords rather than an icon code because the condition
    string is what the snapshot carries, and an unrecognised sky falls
    back to the sun rather than drawing nothing.
    """
    cx, cy = center
    text = (condition or "").lower()

    def cloud(offset_y: int = 0, tint=None):
        tint = tint or color
        base_y = cy + offset_y
        pygame.draw.circle(surface, tint, (cx - size // 3, base_y), size // 3)
        pygame.draw.circle(surface, tint, (cx + size // 4, base_y), size // 4)
        pygame.draw.circle(surface, tint, (cx, base_y - size // 5), size // 3)
        pygame.draw.rect(
            surface, tint,
            (cx - size // 3, base_y, int(size * 0.6), size // 3),
            border_radius=size // 8,
        )

    def sun(cx_=None, cy_=None, r=None, tint=None):
        cx_, cy_ = (cx if cx_ is None else cx_), (cy if cy_ is None else cy_)
        r = r or size // 3
        tint = tint or color
        pygame.draw.circle(surface, tint, (cx_, cy_), r)
        for i in range(8):
            angle = math.radians(i * 45)
            x1 = cx_ + int((r + size * 0.12) * math.cos(angle))
            y1 = cy_ + int((r + size * 0.12) * math.sin(angle))
            x2 = cx_ + int((r + size * 0.28) * math.cos(angle))
            y2 = cy_ + int((r + size * 0.28) * math.sin(angle))
            pygame.draw.line(surface, tint, (x1, y1), (x2, y2), max(2, size // 14))

    def drops(count: int, tint):
        for i in range(count):
            dx = cx - size // 3 + i * (size // 3)
            pygame.draw.line(
                surface, tint,
                (dx, cy + size // 2), (dx - size // 10, cy + int(size * 0.85)),
                max(2, size // 12),
            )

    if any(w in text for w in ("thunder", "storm", "lightning")):
        cloud(tint=DIM)
        pygame.draw.polygon(surface, color, [
            (cx, cy + size // 2),
            (cx - size // 6, cy + int(size * 0.9)),
            (cx + size // 20, cy + int(size * 0.82)),
            (cx - size // 12, cy + int(size * 1.15)),
            (cx + size // 5, cy + int(size * 0.72)),
            (cx + size // 30, cy + int(size * 0.78)),
        ])
    elif any(w in text for w in ("rain", "drizzle", "shower")):
        cloud(tint=DIM)
        drops(3, color)
    elif "snow" in text:
        cloud(tint=DIM)
        for i in range(3):
            dx = cx - size // 3 + i * (size // 3)
            pygame.draw.circle(surface, color, (dx, cy + int(size * 0.72)), max(2, size // 14))
    elif any(w in text for w in ("cloud", "overcast")):
        # Partly cloudy keeps a sun peeking out; fully overcast does not.
        if any(w in text for w in ("few", "scattered", "partly", "broken")):
            sun(cx + size // 3, cy - size // 3, size // 5)
        cloud(tint=DIM if "overcast" in text else color)
    elif any(w in text for w in ("mist", "fog", "haze", "smoke")):
        for i in range(3):
            y = cy - size // 4 + i * (size // 4)
            pygame.draw.line(surface, color, (cx - size // 2, y), (cx + size // 2, y),
                             max(2, size // 12))
    else:
        sun()
