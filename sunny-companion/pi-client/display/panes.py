"""The rotating idle dashboard panes.

Each pane returns False when it has nothing worth showing, and the
rotation skips it. A pane that renders "no data" is worse than no pane:
it spends twelve seconds of a twelve-second cycle telling you nothing, on
a screen whose entire job is being glanceable from across the room.
"""

from datetime import datetime
from typing import Dict, Optional

from display.app import time_12h

BG = (10, 10, 10)
WHITE = (240, 240, 240)
DIM = (120, 120, 120)
BLUE = (37, 150, 190)
PINK = (200, 15, 103)
YELLOW = (247, 209, 1)


class Panes:
    def __init__(self, display) -> None:
        self.d = display

    def _section(self, data: Dict, name: str) -> Optional[Dict]:
        return (data.get("sections") or {}).get(name)

    # --- panes ------------------------------------------------------------

    def clock(self, data: Dict) -> bool:
        d = self.d
        d.header("SUNNY", BLUE)
        now = datetime.now()
        d.text(time_12h(now), d.f_huge, WHITE, d.size[0] // 2,
               int(d.size[1] * 0.18), center=True)
        d.text(f"{now.strftime('%A, %B')} {now.day}", d.f_small, DIM, d.size[0] // 2,
               int(d.size[1] * 0.60), center=True)

        health = self._section(data, "health") or {}
        if health.get("readiness") is not None:
            d.text(f"Readiness {health['readiness']}", d.f_mid, BLUE, d.size[0] // 2,
                   int(d.size[1] * 0.76), center=True)
        # Always shows -- a clock is never "no data", and it is the pane
        # this screen falls back to when the server is unreachable.
        return True

    def calendar(self, data: Dict) -> bool:
        events = (self._section(data, "calendar") or {}).get("events") or []
        if not events:
            return False
        d = self.d
        d.header("TODAY", YELLOW)
        # Fewer rows than before: the type is much larger now, and three
        # readable events beat five that need squinting at.
        y = int(d.size[1] * 0.15)
        for event in events[:3]:
            d.text(event.get("time", ""), d.f_small, YELLOW, d.pad, y)
            y += int(d.size[1] * 0.085)
            y += d.text(event.get("title", ""), d.f_mid, WHITE, d.pad, y,
                        max_width=d.size[0] - d.pad * 2) + int(d.size[1] * 0.045)
        return True

    def weather(self, data: Dict) -> bool:
        w = self._section(data, "weather")
        if not w or w.get("temp") is None:
            return False
        d = self.d
        d.header("WEATHER", BLUE)
        d.text(f"{round(w['temp'])}°", d.f_huge, WHITE, d.size[0] // 2,
               int(d.size[1] * 0.16), center=True)
        d.text(str(w.get("condition") or ""), d.f_mid, BLUE, d.size[0] // 2,
               int(d.size[1] * 0.58), center=True, max_width=d.size[0] - d.pad * 2)
        bits = []
        if w.get("humidity") is not None:
            bits.append(f"{w['humidity']}% humidity")
        if w.get("pressure") is not None:
            bits.append(f"{round(w['pressure'])} hPa")
        if bits:
            d.text(" · ".join(bits), d.f_small, DIM, d.size[0] // 2,
                   int(d.size[1] * 0.78), center=True)
        return True

    def tasks(self, data: Dict) -> bool:
        t = self._section(data, "tasks")
        if not t or not t.get("items"):
            return False
        d = self.d
        d.header(f"TASKS · {t.get('open', 0)} OPEN", PINK)
        y = int(d.size[1] * 0.16)
        for item in t["items"][:4]:
            y += d.text("• " + item.get("title", ""), d.f_mid, WHITE, d.pad, y,
                        max_width=d.size[0] - d.pad * 2) + int(d.size[1] * 0.055)
        return True

    def health(self, data: Dict) -> bool:
        h = self._section(data, "health")
        if not h:
            return False
        rows = [
            ("Readiness", h.get("readiness"), ""),
            ("Sleep", h.get("sleep_hours"), " h"),
            ("Steps", h.get("steps"), ""),
        ]
        rows = [(label, value, unit) for label, value, unit in rows if value is not None]
        if not rows:
            return False

        d = self.d
        d.header("HEALTH", BLUE)

        def shown(value, unit):
            return f"{value:,.0f}{unit}" if float(value) >= 100 else f"{value:g}{unit}"

        if d.size[0] > d.size[1]:
            # Landscape: three stats side by side. Stacked vertically they
            # used a narrow left column and left most of an 800px-wide
            # screen empty, which is the wrong shape for the panel.
            column = d.size[0] // len(rows)
            y = int(d.size[1] * 0.30)
            for i, (label, value, unit) in enumerate(rows):
                cx = column * i + column // 2
                d.text(label, d.f_small, DIM, cx, y, center=True)
                d.text(shown(value, unit), d.f_big, WHITE, cx,
                       y + int(d.size[1] * 0.11), center=True,
                       max_width=column - d.pad)
        else:
            y = int(d.size[1] * 0.16)
            for label, value, unit in rows:
                d.text(label, d.f_small, DIM, d.pad, y)
                d.text(shown(value, unit), d.f_big, WHITE, d.pad, y + int(d.size[1] * 0.075))
                y += int(d.size[1] * 0.27)
        return True

    def usage(self, data: Dict) -> bool:
        u = self._section(data, "usage")
        if not u:
            return False
        d = self.d
        d.header("CLAUDE USAGE", YELLOW)
        d.text(f"${u.get('cost_today', 0):.2f}", d.f_huge, WHITE, d.size[0] // 2,
               int(d.size[1] * 0.16), center=True)
        d.text("today", d.f_small, DIM, d.size[0] // 2, int(d.size[1] * 0.58), center=True)
        d.text(f"${u.get('month_cost', 0):.2f} this month", d.f_mid, YELLOW, d.size[0] // 2,
               int(d.size[1] * 0.76), center=True)
        return True

    def checkin(self, data: Dict) -> bool:
        c = self._section(data, "checkin")
        if not c or not c.get("question"):
            return False
        d = self.d
        d.header("CHECK-IN", PINK)
        d.text(c["question"], d.f_mid, WHITE, d.size[0] // 2, int(d.size[1] * 0.34),
               center=True, max_width=d.size[0] - d.pad * 2)
        d.text("say “hey sunny, no”", d.f_small, DIM, d.size[0] // 2,
               int(d.size[1] * 0.62), center=True)
        return True

    def all(self):
        """Rotation order: clock first because it is the one that always
        renders, then the things most likely to change through the day."""
        return [self.clock, self.calendar, self.weather, self.tasks,
                self.health, self.checkin, self.usage]
