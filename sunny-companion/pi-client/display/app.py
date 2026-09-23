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

# How the touch panel is mounted relative to the framebuffer. Video
# reaches this screen over HDMI and touch over SPI from an ADS7846;
# nothing makes the two agree about orientation, and on this unit they do
# not -- config.txt drives 480x800 portrait timings on glass that is
# natively 800x480 landscape, with swapxy off in the overlay.
#
# Measured rather than assumed: calibrate.py scores all eight possible
# mountings against four real taps and prints the winner. Defaults are the
# identity mapping, so an uncalibrated unit behaves exactly as before
# rather than mysteriously differently.
TOUCH_SWAP = os.environ.get("TOUCH_SWAP", "0") == "1"
TOUCH_FLIP_X = os.environ.get("TOUCH_FLIP_X", "0") == "1"
TOUCH_FLIP_Y = os.environ.get("TOUCH_FLIP_Y", "0") == "1"

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


def fetch_snapshot_once(snapshot: Snapshot) -> None:
    """One snapshot fetch. Split out of the poll loop so the menu's
    Refresh button can force an update without either waiting out the
    interval or starting a second permanent poller."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{SUNNY_URL}/api/companion/snapshot", timeout=10) as r:
            snapshot.update(json.loads(r.read().decode("utf-8")))
    except Exception as e:
        snapshot.fail(f"{type(e).__name__}")
        logger.warning(f"Snapshot fetch failed: {e}")


def poll_snapshot(snapshot: Snapshot, stop: threading.Event) -> None:
    """Background poller. Runs in a thread so a slow or hung request can
    never stall the render loop -- a frozen screen reads as a crashed
    device even when only the network is at fault."""
    while not stop.is_set():
        fetch_snapshot_once(snapshot)
        stop.wait(SNAPSHOT_INTERVAL)


def fetch_checkin() -> Optional[Dict]:
    """Today's unanswered check-in question, or None.

    Its own request rather than a field on the snapshot: the snapshot is
    polled once a minute and cached, and an answer logged from the panel
    has to disappear from the menu immediately rather than up to a minute
    later. Called when the menu opens, not per frame.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(f"{SUNNY_URL}/api/checkin/pending", timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Check-in fetch failed: {type(e).__name__}")
        return None


def post_checkin_answer(question_id: str, answer: str, day: Optional[str] = None) -> bool:
    """Log an answer. True on success.

    The server returns 422 for an answer it cannot parse rather than
    storing a zero, so a False here means the answer genuinely did not
    land and the caller must say so -- silently showing "logged" for a
    rejected answer would leave a gap in the history that looks like a
    day the question was never asked.
    """
    import urllib.request

    payload = {"question_id": question_id, "answer": answer}
    if day:
        payload["day"] = day
    request = urllib.request.Request(
        f"{SUNNY_URL}/api/checkin/answer",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            return r.status == 200
    except Exception as e:
        logger.warning(f"Check-in answer failed: {type(e).__name__}")
        return False


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

    def to_canvas(self, px: int, py: int):
        """Map a touch from PANEL coordinates to CANVAS coordinates.

        Rotating the display does not rotate the touchscreen. The ADS7846
        reports where a finger landed on the physical panel, which after a
        90 degree rotation is nowhere near the pixel the user was aiming
        at -- taps land along the wrong axis entirely, and the failure
        looks like "touch is broken" rather than "touch is rotated".

        present() draws with pygame.transform.rotate, which turns
        COUNTER-clockwise for a positive angle. This is exactly its
        inverse, so the two have to be changed together:

            rotate 90:  canvas(x,y) -> panel(y, cw-1-x)
            so          panel(px,py) -> canvas(cw-1-py, px)

        Returns a plain (x, y) tuple in canvas space. Coordinates are
        clamped rather than rejected when out of range: a resistive panel
        reports the odd reading a pixel or two past the edge, and dropping
        those would silently eat taps aimed at a button on the border.
        """
        cw, ch = self.size
        if self.rotate == 90:
            x, y = cw - 1 - py, px
        elif self.rotate == 270:
            x, y = py, ch - 1 - px
        elif self.rotate == 180:
            x, y = cw - 1 - px, ch - 1 - py
        else:
            x, y = px, py
        return max(0, min(cw - 1, int(x))), max(0, min(ch - 1, int(y)))

    def touch_point(self, event):
        """Canvas coordinates for a pygame touch or mouse event, or None.

        SDL delivers this panel two ways at once under kmsdrm: real
        FINGERDOWN events (normalized 0..1 against the panel) and
        synthesized mouse clicks (already in pixels). Both are accepted so
        the menu works whether SDL's evdev backend decides this is a
        touchscreen or a mouse, and a keyboard/mouse plugged in for
        debugging keeps working too.
        """
        pw, ph = self.physical.get_size()

        if event.type == pygame.FINGERDOWN:
            # SDL normalizes against the ADS7846's own ABS ranges, so these
            # are 0..1 along the TOUCH axes, which are not necessarily the
            # framebuffer's axes. Orient first, scale second -- scaling by
            # the wrong edge length before swapping would squash the
            # reading into the wrong aspect and no later fix recovers it.
            nx, ny = event.x, event.y
            if TOUCH_SWAP:
                nx, ny = ny, nx
            if TOUCH_FLIP_X:
                nx = 1.0 - nx
            if TOUCH_FLIP_Y:
                ny = 1.0 - ny
            return self.to_canvas(nx * pw, ny * ph)

        if event.type == pygame.MOUSEBUTTONDOWN:
            # Already in framebuffer pixels. A real mouse needs no
            # reorientation, but SDL also synthesizes these from the
            # touchscreen, in which case it has applied its own mapping
            # and the same correction applies.
            x, y = event.pos
            if TOUCH_SWAP:
                x, y = y * (pw / ph), x * (ph / pw)
            if TOUCH_FLIP_X:
                x = pw - 1 - x
            if TOUCH_FLIP_Y:
                y = ph - 1 - y
            return self.to_canvas(x, y)

        return None

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

    def header(self, label: str, color, stamp: bool = True):
        """Pane title on the left, date and time on the right.

        Uses f_small rather than f_tiny: this is read at desk distance,
        and the date in particular is the kind of thing you glance at
        rather than lean in for.

        stamp=False drops the date/time. The clock pane passes it: showing
        "Sep 23 · 9:07 AM" in 20px type directly above 9:07 AM in 80px
        type is the same fact twice, and the small copy is the one that
        adds nothing.
        """
        pygame.draw.rect(
            self.screen, color,
            (0, self.offset_y, self.size[0], max(4, int(self.size[1] * 0.020))),
        )
        y = int(self.size[1] * 0.052)
        self.text(label, self.f_small, color, self.pad, y)

        if not stamp:
            return
        now = datetime.now()
        # .day rather than %-d/%#d, for the same portability reason as
        # time_12h above.
        text = f"{now.strftime('%b')} {now.day} · {time_12h(now)}"
        self.text(text, self.f_small, DIM,
                  self.size[0] - self.pad - self.f_small.size(text)[0], y)
