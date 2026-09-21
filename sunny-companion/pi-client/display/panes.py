"""The rotating idle dashboard panes.

Each pane returns False when it has nothing worth showing, and the
rotation skips it. A pane that renders "no data" is worse than no pane:
it spends twelve seconds of a twelve-second cycle telling you nothing, on
a screen whose entire job is being glanceable from across the room.
"""

from datetime import datetime
from typing import Dict, Optional

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
        d.text(now.strftime("%H:%M"), d.f_huge, WHITE, d.size[0] // 2,
               int(d.size[1] * 0.28), center=True)
        d.text(now.strftime("%A, %B %d"), d.f_small, DIM, d.size[0] // 2,
               int(d.size[1] * 0.52), center=True)

        health = self._section(data, "health") or {}
        if health.get("readiness") is not None:
            d.text(f"Readiness {health['readiness']}", d.f_mid, BLUE, d.size[0] // 2,
                   int(d.size[1] * 0.63), center=True)
        # Always shows -- a clock is never "no data", and it is the pane
        # this screen falls back to when the server is unreachable.
        return True

    def calendar(self, data: Dict) -> bool:
        events = (self._section(data, "calendar") or {}).get("events") or []
        if not events:
            return False
        d = self.d
        d.header("TODAY", YELLOW)
        y = int(d.size[1] * 0.11)
        for event in events[:5]:
            d.text(event.get("time", ""), d.f_small, YELLOW, 18, y)
            y += int(d.size[1] * 0.045)
            y += d.text(event.get("title", ""), d.f_mid, WHITE, 18, y,
                        max_width=d.size[0] - 36) + int(d.size[1] * 0.022)
        return True

    def weather(self, data: Dict) -> bool:
        w = self._section(data, "weather")
        if not w or w.get("temp") is None:
            return False
        d = self.d
        d.header("WEATHER", BLUE)
        d.text(f"{round(w['temp'])}°", d.f_huge, WHITE, d.size[0] // 2,
               int(d.size[1] * 0.20), center=True)
        d.text(str(w.get("condition") or ""), d.f_mid, BLUE, d.size[0] // 2,
               int(d.size[1] * 0.48), center=True, max_width=d.size[0] - 30)
        bits = []
        if w.get("humidity") is not None:
            bits.append(f"{w['humidity']}% humidity")
        if w.get("pressure") is not None:
            bits.append(f"{round(w['pressure'])} hPa")
        if bits:
            d.text(" · ".join(bits), d.f_small, DIM, d.size[0] // 2,
                   int(d.size[1] * 0.60), center=True)
        return True

    def tasks(self, data: Dict) -> bool:
        t = self._section(data, "tasks")
        if not t or not t.get("items"):
            return False
        d = self.d
        d.header(f"TASKS · {t.get('open', 0)} OPEN", PINK)
        y = int(d.size[1] * 0.11)
        for item in t["items"][:5]:
            y += d.text("• " + item.get("title", ""), d.f_mid, WHITE, 18, y,
                        max_width=d.size[0] - 36) + int(d.size[1] * 0.028)
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
        y = int(d.size[1] * 0.13)
        for label, value, unit in rows:
            shown = f"{value:,.0f}{unit}" if float(value) >= 100 else f"{value:g}{unit}"
            d.text(label, d.f_small, DIM, 18, y)
            d.text(shown, d.f_big, WHITE, 18, y + int(d.size[1] * 0.040))
            y += int(d.size[1] * 0.20)
        return True

    def usage(self, data: Dict) -> bool:
        u = self._section(data, "usage")
        if not u:
            return False
        d = self.d
        d.header("CLAUDE USAGE", YELLOW)
        d.text(f"${u.get('cost_today', 0):.2f}", d.f_huge, WHITE, d.size[0] // 2,
               int(d.size[1] * 0.20), center=True)
        d.text("today", d.f_small, DIM, d.size[0] // 2, int(d.size[1] * 0.48), center=True)
        d.text(f"${u.get('month_cost', 0):.2f} this month", d.f_mid, YELLOW, d.size[0] // 2,
               int(d.size[1] * 0.60), center=True)
        return True

    def checkin(self, data: Dict) -> bool:
        c = self._section(data, "checkin")
        if not c or not c.get("question"):
            return False
        d = self.d
        d.header("CHECK-IN", PINK)
        d.text(c["question"], d.f_mid, WHITE, d.size[0] // 2, int(d.size[1] * 0.36),
               center=True, max_width=d.size[0] - 30)
        d.text("say “hey sunny, no”", d.f_small, DIM, d.size[0] // 2,
               int(d.size[1] * 0.54), center=True)
        return True

    def all(self):
        """Rotation order: clock first because it is the one that always
        renders, then the things most likely to change through the day."""
        return [self.clock, self.calendar, self.weather, self.tasks,
                self.health, self.checkin, self.usage]
