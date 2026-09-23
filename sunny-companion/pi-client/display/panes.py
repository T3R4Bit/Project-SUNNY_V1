"""The rotating idle dashboard panes.

Each pane returns False when it has nothing worth showing, and the
rotation skips it. A pane that renders "no data" is worse than no pane:
it spends twelve seconds of a twelve-second cycle telling you nothing, on
a screen whose entire job is being glanceable from across the room.

LAYOUT
------
The panel is 800x480 in landscape. The first version of these panes was
written around a single left-aligned or centred column, which left
roughly the right-hand 40% of every screen empty while the content that
mattered -- what a task is due, what is on next -- was cut off or never
sent at all.

So panes use a two-column grid: one dominant thing on the left, its
supporting detail on the right. `_columns()` returns the two x-ranges and
panes compose within them, which keeps the proportions consistent from
pane to pane and stops each one inventing its own margins.

Vertical positions are fractions of the height rather than pixels, so the
same code lays out correctly if the panel is ever driven at a different
mode or the app runs unrotated on a monitor for debugging.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pygame

from display import graphics
from display.app import time_12h

BG = (10, 10, 10)
WHITE = (240, 240, 240)
DIM = (120, 120, 120)
FAINT = (70, 70, 78)
BLUE = (37, 150, 190)
PINK = (200, 15, 103)
YELLOW = (247, 209, 1)
ORANGE = (255, 140, 0)
GREEN = (60, 190, 120)

# Targets the bars are drawn against. A bar with no scale is just a
# coloured rectangle -- these are what make it mean something.
SLEEP_TARGET_HOURS = 8.0
STEP_TARGET = 10000
BODY_BATTERY_TARGET = 100.0


def _tone(fraction: float):
    """Blue when at or near target, orange when well short. Two states
    only -- a continuous gradient would imply a precision these targets
    do not have."""
    return BLUE if fraction >= 0.7 else ORANGE


def _due_label(due: Optional[str]) -> Tuple[str, tuple]:
    """A task's due date as a short label and a colour by urgency.

    Overdue and today are the two states worth shouting about; beyond
    that a weekday name is more use than a date, because "Fri" needs no
    arithmetic and "Sep 26" does.
    """
    if not due:
        return "", FAINT
    try:
        when = date.fromisoformat(due)
    except (TypeError, ValueError):
        return "", FAINT

    delta = (when - date.today()).days
    if delta < 0:
        return (f"{-delta}d late" if delta < -1 else "yesterday"), PINK
    if delta == 0:
        return "today", ORANGE
    if delta == 1:
        return "tomorrow", YELLOW
    if delta < 7:
        return when.strftime("%a"), DIM
    return f"{when.strftime('%b')} {when.day}", FAINT


class Panes:
    def __init__(self, display) -> None:
        self.d = display

    def _section(self, data: Dict, name: str) -> Optional[Dict]:
        return (data.get("sections") or {}).get(name)

    # --- layout helpers ---------------------------------------------------

    def _columns(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """((left_x, left_w), (right_x, right_w)).

        The split is 48/52 rather than even: the left column carries the
        headline number and reads better with a little less room than the
        detail list beside it, which needs the width for text.
        """
        d = self.d
        width = d.size[0]
        gutter = int(width * 0.04)
        left_w = int((width - d.pad * 2 - gutter) * 0.46)
        right_w = width - d.pad * 2 - gutter - left_w
        return (d.pad, left_w), (d.pad + left_w + gutter, right_w)

    def _divider(self, x: int) -> None:
        d = self.d
        top = int(d.size[1] * 0.17) + d.offset_y
        bottom = int(d.size[1] * 0.90) + d.offset_y
        pygame.draw.line(d.screen, (38, 38, 44), (x, top), (x, bottom), 1)

    def _body_top(self) -> int:
        """Where pane content starts, clear of the header."""
        return int(self.d.size[1] * 0.20)

    def _fit_font(self, text: str, max_width: int, start_ratio: float):
        """The largest font at or below `start_ratio` of the short edge
        that renders `text` within `max_width`.

        Needed because the display's font ladder is sized off the panel,
        not off the column a pane happens to draw into. f_huge at 0.40 of
        a 480px short edge renders "9:11 AM" about 500px wide, which
        overflowed the clock's left column and printed straight through
        the event list beside it. Fitting is better than hand-tuning a
        smaller constant, which only moves the cliff to a longer string.
        """
        short = min(self.d.size)
        ratio = start_ratio
        while ratio > 0.06:
            font = pygame.font.Font(None, max(12, int(short * ratio)))
            if font.size(text)[0] <= max_width:
                return font
            ratio -= 0.02
        return pygame.font.Font(None, max(12, int(short * 0.06)))

    def _chip(self, text: str, x: int, y: int, color) -> int:
        """A small outlined label. Returns its width.

        Categories and due dates are metadata, not content -- drawn as
        chips so they read as annotations on the row rather than as more
        words in the sentence.
        """
        d = self.d
        font = d.f_tiny
        surf = font.render(text, True, color)
        box = surf.get_rect()
        box.x, box.y = x + 6, y + 3 + d.offset_y
        ring = pygame.Rect(x, y + d.offset_y, box.width + 12, box.height + 6)
        pygame.draw.rect(d.screen, color, ring, width=1, border_radius=5)
        d.screen.blit(surf, box)
        return ring.width

    def _stat_row(self, x: int, y: int, width: int, label: str,
                  value: str, fraction: Optional[float]) -> int:
        """Label left, value right, optional target bar beneath. Returns
        the height consumed."""
        d = self.d
        d.text(label, d.f_small, DIM, x, y)
        value_w = d.f_small.size(value)[0]
        d.text(value, d.f_small, WHITE, x + width - value_w, y)

        consumed = int(d.f_small.get_height() * 1.15)
        if fraction is not None:
            bar_y = y + consumed + d.offset_y
            graphics.bar(d.screen, (x, bar_y, width, max(5, int(d.size[1] * 0.018))),
                         fraction, _tone(fraction))
            consumed += int(d.size[1] * 0.045)
        return consumed + int(d.size[1] * 0.035)

    # --- panes ------------------------------------------------------------

    def clock(self, data: Dict) -> bool:
        d = self.d
        # No stamp: the header's small "Sep 23 · 9:07 AM" sat directly
        # above the same time in huge type.
        d.header("SUNNY", BLUE, stamp=False)
        (lx, lw), (rx, rw) = self._columns()
        now = datetime.now()

        top = self._body_top()
        # Split the meridiem off: "AM" set at the same size as the digits
        # is both wider than the column allows and visually heavier than a
        # suffix deserves.
        stamp = time_12h(now)
        digits, _, meridiem = stamp.partition(" ")
        clock_font = self._fit_font(digits, lw, 0.40)

        surf = clock_font.render(digits, True, WHITE)
        d.screen.blit(surf, (lx, top + d.offset_y))
        if meridiem:
            d.text(meridiem, d.f_mid, DIM, lx + surf.get_width() + int(d.size[0] * 0.012),
                   top + int(surf.get_height() * 0.30))

        d.text(f"{now.strftime('%A, %B')} {now.day}", d.f_small, DIM,
               lx, top + int(d.size[1] * 0.42), max_width=lw)

        # The right column used to be empty. What is on next is the thing
        # most worth knowing beside the time, and it is already fetched.
        events = (self._section(data, "calendar") or {}).get("events") or []
        if events:
            self._divider(rx - int(d.size[0] * 0.02))
            d.text("NEXT UP", d.f_tiny, BLUE, rx, top)
            y = top + int(d.size[1] * 0.09)
            for event in events[:3]:
                d.text(event.get("time", ""), d.f_tiny, YELLOW, rx, y)
                y += int(d.size[1] * 0.055)
                y += d.text(event.get("title", ""), d.f_small, WHITE, rx, y,
                            max_width=rw) + int(d.size[1] * 0.045)
        # Always shows -- a clock is never "no data", and it is the pane
        # this screen falls back to when the server is unreachable.
        return True

    def calendar(self, data: Dict) -> bool:
        events = (self._section(data, "calendar") or {}).get("events") or []
        if not events:
            return False
        d = self.d
        d.header(f"TODAY · {len(events)}", YELLOW)

        # A fixed time column, so titles start on a common left edge
        # instead of stepping in and out with the length of each time.
        time_w = int(d.size[0] * 0.17)
        y = self._body_top()
        row_h = int(d.size[1] * 0.155)
        for event in events[:4]:
            d.text(event.get("time", ""), d.f_small, YELLOW, d.pad, y,
                   max_width=time_w)
            d.text(event.get("title", ""), d.f_mid, WHITE, d.pad + time_w, y - 4,
                   max_width=d.size[0] - d.pad * 2 - time_w)
            y += row_h
            if y > d.size[1] * 0.88:
                break
        return True

    def weather(self, data: Dict) -> bool:
        w = self._section(data, "weather")
        if not w or w.get("temp") is None:
            return False
        d = self.d
        d.header("WEATHER", BLUE)
        (lx, lw), (rx, rw) = self._columns()
        top = self._body_top()

        graphics.weather_glyph(
            d.screen,
            (lx + lw // 2, top + int(d.size[1] * 0.26) + d.offset_y),
            int(min(d.size) * 0.17), w.get("condition", ""), YELLOW,
        )

        d.text(f"{round(w['temp'])}°", d.f_huge, WHITE, rx, top - int(d.size[1] * 0.03))
        d.text(str(w.get("condition") or ""), d.f_small, BLUE, rx,
               top + int(d.size[1] * 0.40), max_width=rw)

        y = top + int(d.size[1] * 0.52)
        if w.get("humidity") is not None:
            y += self._stat_row(rx, y, rw, "Humidity", f"{w['humidity']}%", None)
        if w.get("pressure") is not None:
            self._stat_row(rx, y, rw, "Pressure", f"{round(w['pressure'])} hPa", None)
        return True

    def tasks(self, data: Dict) -> bool:
        t = self._section(data, "tasks")
        if not t or not t.get("items"):
            return False
        d = self.d
        items = t["items"]
        d.header(f"TASKS · {t.get('open', 0)} OPEN", PINK)

        # All five rows, not four. The header said "5 OPEN" while four
        # were listed, which makes the screen look like it is lying.
        y = self._body_top() - int(d.size[1] * 0.02)
        row_h = int(d.size[1] * 0.145)
        # Reserve room on the right for the due chip so long titles
        # truncate before they collide with it rather than overprinting.
        chip_zone = int(d.size[0] * 0.22)

        for item in items[:5]:
            due_text, due_color = _due_label(item.get("due_date"))
            title_w = d.size[0] - d.pad * 2 - (chip_zone if due_text else 0)

            pygame.draw.circle(d.screen, due_color if due_text else FAINT,
                               (d.pad + 4, y + int(d.f_small.get_height() * 0.55) + d.offset_y), 4)
            d.text(item.get("title", ""), d.f_small, WHITE, d.pad + 16, y,
                   max_width=title_w - 16)

            if due_text:
                width = d.f_tiny.size(due_text)[0] + 12
                self._chip(due_text, d.size[0] - d.pad - width, y, due_color)

            tag = item.get("tag") or ""
            if tag and tag.lower() != "general":
                self._chip(tag, d.pad + 16, y + int(d.size[1] * 0.06), FAINT)
                y += int(d.size[1] * 0.045)

            y += row_h
            if y > d.size[1] * 0.92:
                break
        return True

    def health(self, data: Dict) -> bool:
        h = self._section(data, "health")
        if not h:
            return False

        readiness = h.get("readiness")
        stats = [
            ("Sleep", h.get("sleep_hours"), "h", SLEEP_TARGET_HOURS),
            ("Steps", h.get("steps"), "", STEP_TARGET),
            ("Body battery", h.get("body_battery"), "", BODY_BATTERY_TARGET),
        ]
        stats = [s for s in stats if s[1] is not None]
        if readiness is None and not stats:
            return False

        d = self.d
        # The date this came from, when it isn't today's. A stale number
        # shown as current is worse than no number.
        label = "HEALTH"
        if h.get("as_of"):
            try:
                when = date.fromisoformat(h["as_of"])
                delta = (date.today() - when).days
                label = f"HEALTH · {'yesterday' if delta == 1 else when.strftime('%b ') + str(when.day)}"
            except (TypeError, ValueError):
                pass
        d.header(label, BLUE)

        (lx, lw), (rx, rw) = self._columns()
        top = self._body_top()

        if readiness is not None:
            fraction = readiness / 100.0
            radius = int(min(d.size) * 0.20)
            cx = lx + lw // 2
            cy = top + radius + int(d.size[1] * 0.06) + d.offset_y
            graphics.arc_gauge(d.screen, (cx, cy), radius, fraction, _tone(fraction))
            # Number inside the ring: the gauge shows proportion, the
            # figure shows the value, and separating them makes the eye
            # do work for nothing.
            number = f"{readiness:g}"
            surf = d.f_big.render(number, True, WHITE)
            d.screen.blit(surf, surf.get_rect(center=(cx, cy)))
            d.text("READINESS", d.f_tiny, DIM, cx,
                   cy - d.offset_y + radius + int(d.size[1] * 0.03), center=True)
            band = h.get("band")
            if band:
                d.text(band.upper(), d.f_tiny, _tone(fraction), cx,
                       cy - d.offset_y + radius + int(d.size[1] * 0.09), center=True)

        if stats:
            self._divider(rx - int(d.size[0] * 0.02))
            y = top
            for name, value, unit, target in stats:
                shown = f"{value:,.0f}{unit}" if float(value) >= 100 else f"{value:g}{unit}"
                y += self._stat_row(rx, y, rw, name, shown,
                                    float(value) / target if target else None)
        return True

    def usage(self, data: Dict) -> bool:
        u = self._section(data, "usage")
        if not u:
            return False
        d = self.d
        d.header("CLAUDE USAGE", YELLOW)
        (lx, lw), (rx, rw) = self._columns()
        top = self._body_top()

        d.text(f"${u.get('cost_today', 0):.2f}", d.f_huge, WHITE, lx, top)
        d.text("today", d.f_small, DIM, lx, top + int(d.size[1] * 0.42))

        self._divider(rx - int(d.size[0] * 0.02))
        y = top
        month = u.get("month_cost", 0)
        cap = u.get("month_cap") or 0
        y += self._stat_row(rx, y, rw, "This month", f"${month:.2f}",
                            (month / cap) if cap else None)
        if cap:
            y += self._stat_row(rx, y, rw, "Cap", f"${cap:.0f}", None)
        tokens = u.get("tokens_today")
        if tokens:
            self._stat_row(rx, y, rw, "Tokens today", f"{tokens:,}", None)
        return True

    def checkin(self, data: Dict) -> bool:
        c = self._section(data, "checkin")
        if not c or not c.get("question"):
            return False
        d = self.d
        d.header("CHECK-IN", PINK)
        top = self._body_top()
        d.text(c["question"], d.f_mid, WHITE, d.pad, top,
               max_width=d.size[0] - d.pad * 2)
        # Now that the panel takes touch, the tap is the faster answer and
        # should be what the prompt points at.
        d.text("tap the screen to answer · or say “hey sunny, no”",
               d.f_small, DIM, d.pad, top + int(d.size[1] * 0.30),
               max_width=d.size[0] - d.pad * 2)
        return True

    def all(self):
        """Rotation order: clock first because it is the one that always
        renders, then the things most likely to change through the day."""
        return [self.clock, self.calendar, self.weather, self.tasks,
                self.health, self.checkin, self.usage]
