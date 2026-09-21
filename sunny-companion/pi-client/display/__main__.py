"""Entry point: `python3 -m display` on the Pi.

Ties the pieces together -- the snapshot poller, the rotating panes, the
face, and the notification banner -- into one render loop that owns the
screen.

TWO SOURCES, TWO CADENCES
-------------------------
Dashboard data is PULLED on a slow timer, because it changes on the order
of minutes and a poll that fails is harmless. Notifications are PUSHED
over the companion WebSocket, because a reminder that arrives a minute
late has already failed at its job.

Both run in background threads. The render loop never blocks on the
network: a frozen screen reads as a dead device even when only WiFi is
at fault, and this thing sits on a desk where that distinction matters.
"""

import json
import logging
import os
import sys
import threading
import time

import pygame

from display.app import (
    BG, BLUE, DIM, FPS, ORANGE, PANE_SECONDS, PINK, SUNNY_URL, WHITE, YELLOW,
    Display, Notifications, Snapshot, poll_snapshot,
)
from display.face import Face
from display.panes import Panes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("companion")

# How long the face stays up after the last activity before the dashboard
# comes back. Long enough that a pause mid-sentence doesn't flip the
# screen away, short enough that an abandoned conversation doesn't leave
# a static face there for minutes.
FACE_LINGER_SECONDS = 8

# Frame rate while showing the dashboard. Text that changes once a minute
# does not need 30fps, and this is a four-core 1.2GHz board that also runs
# wake-word detection.
IDLE_FPS = int(os.environ.get("IDLE_FPS", "4"))

# Share of the screen the notification banner takes. Defined once because
# the banner height and the offset panes are pushed down by must agree --
# when they drifted apart, pane content rendered underneath the banner.
BANNER_FRACTION = 0.42

# Debug capture, off unless asked for. See the render loop for why reading
# /dev/fb0 does not work under kmsdrm.
SCREENSHOT_PATH = os.environ.get("SCREENSHOT_PATH", "")
SCREENSHOT_AFTER = float(os.environ.get("SCREENSHOT_AFTER", "5"))
SCREENSHOT_EXIT = os.environ.get("SCREENSHOT_EXIT", "") == "1"


class Companion:
    def __init__(self) -> None:
        self.display = Display()
        self.panes = Panes(self.display)
        self.face = Face(self.display)
        self.snapshot = Snapshot()
        self.notifications = Notifications()
        self.stop = threading.Event()

        self.state = "idle"
        self.last_activity = 0.0
        self.pane_index = 0
        self.pane_started = time.time()
        self._started = time.time()

    # --- background ------------------------------------------------------

    def start_threads(self) -> None:
        threading.Thread(
            target=poll_snapshot, args=(self.snapshot, self.stop), daemon=True
        ).start()
        threading.Thread(target=self._listen_events, daemon=True).start()

    def _listen_events(self) -> None:
        """Hold the companion WebSocket open for pushed notifications and
        pipeline state.

        Reconnects forever with a capped backoff. The server restarts
        (deploys, reboots) and WiFi drops; a device that gives up after a
        few tries is a device that is silently dead by morning.
        """
        try:
            from websockets.sync.client import connect
        except ImportError:
            logger.warning("websockets not installed — notifications and face states disabled")
            return

        url = SUNNY_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/pi"
        backoff = 2

        while not self.stop.is_set():
            try:
                with connect(url, open_timeout=10) as ws:
                    logger.info("Connected to Sunny")
                    backoff = 2
                    while not self.stop.is_set():
                        raw = ws.recv()
                        if isinstance(raw, bytes):
                            # Audio frames belong to the voice worker, not
                            # the display. Ignored rather than treated as
                            # an error.
                            continue
                        self._handle_event(json.loads(raw))
            except Exception as e:
                logger.warning(f"Socket closed ({type(e).__name__}) — retrying in {backoff}s")
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60)

    def _handle_event(self, event: dict) -> None:
        if event.get("type") == "notification":
            self.notifications.push(event.get("title", "Sunny"), event.get("body", ""))
            logger.info(f"Notification: {event.get('title')} — {event.get('body')}")
            return

        state = event.get("state")
        if state:
            self.state = state
            self.face.set_state(state)
            self.last_activity = time.time()

    # --- rendering -------------------------------------------------------

    def _draw_banner(self, note: dict) -> None:
        d = self.display
        w, h = d.size
        height = int(h * BANNER_FRACTION)
        pygame.draw.rect(d.screen, (26, 26, 26), (0, 0, w, height))
        pygame.draw.rect(d.screen, PINK, (0, 0, w, max(4, int(h * 0.014))))

        d.text("NOTIFICATION", d.f_tiny, PINK, d.pad, int(h * 0.055))
        y = int(h * 0.13)
        y += d.text(note.get("title", ""), d.f_big, WHITE, d.pad, y, max_width=w - d.pad * 2)
        if note.get("body"):
            d.text(note["body"], d.f_mid, DIM, d.pad, y + int(h * 0.02),
                   max_width=w - d.pad * 2)

    def _draw_status(self) -> None:
        # Absolute position: the footer is chrome, not pane content.
        """A one-line footer about the connection, only when something is
        wrong. A permanent "connected" badge is noise; the absence of a
        warning is the signal."""
        data, fetched_at, error = self.snapshot.read()
        d = self.display
        message, color = None, DIM

        if self.snapshot.never_loaded:
            message, color = "waiting for Sunny…", DIM
        elif self.snapshot.stale:
            age = int((time.time() - fetched_at) / 60)
            message, color = f"data {age} min old · {error or 'no connection'}", ORANGE

        if message:
            d.offset_y = 0
            d.text(message, d.f_tiny, color, d.size[0] // 2,
                   d.size[1] - int(d.size[1] * 0.045), center=True)

    def _advance_pane(self, data: dict) -> None:
        panes = self.panes.all()
        if time.time() - self.pane_started < PANE_SECONDS:
            return
        # Skip panes with nothing to show. Bounded by the pane count so an
        # empty snapshot can't spin forever looking for a renderable one.
        for _ in range(len(panes)):
            self.pane_index = (self.pane_index + 1) % len(panes)
            if self._pane_has_content(panes[self.pane_index], data):
                break
        self.pane_started = time.time()

    def _pane_has_content(self, pane, data: dict) -> bool:
        # Probing by rendering to the real surface would flicker, so this
        # asks the pane against a throwaway surface first.
        saved = self.display.screen
        self.display.screen = pygame.Surface(self.display.size)
        try:
            return bool(pane(data))
        except Exception:
            return False
        finally:
            self.display.screen = saved

    def run(self) -> None:
        clock = pygame.time.Clock()
        self.start_threads()

        while True:
            # The face animates; the dashboard is static text that changes
            # once a minute. Running both at 30fps on a Pi 3B spends most
            # of the CPU rotating identical frames, so idle drops to a
            # tenth of that. Rotation happens per frame, so this is where
            # its cost is actually paid or avoided.
            talking_now = (time.time() - self.last_activity) < FACE_LINGER_SECONDS
            dt = clock.tick(FPS if talking_now else IDLE_FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        return
                    # Any other key dismisses a banner -- the device has no
                    # touchscreen input wired up, but a keyboard is often
                    # plugged in while working on it.
                    self.notifications.dismiss()

            data, _, _ = self.snapshot.read()
            self.display.screen.fill(BG)

            # Push pane content below the banner when one is up, so the
            # first rows aren't drawn underneath it. Read before rendering
            # so the offset and the banner always agree about whether
            # there is one.
            note = self.notifications.current()
            self.display.offset_y = int(self.display.size[1] * BANNER_FRACTION) if note else 0

            talking = (time.time() - self.last_activity) < FACE_LINGER_SECONDS
            if talking and self.state != "idle":
                self.face.draw(dt)
            else:
                if self.state != "idle":
                    self.state = "idle"
                    self.face.set_state("idle")
                self._advance_pane(data)
                panes = self.panes.all()
                try:
                    if not panes[self.pane_index](data):
                        panes[0](data)  # clock always renders
                except Exception as e:
                    logger.error(f"Pane render failed: {e}", exc_info=True)
                    panes[0](data)

            # Banner last so it sits above whatever is behind it, and
            # drawn at absolute coordinates rather than offset ones.
            if note:
                self.display.offset_y = 0
                self._draw_banner(note)

            self._draw_status()
            self.display.present()

            # Debug capture. kmsdrm renders straight to the DRM plane and
            # never touches /dev/fb0, so reading the framebuffer shows the
            # old console rather than this app -- the only way to see what
            # is actually on screen from an SSH session is for the app to
            # save its own surface.
            if SCREENSHOT_PATH and time.time() - self._started > SCREENSHOT_AFTER:
                try:
                    pygame.image.save(self.display.physical, SCREENSHOT_PATH)
                    logger.info(f"Saved screenshot to {SCREENSHOT_PATH}")
                except Exception as e:
                    logger.warning(f"Screenshot failed: {e}")
                if SCREENSHOT_EXIT:
                    return


def main() -> int:
    try:
        Companion().run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Display crashed: {e}", exc_info=True)
        return 1
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
