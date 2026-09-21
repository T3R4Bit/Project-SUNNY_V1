# Companion display

One pygame app that owns the screen: a rotating dashboard when idle, the
face while you're talking to it, and notification banners over either.

Runs on the Pi 3 Model B at `sunny-companion` (480x800 Waveshare panel).

## Running it

```bash
cd ~/Project-SUNNY/sunny-companion/pi-client
SUNNY_URL=http://sunshine-m700.wahoo-sidewinder.ts.net:5000 python3 -m display
```

Installed as a **user** systemd service (`systemctl --user`), not a system
one, because the `sunny` account's passwordless sudo covers `systemctl`
but not writing to `/etc/systemd/system`. Linger is enabled so it starts
at boot without anyone logging in.

```bash
systemctl --user status sunny-face
systemctl --user restart sunny-face
journalctl --user -u sunny-face -f
```

## Why no browser

This Pi has 905MB of RAM. A desktop session idles around 350-450MB and
Chromium wants another 300-500MB, which leaves nothing for the wake-word
listener and audio. The app measures **129MB**, leaving ~570MB free.

It also means one process owns the display. A browser dashboard plus a
separate pygame face would have to hand the screen back and forth every
time you spoke.

## The GUI

**SDL's kmsdrm driver renders straight to the panel with no X server** --
confirmed working here at 480x800. The desktop is installed (lightdm +
labwc) and enabled, but the default target is `multi-user`, so the face
app owns the screen on boot.

To switch to the desktop:

```bash
systemctl --user stop sunny-face
sudo systemctl isolate graphical.target
```

And back:

```bash
sudo systemctl isolate multi-user.target
systemctl --user start sunny-face
```

> Both *can* run at once -- neither crashes, and the app still gets a
> kmsdrm surface with lightdm up. But which one is actually visible on the
> physical panel in that state was never established, so don't rely on it.
> Run one or the other.

The app picks its driver automatically (X11 when `DISPLAY` is set, kmsdrm
otherwise), so neither mode needs a config change.

## Rotation

`SCREEN_ROTATE=90` (set in the service unit). Panes draw onto a logical
canvas with width and height swapped, so they lay out for the orientation
you see rather than the one the panel reports: panel 480x800 becomes
logical 800x480.

If the picture comes out upside down for how the panel is mounted, use
`270`. `0` disables rotation entirely and makes `present()` a straight
blit with no per-frame cost.

```bash
systemctl --user edit --full sunny-face   # change SCREEN_ROTATE
systemctl --user restart sunny-face
```

Done in software rather than `/boot/firmware/config.txt` because writing
there needs a sudo password this account doesn't have passwordless, and a
bad boot config leaves the panel dark until it's fixed physically. The
cost is one rotate-and-blit per frame, which is why the dashboard idles at
`IDLE_FPS` (4) instead of 30 -- measured **14% of one core** on the Pi 3B.
The face still runs at full rate while it animates.

## Data

Two sources, two cadences, both on background threads so the render loop
never blocks on the network:

| | how | why |
| --- | --- | --- |
| Dashboard | polls `/api/companion/snapshot` every 60s | changes over minutes; a failed poll is harmless |
| Notifications | pushed over `/ws/pi` | a reminder a minute late has already failed |

The server buffers the last 10 notifications and replays anything from the
**last two minutes** on reconnect, so a restart mid-reminder doesn't
swallow it. Older ones aren't replayed -- a notification you already saw
reappearing trains you to ignore the banner.

When the server goes away the last good snapshot keeps rendering with a
staleness marker. A dashboard showing slightly old data is useful; a black
screen is not.

## Sizing

Type is scaled off the panel's short edge and sized for **desk distance**,
not phone distance -- this screen is 4.3" but sits two feet away and is
never touched, so everything is deliberately oversized.

`UI_SCALE` multiplies every font if it still isn't right:

```bash
systemctl --user edit --full sunny-face   # Environment=UI_SCALE=1.2
systemctl --user restart sunny-face
```

Layout adapts to the aspect: the health stats sit in three columns in
landscape and stack in portrait, because stacked in landscape they used a
narrow left column and left most of an 800px screen empty.

Times are 12-hour throughout, built by hand rather than with `%-I`
(glibc-only) or `%#I` (Windows-only).

## Panes

`clock`, `calendar`, `weather`, `tasks`, `health`, `checkin`, `usage` --
12 seconds each, and a pane with nothing to show is **skipped** rather
than rendering "no data". Twelve seconds of a twelve-second cycle telling
you nothing is worse than not appearing.

## Debugging from SSH

kmsdrm renders to the DRM plane and never touches `/dev/fb0`, so reading
the framebuffer shows the old console, not the app. Have it save its own
surface instead:

```bash
SCREENSHOT_PATH=/tmp/shot.png SCREENSHOT_AFTER=6 SCREENSHOT_EXIT=1 python3 -m display
```

## Environment

| Variable | Default | |
| --- | --- | --- |
| `SUNNY_URL` | the tailnet address | server base URL |
| `SNAPSHOT_INTERVAL` | `60` | dashboard poll seconds |
| `PANE_SECONDS` | `12` | seconds per pane |
| `FPS` | `30` | frame cap while the face animates |
| `IDLE_FPS` | `4` | frame cap on the dashboard |
| `UI_SCALE` | `1.0` | multiplies every font size |
| `SDL_VIDEODRIVER` | auto | force `kmsdrm` or `x11` |
