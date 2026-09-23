"""Tap-to-open menu for the companion panel.

The Pi sits on a desk showing a rotating dashboard you cannot influence.
This makes it answer a finger: tap anywhere to open a grid of big
buttons, tap one, it acts and closes.

WHY THE BUTTONS ARE SO LARGE
----------------------------
This is a resistive ADS7846 panel, not a phone. It reads one point, it is
less precise than capacitive glass, and pressing it firmly enough to
register nudges the whole unit. On top of that the most valuable button
here gets pressed first thing in the morning by someone half awake. So
targets are sized in the region of 150x90 rather than to a phone's 44pt
guideline, and there are at most six of them.

WHY A PRESS FLASHES
-------------------
A resistive panel gives no physical feedback and sometimes misses a light
touch. Without a visible response to the press itself, an unregistered
tap and a registered one that did something invisible look identical, and
the natural reaction is to jab the screen repeatedly. PRESS_FLASH_SECONDS
holds a highlight on the pressed button so the press is always
acknowledged even when the action behind it takes a moment.

ACTIONS DO NOT BLOCK
--------------------
An item's callback runs on the render thread, so anything touching the
network must hand off to a thread and return immediately. The check-in
buttons do exactly that. A blocking call here freezes the display, which
on a device whose whole job is to look alive reads as a crash.
"""

import logging
import time
from typing import Callable, List, Optional

import pygame

logger = logging.getLogger("companion.menu")

# Close on its own after this long untouched. Long enough to read the
# options and decide, short enough that a menu opened by a sleeve is gone
# before it matters.
IDLE_CLOSE_SECONDS = 20

# How long a pressed button stays highlighted.
PRESS_FLASH_SECONDS = 0.18

# Grid. Four across on an 800-wide landscape canvas gives ~180px columns.
COLUMNS = 4

BG = (16, 16, 18)
SCRIM = (0, 0, 0, 190)
LABEL = (240, 240, 240)
IDLE_FILL = (34, 34, 38)
BORDER = (70, 70, 78)


class MenuItem:
    """One button. `action` takes no arguments and returns an optional
    status string to flash on screen after it runs."""

    def __init__(self, label: str, action: Callable[[], Optional[str]],
                 color=(37, 150, 190), sublabel: str = ""):
        self.label = label
        self.action = action
        self.color = color
        self.sublabel = sublabel
        self.rect: Optional[pygame.Rect] = None


class Menu:
    def __init__(self, display) -> None:
        self.display = display
        self.open = False
        self.items: List[MenuItem] = []
        self.title = ""
        self._opened_at = 0.0
        self._pressed: Optional[MenuItem] = None
        self._pressed_at = 0.0
        self._status = ""
        self._status_until = 0.0
        # Rebuilt on every open rather than once at startup: whether there
        # is a check-in to answer changes during the day, and a menu that
        # offers yesterday's question is worse than one that offers none.
        self._build: Optional[Callable[[], List[MenuItem]]] = None

    def set_builder(self, build: Callable[[], List[MenuItem]]) -> None:
        self._build = build

    def toggle(self) -> None:
        self.close() if self.open else self.show()

    def show(self) -> None:
        self.items = self._build() if self._build else []
        self.open = True
        self._opened_at = time.time()
        self._pressed = None

    def close(self) -> None:
        self.open = False
        self._pressed = None

    def flash(self, message: str, seconds: float = 2.5) -> None:
        """Show a short confirmation over the dashboard after the menu
        closes -- "Logged: no migraine" and the like. Without it a tap
        that succeeds looks exactly like a tap that did nothing."""
        self._status = message
        self._status_until = time.time() + seconds

    def tick(self) -> None:
        if self.open and time.time() - self._opened_at > IDLE_CLOSE_SECONDS:
            self.close()

    def handle_tap(self, point) -> bool:
        """Route a tap. Returns True if the menu consumed it.

        A tap while closed opens the menu and is deliberately NOT passed
        through to whatever is underneath -- the first touch is always
        just "wake up", so there is no way to trigger an action by
        accident on a screen you were not already looking at.
        """
        if not self.open:
            self.show()
            return True

        for item in self.items:
            if item.rect and item.rect.collidepoint(point):
                self._pressed = item
                self._pressed_at = time.time()
                self._run(item)
                return True

        # A tap on empty space closes. On a panel this small the gap
        # between buttons is the only "cancel" that needs no button.
        self.close()
        return True

    def _run(self, item: MenuItem) -> None:
        try:
            result = item.action()
        except Exception as e:
            logger.error(f"Menu action {item.label!r} failed: {e}", exc_info=True)
            self.flash("That didn't work")
            self.close()
            return
        if result:
            self.flash(result)
        self.close()

    # --- drawing ---------------------------------------------------------

    def draw(self) -> None:
        """Draw the menu over whatever the dashboard already rendered.

        Drawn at absolute coordinates with offset_y forced to zero: the
        menu is not a pane and must not be pushed down by a notification
        banner, or its bottom row would fall off the screen.
        """
        if not self.open:
            return

        display = self.display
        saved_offset, display.offset_y = display.offset_y, 0
        try:
            width, height = display.size
            scrim = pygame.Surface((width, height), pygame.SRCALPHA)
            scrim.fill(SCRIM)
            display.screen.blit(scrim, (0, 0))

            pad = display.pad
            top = pad
            if self.title:
                display.text(self.title, display.f_small, LABEL, width // 2, top, center=True)
                top += int(display.f_small.get_height() * 1.4)

            self._layout(top)
            for item in self.items:
                self._draw_item(item)
        finally:
            display.offset_y = saved_offset

    def _layout(self, top: int) -> None:
        """Assign each item a rect. Recomputed per frame so the grid
        follows the canvas rather than assuming 800x480."""
        width, height = self.display.size
        pad = self.display.pad
        gap = max(6, pad // 2)

        count = len(self.items)
        if not count:
            return
        columns = min(COLUMNS, count)
        rows = (count + columns - 1) // columns

        usable_w = width - pad * 2 - gap * (columns - 1)
        usable_h = height - top - pad - gap * (rows - 1)
        cell_w = usable_w // columns
        cell_h = usable_h // rows

        for index, item in enumerate(self.items):
            row, col = divmod(index, columns)
            # Last row centres any remainder, so three buttons under four
            # don't sit flush left with a hole where the fourth would be.
            in_row = min(columns, count - row * columns)
            row_width = in_row * cell_w + (in_row - 1) * gap
            x0 = (width - row_width) // 2
            item.rect = pygame.Rect(
                x0 + col * (cell_w + gap),
                top + row * (cell_h + gap),
                cell_w, cell_h,
            )

    def _draw_item(self, item: MenuItem) -> None:
        display = self.display
        pressed = (item is self._pressed
                   and time.time() - self._pressed_at < PRESS_FLASH_SECONDS)

        fill = item.color if pressed else IDLE_FILL
        pygame.draw.rect(display.screen, fill, item.rect, border_radius=10)
        pygame.draw.rect(display.screen, item.color if not pressed else LABEL,
                         item.rect, width=2, border_radius=10)

        font = display.f_small
        label = display._truncate(item.label, font, item.rect.width - 12)
        surf = font.render(label, True, LABEL)
        centre_y = item.rect.centery
        if item.sublabel:
            centre_y -= display.f_tiny.get_height() // 2
        display.screen.blit(surf, surf.get_rect(center=(item.rect.centerx, centre_y)))

        if item.sublabel:
            sub = display._truncate(item.sublabel, display.f_tiny, item.rect.width - 12)
            sub_surf = display.f_tiny.render(sub, True, BORDER if not pressed else LABEL)
            display.screen.blit(sub_surf, sub_surf.get_rect(
                center=(item.rect.centerx, centre_y + font.get_height() - 2)))

    def draw_status(self) -> None:
        """The post-action confirmation. Separate from draw() because it
        outlives the menu -- the point is to be visible once the menu has
        closed and the dashboard is back."""
        if time.time() > self._status_until or not self._status:
            return
        display = self.display
        saved_offset, display.offset_y = display.offset_y, 0
        try:
            width, height = display.size
            font = display.f_small
            text = display._truncate(self._status, font, width - display.pad * 2)
            surf = font.render(text, True, LABEL)
            box = surf.get_rect(center=(width // 2, height - int(height * 0.12)))
            backing = box.inflate(display.pad, display.pad // 2)
            pygame.draw.rect(display.screen, BG, backing, border_radius=8)
            pygame.draw.rect(display.screen, (37, 150, 190), backing, width=2, border_radius=8)
            display.screen.blit(surf, box)
        finally:
            display.offset_y = saved_offset
