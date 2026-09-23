---
id: sunny-pi-companion
type: component
status: active
created: 2026-09-22
updated: 2026-09-23
tags: [pi, companion, display, touch, pygame, kmsdrm, component]
---

# Pi companion panel

A Raspberry Pi 3B on the desk running a rotating dashboard, a face when
Sunny is talking, notification banners, and a touch menu.

`sunny-companion/pi-client/display/` — one pygame app, no browser, no X.

## Hardware

**Waveshare 4inch HDMI LCD (H)** — 800×480 IPS. Video over **HDMI**,
touch over **SPI** from an ADS7846 resistive controller. Those are two
independent paths, which is the source of the one unsolved problem below.

| | |
| --- | --- |
| Board | Pi 3B, 905MB RAM |
| Renderer | SDL **kmsdrm** — straight to the DRM plane, no X server |
| Panel mode | `hdmi_timings=480 … 800 …` — driven **portrait** |
| Logical canvas | 800×480 landscape, rotated in software |
| Touch | `/dev/input/event3`, IRQ 185 on GPIO 25 |

No X saves roughly 350MB on a 905MB box. A consequence: **reading
`/dev/fb0` shows the old console, not the app** — kmsdrm never touches
the framebuffer. The only way to see the screen over SSH is for the app
to save its own surface (`SCREENSHOT_PATH`).

## Panes

`clock · calendar · weather · tasks · health · checkin · usage`

Each returns `False` when it has nothing worth showing and the rotation
skips it. A pane rendering "no data" is worse than no pane: it spends
twelve seconds of a twelve-second cycle saying nothing.

### Layout

Two-column grid — headline left, supporting detail right. The first
version used a single left-aligned column and left ~40% of every screen
empty while truncating the content that mattered.

| Pane | Left | Right |
| --- | --- | --- |
| clock | time + date | what's on next |
| health | readiness ring, figure inside | sleep / steps / body battery with target bars |
| tasks | all five rows | due chips coloured by urgency |

Vertical positions are fractions of the height, not pixels, so the same
code lays out correctly at a different mode or unrotated on a monitor.

The clock's font is **fitted to its column** rather than taken from the
global ladder — `f_huge` renders "9:11 AM" about 500px wide and printed
straight through the event list beside it. Fitting beats a smaller
constant, which only moves the cliff to a longer string.

## Touch menu

Tap anywhere → a grid of large buttons. Tap one, it acts and closes. Tap
empty space or wait 20s to dismiss.

A tap while a notification is up **dismisses the notification** instead —
acknowledging an alert is the likelier intent and it needs no button.

Contents, in order of what someone standing over the panel wants:

1. **Check-in Yes/No**, only while a question is outstanding. The one
   daily input that otherwise needs a keyboard, asked at a time of day
   when nobody wants one.
2. Pane jumps — pinned 45s so a tapped pane doesn't rotate away mid-read
3. Refresh
4. Close

Buttons are sized for a **resistive** panel and a half-awake finger, not
to a phone's 44pt guideline. A press flashes: without visible
acknowledgement an unregistered tap and a registered one look identical,
and the response to that is jabbing at the screen. The menu also runs at
full FPS — at `IDLE_FPS` the 0.18s flash fell inside a single frame.

### Rotation is the whole risk

**Rotating the display does not rotate the touchscreen.** The panel
reports where the finger physically landed, which after `present()`'s 90°
turn is nowhere near the pixel being aimed at — and the failure looks
like "touch is broken" rather than "touch is rotated".

`Display.to_canvas()` is the exact inverse of `pygame.transform.rotate`.
`test_touch.py` verifies that by drawing a marker pixel, running the
**real** rotation, finding where it landed and mapping it back — so
`present()` and `to_canvas()` cannot drift apart without the test
failing. Zero drift at 0/90/180/270.

Comparing `to_canvas` against a second copy of the same arithmetic would
have proved nothing.

### Unsolved: touch orientation

Video is HDMI and touch is SPI, and nothing makes the two agree. On this
unit they demonstrably don't: the panel is driven **portrait** on glass
that is natively **landscape**, and the overlay has `swapxy = <0x00>`.
There are eight possible mappings.

`calibrate.py` measures it — four taps, scores all eight, prints
`TOUCH_SWAP` / `TOUCH_FLIP_X` / `TOUCH_FLIP_Y`, which go in the service
environment. `app.py` already reads them, so it is a config line, not a
code change.

**Needs someone physically at the panel.** Hardware is confirmed working
(IRQ 185 counts up on touch).

## Data

`GET /api/companion/snapshot` — one composite call, polled slowly. Five
sequential round trips per refresh is both slower and more code on the
side that can least afford it.

Every section degrades independently, and **absent sections are omitted
rather than sent empty**, so the device can tell "nothing today" from
"couldn't fetch".

### The health pane was blank for a reason worth recording

`_health()` returned `None` whenever *today* had no Garmin row, and
Garmin was IP rate-limited overnight — so a year of history in the
database rendered as a black screen, reported as "the UI is broken".

It now falls back to the most recent reading and carries `as_of`, which
the pane shows as `HEALTH · yesterday`. A stale number shown as current
would be worse than none; a blank pane is indistinguishable from a crash.

## Notifications

Pushed over the `/ws/pi` WebSocket, because a reminder arriving a minute
late has already failed at its job. Dashboard data is pulled on a timer
because it changes on the order of minutes.

Reconnect replays only the last **120 seconds**. Replaying the whole
buffer meant an hours-old reminder popped up again on every restart,
which trains you to ignore the banner.

## Env knobs

| Variable | Default | What |
| --- | --- | --- |
| `SCREEN_ROTATE` | 90 | Display rotation |
| `UI_SCALE` | 1.0 | Font multiplier |
| `IDLE_FPS` | 4 | Dashboard frame rate |
| `PANE_SECONDS` | 12 | Rotation interval |
| `PANE_PIN_SECONDS` | 45 | How long a tapped pane holds |
| `PANE_ONLY` | — | Pin one pane, for screenshots |
| `MENU_OPEN` | — | Open the menu at startup, for screenshots |
| `TOUCH_DEBUG` | — | Crosshair + panel/canvas coords at the last tap |
| `SCREENSHOT_PATH` | — | Save the surface (see kmsdrm note above) |

## Service

`sunny-face.service`, a **systemd user unit** (not Docker, not a system
unit). `loginctl enable-linger` keeps it up without a login.

## See also

- [[../COMMANDS.md]] — the menu, summarised
- [[../ROADMAP-2026-09.md]] — the calibration item
