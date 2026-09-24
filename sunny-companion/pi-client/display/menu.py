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

from display import icons

logger = logging.getLogger("companion.menu")

# Close on its own after this long untouched. Long enough to read the
# options and decide, short enough that a menu opened by a sleeve is gone
# before it matters.
IDLE_CLOSE_SECONDS = 20

# How long a pressed button stays highlighted.
PRESS_FLASH_SECONDS = 0.18

# Grid. Four across on an 800-wide landscape canvas gives ~180px columns.
COLUMNS = 4

BG = (12, 12, 14)
# OPAQUE. This was rgba(0,0,0,190) and the dashboard read straight
# through it -- the clock, the pane header and the event list all ghosted
# behind the buttons, which is what "looks phased" meant. A translucent
# scrim is a desktop idiom; on a 4in panel at arm's length it just makes
# both layers unreadable. The menu owns the screen while it is open.
SCRIM = (12, 12, 14)
LABEL = (240, 240, 240)
IDLE_FILL = (26, 26, 30)
BORDER = (70, 70, 78)


class MenuItem:
    """One button. `action` takes no arguments and returns an optional
    status string to flash on screen after it runs."""

    def __init__(self, label: str, action: Callable[[], Optional[str]],
                 color=(37, 150, 190), sublabel: str = "", icon: str = "dot",
                 closes: bool = True):
        self.label = label
        self.action = action
        self.color = color
        self.sublabel = sublabel
        # False for an item that opens a submenu -- otherwise _run would
        # close the whole menu the instant the submenu was pushed.
        self.closes = closes
        # Icon NAME, not a function -- see icons.ICONS. An unknown name
        # falls back to a dot rather than raising, so adding a menu item
        # can never blank the screen.
        self.icon = icon
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
        # Parent pages, innermost last. A submenu pushes the current page
        # here and restores it on back, so "back" never has to know what
        # it came from.
        self._stack: List[tuple] = []

    def set_builder(self, build: Callable[[], List[MenuItem]]) -> None:
        self._build = build

    def toggle(self) -> None:
        self.close() if self.open else self.show()

    def show(self) -> None:
        self.items = self._build() if self._build else []
        self._stack = []
        self.open = True
        self._opened_at = time.time()
        self._pressed = None

    def push(self, title: str, items: List[MenuItem]) -> None:
        """Open a submenu, remembering the page it came from."""
        self._stack.append((self.title, self.items))
        self.title = title
        self.items = items
        self._pressed = None
        # Reset the idle timer: arriving at a submenu is activity, and
        # inheriting the parent's timer could close it mid-read.
        self._opened_at = time.time()

    def pop(self) -> None:
        """Back one level, or close if already at the top."""
        if not self._stack:
            self.close()
            return
        self.title, self.items = self._stack.pop()
        self._pressed = None
        self._opened_at = time.time()

    @property
    def depth(self) -> int:
        return len(self._stack)

    def close(self) -> None:
        self.open = False
        self._pressed = None
        self._stack = []

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

        # A tap on empty space goes BACK one level rather than closing
        # outright. In a submenu, closing the lot would throw away the
        # step you were halfway through answering.
        self.pop()
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
        if item.closes:
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

            # A plain opaque fill, not an alpha blit. Nothing underneath
            # should be visible at all.
            display.screen.fill(SCRIM)

            # Breathing room. The grid used to start at display.pad (~28px)
            # on every side, which put buttons hard against the bezel and
            # read as the whole thing being shoved into a corner.
            margin = int(width * 0.05)
            top = int(height * 0.06)

            if self.title:
                surf = display.f_small.render(
                    display._truncate(self.title, display.f_small, width - margin * 2),
                    True, LABEL)
                display.screen.blit(surf, surf.get_rect(center=(width // 2, top)))
                top += int(display.f_small.get_height() * 0.9)
            else:
                top = int(height * 0.04)

            self._layout(top, margin)
            for item in self.items:
                self._draw_item(item)
        finally:
            display.offset_y = saved_offset

    def _layout(self, top: int, margin: int) -> None:
        """Assign each item a rect. Recomputed per frame so the grid
        follows the canvas rather than assuming 800x480."""
        width, height = self.display.size
        gap = max(8, int(width * 0.018))

        count = len(self.items)
        if not count:
            return
        columns = min(COLUMNS, count)
        rows = (count + columns - 1) // columns

        bottom_margin = int(height * 0.06)
        usable_w = width - margin * 2 - gap * (columns - 1)
        usable_h = height - top - bottom_margin - gap * (rows - 1)
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
        """One button: icon above, label below.

        The icon carries the meaning at a glance and the word confirms it.
        Icon-only would need a legend on a panel this size; text-only is
        what the first version was, and four words in a row all look the
        same from across a desk.
        """
        display = self.display
        pressed = (item is self._pressed
                   and time.time() - self._pressed_at < PRESS_FLASH_SECONDS)

        rect = item.rect
        fill = item.color if pressed else IDLE_FILL
        edge = LABEL if pressed else item.color
        content = LABEL if pressed else item.color

        pygame.draw.rect(display.screen, fill, rect, border_radius=14)
        pygame.draw.rect(display.screen, edge, rect, width=2, border_radius=14)

        font = display.f_small
        label = display._truncate(item.label, font, rect.width - 14)
        label_surf = font.render(label, True, LABEL)

        # Icon sized off the button, so it stays proportional whether the
        # grid is four wide or two.
        icon_size = int(min(rect.width, rect.height) * 0.42)
        block_h = icon_size + int(font.get_height() * 1.15)
        icon_cy = rect.centery - block_h // 2 + icon_size // 2
        icons.draw(item.icon, display.screen, (rect.centerx, icon_cy), icon_size, content)

        display.screen.blit(label_surf, label_surf.get_rect(
            center=(rect.centerx, icon_cy + icon_size // 2 + int(font.get_height() * 0.62))))

        if item.sublabel:
            sub = display._truncate(item.sublabel, display.f_tiny, rect.width - 14)
            sub_surf = display.f_tiny.render(sub, True, BORDER if not pressed else LABEL)
            display.screen.blit(sub_surf, sub_surf.get_rect(
                center=(rect.centerx, rect.bottom - int(display.f_tiny.get_height() * 0.9))))

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
