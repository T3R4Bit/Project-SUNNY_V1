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
    Display, Notifications, Snapshot, fetch_checkin, fetch_snapshot_once, poll_snapshot,
    post_checkin_answer,
)
from display.face import Face
from display.menu import Menu, MenuItem
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

# How long a pane tapped from the menu holds the screen before the
# carousel resumes. Long enough to actually read a full task list.
PANE_PIN_SECONDS = int(os.environ.get("PANE_PIN_SECONDS", "45"))

# Pin the rotation to one pane by name, for development. Without it,
# capturing a specific pane means guessing at rotation timing and taking
# the same screenshot twice.
PANE_ONLY = os.environ.get("PANE_ONLY", "")

# Draws a crosshair and the coordinates wherever the screen is touched,
# in both panel and canvas space. This panel is resistive and its driver
# has no calibration applied, so if taps land off-target this is the only
# way to see whether the problem is the rotation mapping or the panel's
# own ranges -- without it, "the buttons don't work" has no next step.
TOUCH_DEBUG = os.environ.get("TOUCH_DEBUG", "") == "1"

# Open the menu at startup, so it can be screenshotted over SSH without
# anyone physically touching the panel.
# "1" opens the top-level menu; "checkin" opens the check-in page under
# it, so both can be screenshotted without anyone touching the panel.
MENU_OPEN = os.environ.get("MENU_OPEN", "")

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

        self.menu = Menu(self.display)
        self.menu.set_builder(self._menu_items)
        # Set by a pane-jump button. While it holds a name the carousel
        # stops advancing and that pane stays up, so tapping "Tasks" means
        # tasks are still there ten seconds later instead of having
        # rotated away mid-read.
        self.pinned_pane = ""
        self.pinned_until = 0.0
        self._last_touch = None
        # Filled by _menu_items each time the menu opens, so the check-in
        # page always reflects what was outstanding at that moment.
        self._checkin_pending = []
        self._checkin_day = None

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

    # --- menu ------------------------------------------------------------

    def _menu_items(self):
        """The top-level menu, rebuilt each time it opens.

        The check-in is ONE button here, not a Yes and a No. Those two
        took a quarter of an eight-slot grid for a single question, and
        would have taken half of it the moment a second question existed
        -- checkin.pending() already returns a list. The button opens its
        own page instead, which also gives room to show the question in
        full rather than squeezed into a title.
        """
        items = []

        pending = fetch_checkin() or {}
        outstanding = [q for q in (pending.get("pending") or [])
                       if q.get("type") == "yes_no"]
        self._checkin_day = pending.get("day")
        self._checkin_pending = outstanding

        self.menu.title = "Sunny"
        if outstanding:
            # A COUNT, not the question text. The prompt truncated to
            # "Did you have a mi…" in the button width, which tells you
            # less than a number does and looks broken doing it. The
            # question itself is the title of the page behind this.
            sub = f"{len(outstanding)} waiting"
            items.append(MenuItem("Check-in", self._open_checkin, PINK,
                                  sublabel=sub, icon="question", closes=False))

        for label, pane, icon in (("Calendar", "calendar", "calendar"),
                                  ("Weather", "weather", "cloud"),
                                  ("Tasks", "tasks", "checklist"),
                                  ("Health", "health", "heart")):
            items.append(MenuItem(label, lambda p=pane, l=label: self._pin_pane(p, l),
                                  BLUE, icon=icon))

        items.append(MenuItem("Refresh", self._refresh, YELLOW, icon="refresh"))
        items.append(MenuItem("Close", lambda: None, DIM, icon="back"))
        return items

    def _open_checkin(self):
        """Push the check-in page for the first outstanding question."""
        self._show_checkin_question(0)
        return None

    def _show_checkin_question(self, index: int):
        """One question per page: prompt as the title, Yes / No / Back.

        Answering advances to the next outstanding question rather than
        dropping back to the top, so several can be cleared in a row
        without reopening the menu each time.
        """
        questions = getattr(self, "_checkin_pending", [])
        if index >= len(questions):
            self.menu.close()
            return

        question = questions[index]
        qid = question["id"]
        day = getattr(self, "_checkin_day", None)
        position = f"{index + 1} of {len(questions)}" if len(questions) > 1 else ""

        def answer(value):
            self._answer_checkin(qid, value, day)
            remaining = index + 1
            if remaining < len(questions):
                self._show_checkin_question(remaining)
            else:
                self.menu.close()
            return None

        self.menu.push(question["prompt"], [
            MenuItem("Yes", lambda: answer("yes"), PINK, sublabel=position,
                     icon="check", closes=False),
            MenuItem("No", lambda: answer("no"), BLUE, sublabel=position,
                     icon="cross", closes=False),
            MenuItem("Back", self.menu.pop, DIM, icon="back", closes=False),
        ])

    def _answer_checkin(self, question_id: str, answer: str, day):
        """Log a check-in answer without blocking the render loop.

        The POST happens on a thread and the confirmation is flashed from
        there, so a slow or dead server leaves the screen animating rather
        than frozen. The message distinguishes success from failure
        because the server rejects an unparseable answer instead of
        storing a zero -- claiming "logged" on a rejection would leave a
        hole in the history that reads as a day never asked about.
        """
        def work():
            ok = post_checkin_answer(question_id, answer, day)
            self.menu.flash(f"Logged: {answer}" if ok else "Couldn't reach Sunny")

        threading.Thread(target=work, daemon=True).start()
        return None

    def _pin_pane(self, pane_name: str, label: str):
        panes = self.panes.all()
        target = getattr(self.panes, pane_name, None)
        if target is None or target not in panes:
            return f"No {label} pane"
        self.pinned_pane = pane_name
        self.pinned_until = time.time() + PANE_PIN_SECONDS
        self.pane_index = panes.index(target)
        self.pane_started = time.time()
        return None

    def _refresh(self):
        """Ask for fresh data now instead of waiting out the poll interval.

        Fires a one-shot fetch on its own thread rather than poking the
        polling thread, which is parked in a stop.wait() and has no way to
        be woken early without a second synchronisation primitive for a
        button pressed once a week.
        """
        threading.Thread(
            target=fetch_snapshot_once, args=(self.snapshot,), daemon=True
        ).start()
        return "Refreshing…"

    def _advance_pane(self, data: dict) -> None:
        if PANE_ONLY:
            return
        # A pane pinned from the menu holds the screen until it expires.
        if self.pinned_pane:
            if time.time() < self.pinned_until:
                return
            self.pinned_pane = ""
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

    def _draw_touch_hint(self) -> None:
        """A small persistent "tap" pill in the bottom-right corner.

        Without it the touch menu is completely invisible until touched,
        which makes a deployed build indistinguishable from an old one --
        the first question after shipping this was "the Pi hasn't
        updated", because nothing on screen said otherwise. It doubles as
        the affordance: nothing else about the panel suggests it responds
        to a finger.

        Dim and small on purpose. This sits on a desk all day and the
        dashboard is the point; a bright control would compete with it.
        """
        display = self.display
        saved, display.offset_y = display.offset_y, 0
        try:
            width, height = display.size
            font = display.f_small
            label = "MENU"
            surf = font.render(label, True, WHITE)

            # Sized as a real button, not a footnote. The first version was
            # f_tiny in the corner and the immediate feedback was that it
            # was too small to notice or aim at -- which it was, on a 4in
            # panel read from two feet away with a fingertip covering
            # roughly 40px of glass.
            pad_x = int(width * 0.028)
            pad_y = int(height * 0.022)
            box = pygame.Rect(0, 0, surf.get_width() + pad_x * 2,
                              surf.get_height() + pad_y * 2)
            box.right = width - display.pad
            box.bottom = height - int(height * 0.035)

            pygame.draw.rect(display.screen, (26, 26, 30), box, border_radius=10)
            pygame.draw.rect(display.screen, BLUE, box, width=2, border_radius=10)

            # Three bars, the one symbol everyone already reads as "menu".
            bar_w = int(surf.get_width() * 0.42)
            bar_x = box.x + pad_x
            bar_gap = max(4, int(box.height * 0.16))
            bar_y = box.centery - bar_gap
            for i in range(3):
                pygame.draw.line(display.screen, BLUE, (bar_x, bar_y + i * bar_gap),
                                 (bar_x + bar_w, bar_y + i * bar_gap), 2)

            display.screen.blit(surf, surf.get_rect(
                midleft=(bar_x + bar_w + pad_x // 2, box.centery)))
        finally:
            display.offset_y = saved

    def _draw_touch_debug(self) -> None:
        """Crosshair and coordinates at the last touch, for calibration.

        Shows the raw panel point alongside the canvas point it mapped to,
        because those are the two things that can independently be wrong:
        a bad panel reading means the ADS7846 needs calibrating, while a
        sane panel reading that maps to the wrong canvas point means the
        rotation inverse is wrong. One number cannot tell those apart.
        """
        if not self._last_touch:
            return
        point, event, when = self._last_touch
        display = self.display
        saved, display.offset_y = display.offset_y, 0
        try:
            age = time.time() - when
            if age > 6:
                return
            x, y = point
            pygame.draw.line(display.screen, ORANGE, (x - 22, y), (x + 22, y), 2)
            pygame.draw.line(display.screen, ORANGE, (x, y - 22), (x, y + 22), 2)
            pygame.draw.circle(display.screen, ORANGE, (x, y), 16, 2)

            if event.type == pygame.FINGERDOWN:
                pw, ph = display.physical.get_size()
                raw = f"finger {event.x * pw:.0f},{event.y * ph:.0f}"
            else:
                raw = f"mouse {event.pos[0]},{event.pos[1]}"
            display.text(f"{raw}  ->  canvas {x},{y}", display.f_tiny, ORANGE,
                         display.pad, display.size[1] - display.f_tiny.get_height() - 4)
        finally:
            display.offset_y = saved

    def run(self) -> None:
        clock = pygame.time.Clock()
        self.start_threads()
        if MENU_OPEN:
            self.menu.show()
            if MENU_OPEN == "checkin":
                self._open_checkin()

        while True:
            # The face animates; the dashboard is static text that changes
            # once a minute. Running both at 30fps on a Pi 3B spends most
            # of the CPU rotating identical frames, so idle drops to a
            # tenth of that. Rotation happens per frame, so this is where
            # its cost is actually paid or avoided.
            # The menu runs at full frame rate. At IDLE_FPS the 0.18s press
            # highlight lands inside a single frame and a tap looks like it
            # did nothing -- on a resistive panel with no haptics that is
            # the difference between "it works" and jabbing at it.
            talking_now = (time.time() - self.last_activity) < FACE_LINGER_SECONDS
            interactive = talking_now or self.menu.open
            dt = clock.tick(FPS if interactive else IDLE_FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        return
                    if event.key == pygame.K_m:
                        # Keyboard equivalent of a tap, for working on the
                        # menu over SSH with a keyboard plugged in.
                        self.menu.toggle()
                        continue
                    # Any other key dismisses a banner -- a keyboard is
                    # often plugged in while working on it.
                    self.notifications.dismiss()

                point = self.display.touch_point(event)
                if point is not None:
                    self._last_touch = (point, event, time.time())
                    # A touch ALWAYS opens the menu. It used to be swallowed
                    # while a notification was up, on the theory that
                    # dismissing the alert was the likelier intent -- but
                    # that made the one rule anyone has to remember ("touch
                    # the screen, get the menu") conditional on something
                    # invisible until it happens. A banner now clears AND
                    # the menu opens, which serves both intents in one tap.
                    if self.notifications.current():
                        self.notifications.dismiss()
                    self.menu.handle_tap(point)

            self.menu.tick()

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
                if PANE_ONLY:
                    pinned = getattr(self.panes, PANE_ONLY, None)
                    if pinned:
                        panes = [pinned]
                        self.pane_index = 0
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
            # Menu above the banner: it is the thing being interacted with,
            # and a notification arriving mid-tap must not cover the button
            # a finger is already on its way to.
            if not self.menu.open and not note:
                self._draw_touch_hint()
            self.menu.draw()
            self.menu.draw_status()
            if TOUCH_DEBUG:
                self._draw_touch_debug()
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
    """Entry point, with crash reporting wired around the render loop.

    crash_reporter.py has existed since the Pi client was built and had
    NO callers -- mark_running, mark_clean_shutdown and
    report_crash_if_needed were never invoked from anywhere, so the
    device has never reported a crash in its life. It was written for the
    wake-word listener, which is not running yet; the display is the
    process that actually needs it.

    Order matters: report BEFORE marking, or this run's own marker is the
    one it finds.
    """
    import crash_reporter
    import signal

    # systemd stops a unit with SIGTERM, whose default handler exits the
    # process WITHOUT raising anything -- so the clean-shutdown marker
    # never got cleared and every `systemctl restart` would still be
    # reported as a crash. Translating it into KeyboardInterrupt routes a
    # deliberate stop down the same path as Ctrl-C, which is what it is.
    def _on_sigterm(signum, frame):
        raise KeyboardInterrupt()

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        # Not the main thread, or a platform without SIGTERM. Worst case
        # is the old behaviour.
        pass

    service = "sunny-face"
    try:
        crash_reporter.report_crash_if_needed(service, SUNNY_URL)
        crash_reporter.mark_running(service)
    except Exception as e:
        # A reporting failure must never stop the display starting. The
        # screen being up matters more than knowing why it went down.
        logger.warning(f"crash reporting unavailable: {e}")

    clean = False
    try:
        Companion().run()
        clean = True
    except KeyboardInterrupt:
        # Ctrl-C and `systemctl stop` are deliberate. Marking clean here
        # is what stops a restart being reported as a crash next time --
        # without it, every restart looks like one, which is how the
        # signal becomes noise.
        clean = True
    except Exception as e:
        logger.error(f"Display crashed: {e}", exc_info=True)
        return 1
    finally:
        pygame.quit()
        if clean:
            try:
                crash_reporter.mark_clean_shutdown(service)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
