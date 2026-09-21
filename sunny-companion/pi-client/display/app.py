#!/usr/bin/env python3
"""Sunny Companion display: rotating dashboard, animated face, notifications.

ONE PROCESS, NO BROWSER
-----------------------
This is a Pi 3 Model B with 905MB of RAM. A desktop session idles at
~350-450MB and Chromium wants another ~300-500MB on top, which leaves
nothing for the wake-word listener and audio. pygame costs ~60-80MB, so
the dashboard and the face are one pygame app rather than a browser
showing a web page with a separate renderer beside it.

It also means one process owns the screen. A browser for the dashboard
plus a pygame face would have to hand the display back and forth every
time you spoke, which is exactly the kind of thing that breaks at 2am.

NO X REQUIRED
-------------
SDL's kmsdrm driver renders straight to the display with no X server --
confirmed working at 480x800 on this hardware. The driver is auto-detected
so the same binary works whether or not a desktop happens to be running:
X11 when there's a DISPLAY to attach to, kmsdrm otherwise.

DEGRADING
---------
The server going away must not blank the screen. The last good snapshot
keeps rendering with a staleness marker, because a dashboard showing
slightly old data is useful and a black screen is not.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional

import pygame

logger = logging.getLogger("companion.display")

SUNNY_URL = os.environ.get("SUNNY_URL", "http://sunshine-m700.wahoo-sidewinder.ts.net:5000")
SNAPSHOT_INTERVAL = int(os.environ.get("SNAPSHOT_INTERVAL", "60"))
PANE_SECONDS = int(os.environ.get("PANE_SECONDS", "12"))
FPS = int(os.environ.get("FPS", "30"))

# Screen rotation in degrees, counter-clockwise, applied at present time.
#
# Done in software rather than in /boot/firmware/config.txt for two
# reasons: writing there needs a sudo password this account doesn't have
# passwordless, and a bad boot config leaves the panel dark until it's
# fixed physically. This is a one-line env change and a service restart.
#
# The trade is a rotate-and-blit per frame. pygame has a fast path for
# exact multiples of 90, so it is cheap, but see present() -- the
# dashboard doesn't need 30fps and drops its frame rate to pay for it.
ROTATE = int(os.environ.get("SCREEN_ROTATE", "90")) % 360

# Global type scale. The device is read from across a desk, not held, so
# the defaults below are already larger than a screen this size would
# normally carry -- this is for tuning without editing ratios.
UI_SCALE = float(os.environ.get("UI_SCALE", "1.0"))

# A snapshot older than this is marked stale on screen rather than shown
# as if it were current. Three missed polls -- enough to ride out one
# blip, short enough that you are never misled for long.
STALE_AFTER = SNAPSHOT_INTERVAL * 3

# How long a notification banner stays up. Long enough to read across the
# room, short enough that the dashboard isn't hidden for minutes.
NOTIFICATION_SECONDS = 25

BG = (10, 10, 10)
WHITE = (240, 240, 240)
DIM = (120, 120, 120)
BLUE = (37, 150, 190)
PINK = (200, 15, 103)
YELLOW = (247, 209, 1)
ORANGE = (255, 140, 0)


def time_12h(when: Optional[datetime] = None) -> str:
    """"4:17 PM" -- 12-hour with no leading zero.

    Built by hand rather than with %-I (glibc-only) or %#I (Windows-only):
    this is developed on one platform and runs on another, and a strftime
    that raises on the wrong OS is a silly way to lose a display.
    """
    when = when or datetime.now()
    hour = when.hour % 12 or 12
    return f"{hour}:{when.minute:02d} {when.strftime('%p')}"


def _pick_driver() -> str:
    """Use whatever display path exists.

    X11 when a desktop session is running (DISPLAY is set), kmsdrm
    otherwise. Auto-detecting rather than hardcoding means enabling or
    disabling the desktop doesn't require touching this file -- the app
    is not the thing that should care.
    """
    if os.environ.get("SDL_VIDEODRIVER"):
        return os.environ["SDL_VIDEODRIVER"]
    if os.environ.get("DISPLAY"):
        return "x11"
    return "kmsdrm"


class Snapshot:
    """The last good server state, and how old it is.

    Holds onto the previous payload on failure instead of clearing: a
    dashboard showing four-minute-old weather is useful, a blank one is
    not, and the staleness marker keeps it honest.
    """

    def __init__(self) -> None:
        self.data: Dict = {}
        self.fetched_at: float = 0.0
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    def update(self, data: Dict) -> None:
        with self._lock:
            self.data = data
            self.fetched_at = time.time()
            self.error = None

    def fail(self, message: str) -> None:
        with self._lock:
            self.error = message

    def read(self):
        with self._lock:
            return dict(self.data), self.fetched_at, self.error

    @property
    def stale(self) -> bool:
        return self.fetched_at > 0 and (time.time() - self.fetched_at) > STALE_AFTER

    @property
    def never_loaded(self) -> bool:
        return self.fetched_at == 0


class Notifications:
    """Incoming notification banners, newest first."""

    def __init__(self) -> None:
        self.queue: deque = deque(maxlen=5)
        self.shown_at: float = 0.0
        self._lock = threading.Lock()

    def push(self, title: str, body: str) -> None:
        with self._lock:
            self.queue.appendleft({"title": title, "body": body, "at": time.time()})
            self.shown_at = time.time()

    def current(self) -> Optional[Dict]:
        with self._lock:
            if not self.queue:
                return None
            if time.time() - self.shown_at > NOTIFICATION_SECONDS:
                self.queue.popleft()
                self.shown_at = time.time()
                return self.queue[0] if self.queue else None
            return self.queue[0]

    def dismiss(self) -> None:
        with self._lock:
            if self.queue:
                self.queue.popleft()
            self.shown_at = time.time()


def poll_snapshot(snapshot: Snapshot, stop: threading.Event) -> None:
    """Background poller. Runs in a thread so a slow or hung request can
    never stall the render loop -- a frozen screen reads as a crashed
    device even when only the network is at fault."""
    import urllib.error
    import urllib.request

    while not stop.is_set():
        try:
            with urllib.request.urlopen(f"{SUNNY_URL}/api/companion/snapshot", timeout=10) as r:
                snapshot.update(json.loads(r.read().decode("utf-8")))
        except Exception as e:
            snapshot.fail(f"{type(e).__name__}")
            logger.warning(f"Snapshot fetch failed: {e}")
        stop.wait(SNAPSHOT_INTERVAL)


class Display:
    def __init__(self) -> None:
        driver = _pick_driver()
        os.environ.setdefault("SDL_VIDEODRIVER", driver)
        pygame.init()
        pygame.mouse.set_visible(False)

        info = pygame.display.Info()
        physical = (info.current_w, info.current_h)
        self.physical = pygame.display.set_mode(physical, pygame.FULLSCREEN)
        pygame.display.set_caption("Sunny Companion")

        # Everything draws onto `canvas` at the LOGICAL size; present()
        # rotates it onto the physical panel. A 90 or 270 rotation swaps
        # width and height, so panes lay themselves out for the orientation
        # you actually see rather than the one the panel reports.
        self.rotate = ROTATE
        self.size = (physical[1], physical[0]) if self.rotate in (90, 270) else physical
        self.canvas = pygame.Surface(self.size)
        self.screen = self.canvas

        logger.info(
            f"Display up: {driver} panel {physical[0]}x{physical[1]} "
            f"-> logical {self.size[0]}x{self.size[1]} (rotate {self.rotate})"
        )

        # Scale type to the panel rather than hardcoding sizes -- the same
        # code has to look right on a 480x800 portrait panel and on a
        # monitor if one is ever plugged in for debugging.
        # Scaled off the SHORT edge so a rotation doesn't resize the type,
        # and sized for reading at desk distance rather than phone
        # distance -- this panel is 4.3", but it is two feet away and
        # never touched, so everything is deliberately oversized.
        short = min(self.size)

        def font(ratio: float):
            return pygame.font.Font(None, max(12, int(short * ratio * UI_SCALE)))

        self.f_huge = font(0.40)
        self.f_big = font(0.20)
        self.f_mid = font(0.105)
        self.f_small = font(0.072)
        self.f_tiny = font(0.052)

        # Vertical offset applied to everything a pane draws. The
        # notification banner sits at the top of the screen, and without
        # this a pane's first rows render underneath it -- confirmed on
        # the real panel, where the calendar's first event was hidden
        # behind a banner. Panes stay offset-unaware; this shifts them.
        self.offset_y = 0

        # Side margin, proportional rather than a fixed 18px -- the same
        # gutter has to look right at 480 wide and on a larger panel.
        self.pad = int(self.size[0] * 0.035)

    def present(self) -> None:
        """Push the canvas to the panel, rotating if needed.

        Called once per frame instead of pygame.display.flip(). When
        rotation is off this is a straight blit, so the unrotated path
        costs nothing extra.
        """
        if self.rotate:
            self.physical.blit(pygame.transform.rotate(self.canvas, self.rotate), (0, 0))
        else:
            self.physical.blit(self.canvas, (0, 0))
        pygame.display.flip()

    def text(self, surface_text, font, color, x, y, center=False, max_width=None):
        if max_width:
            surface_text = self._truncate(surface_text, font, max_width)
        surf = font.render(surface_text, True, color)
        rect = surf.get_rect()
        if center:
            rect.centerx = x
        else:
            rect.x = x
        rect.y = y + self.offset_y
        self.screen.blit(surf, rect)
        return rect.height

    def _truncate(self, value: str, font, max_width: int) -> str:
        if font.size(value)[0] <= max_width:
            return value
        while value and font.size(value + "…")[0] > max_width:
            value = value[:-1]
        return value + "…"

    def header(self, label: str, color):
        """Pane title on the left, date and time on the right.

        Uses f_small rather than f_tiny: this is read at desk distance,
        and the date in particular is the kind of thing you glance at
        rather than lean in for.
        """
        pygame.draw.rect(
            self.screen, color,
            (0, self.offset_y, self.size[0], max(4, int(self.size[1] * 0.020))),
        )
        y = int(self.size[1] * 0.052)
        self.text(label, self.f_small, color, self.pad, y)

        now = datetime.now()
        # .day rather than %-d/%#d, for the same portability reason as
        # time_12h above.
        stamp = f"{now.strftime('%b')} {now.day} · {time_12h(now)}"
        self.text(stamp, self.f_small, DIM,
                  self.size[0] - self.pad - self.f_small.size(stamp)[0], y)
