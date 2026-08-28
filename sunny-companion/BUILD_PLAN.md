# Sunny Companion — Build Plan (Desk Unit v1)

Step-by-step, in dependency order. Check items off as they're done. Each phase assumes the previous one works before moving on — don't build the face renderer against a kiosk stack that hasn't been proven to boot yet.

## Repo layout

Everything lives in this one repo (Project-SUNNY) — no separate repo for the Pi side. The Pi gets a plain `git clone` of the whole thing (the tracked repo is ~7MB; all the bulky stuff — `venv/`, `piper_voices/`, `vosk_models/`, `*.db` — is gitignored, so cloning it onto the Pi doesn't pull any of that):

```text
sunny-companion/
├── README.md / BUILD_PLAN.md
├── dev-watchdog.py                     (dev-only: keeps the local test server running)
└── pi-client/                          ← everything that runs ON the Pi
    ├── wake_word_listener.py           (Phase 5)
    ├── wake_on_lan.py                  (Phase 5)
    ├── crash_reporter.py               (Phase 5)
    ├── systemd/
    │   ├── sunny-face.service          (Phase 2 — kiosk display, renderer TBD)
    │   └── sunny-client.service        (Phase 5 — wake-word + network client)
    └── face_renderer/                  (Phase 4 -- the avatar-lab attempt was
                                          scrapped 2026-08-23; this is the pygame
                                          restart, standalone prototype only so far)
```

The new server-side endpoint (Phase 6) stays in `sunny_code/`, alongside the existing `stt.py`/`tts.py`/`voice_worker.py` — not in `sunny-companion/`.

Updating the device going forward is just `git pull` on the Pi + restarting the two systemd services below. Set up a dedicated read-only deploy key / fine-grained PAT for the Pi to clone and pull with (same pattern as the existing Lenovo server SSH key) rather than putting personal GitHub credentials on a physically-accessible embedded device.

## Phase 0 — Parts arrival

- [x] Board bought (Pi 3 Model B, $32)
- [x] Rest of BOM ordered (screen, mic, SD card, PSU — see [README.md](README.md) for links)
- [x] Parts arrive

## Phase 1 — Base OS

- [x] Flash **Raspberry Pi OS Lite (64-bit)** to the microSD card — headless, no desktop environment. **2026-08-28: actual image turned out to be Debian 13 (Trixie)-based, not Bookworm as originally planned** — Raspberry Pi OS's current release had moved on by the time of flashing. Ships Python 3.13 by default (no 3.11/3.12 package available via apt), which had downstream effects — see Phase 5's openWakeWord note
- [x] First boot: SSH enabled, WiFi connected, hostname `sunny-companion` (user account is `sunny`, not `sunny-companion` — only the hostname uses that string). Note: the Raspberry Pi Imager's "public-key authentication" field silently didn't take — first boot only accepted the account password, not the pasted key; keys were added manually via `~/.ssh/authorized_keys` after logging in with the password instead
- [ ] `sudo apt update && sudo apt upgrade` — only targeted package installs done so far (`git`, `python3-venv`, `python3-pip`, `portaudio19-dev`, `alsa-utils`), not a full system upgrade
- [x] Confirmed reachable over SSH on the home WiFi network (`sunny@sunny-companion.local`, port 44 — moved off default port 22 to match the sunny-lenovo convention)
- [x] Dedicated read-only GitHub deploy key generated on the Pi itself and added via the repo's Settings → Deploy keys (repo is private, so this was required, not optional); `git clone` done to `~/Project-SUNNY`

## Phase 2 — Kiosk display stack

- [ ] `sudo apt install cog libwpewebkit-1.1-0`
- [ ] Test: `cog --platform=drm https://example.com` renders full-screen with no X11/Wayland compositor running — confirms the screen (once attached) and DRM/KMS path work
- [ ] Attach the Waveshare screen (GPIO + HDMI direct-connect) and repeat the test on real hardware
- [ ] Write `pi-client/systemd/sunny-face.service`: launches whatever Phase 4 ends up being (a `cog --platform=drm <url>` invocation if the replacement is still browser-based, or something else entirely if not — depends on the Phase 4 decision), `WantedBy=multi-user.target` (no network dependency — assets should already be on disk, so the face should appear immediately on boot rather than waiting on WiFi), `Restart=on-failure`
- [ ] `systemctl enable sunny-face.service` — confirm boot-to-face works with no login prompt, no manual steps, and that it survives a crash (kill the process, confirm systemd restarts it)

## Phase 3 — Audio I/O

- [ ] Confirm 3.5mm audio out works: `speaker-test` or `aplay` a test WAV through the Pi's onboard jack — not tested yet, mic came first
- [x] Plug in the USB mic, confirm it's detected: `arecord -l` — shows up as `card 2: USB PnP Sound Device` (TI PCM2902 codec)
- [x] Record a short clip and play it back to confirm mic quality/levels — **2026-08-28 finding: the SunFounder mic's default ALSA capture gain was 0% (muted-equivalent, despite showing `[on]`)**; raised to 100% (`amixer -c 2 sset Mic 16`, its max — 23.81dB) which fixed detection but voice was still barely audible even at point-blank range. A tap-the-capsule test at the same gain setting hit full digital clipping (peak 32768) while close-range voice only peaked ~1800 — proves the capture path (USB/ALSA/wiring) is completely fine, the capsule itself is just acoustically insensitive to voice specifically, not defective. Fix: an 8x digital gain multiplier applied in software after capture (zero clipping at that level, confirmed audible on playback) — implemented in `wake_word_listener.py`'s `MIC_GAIN` constant. Software gain amplifies noise along with signal, so this is a workaround, not a substitute for a more sensitive mic if it proves inadequate at real desk distance (only tested point-blank so far)
- [ ] Set explicit default ALSA input/output devices (`/etc/asound.conf` or `.asoundrc`) so they don't shift if USB device order changes on reboot — not done yet

## Phase 4 — Face renderer (scrapped and restarting)

**2026-08-23: the bible-strong-avatar-lab attempt was built (character, expression set, state machine wiring, WebSocket client, amplitude-driven CSS pulse for "speaking") and then scrapped.** It's been removed from the repo entirely. What it proved, for whenever a new attempt starts: the animation-engine-vs-static-image distinction mattered and is worth checking again for whatever's next; the chosen library had no mouth geometry at all, so "speaking" ended up as a CSS pulse rather than real mouth movement — worth deciding upfront next time whether that's acceptable or a dealbreaker; and the render-performance risk flagged from the start (Pi 3 B's CPU cost for whatever does the rendering) never actually got validated on real hardware before the scrap, so it's still an open unknown, not a resolved one.

- [ ] Decide the renderer approach (see README's Open Questions — this decision also feeds back into whether the Pi 3 B board choice still holds)
- [ ] Everything below is a placeholder shape, not a committed plan, until that's decided: design/build whatever the face actually is, wire it to the state machine (idle/listening/thinking/searching/speaking + emotion overlay) that `pi_companion.py` already emits over `/ws/pi`, get it running standalone on a dev machine, then validate it actually renders smoothly on the real Pi 3 B hardware before investing further

**2026-08-23: leaning candidate for the restart — Python/pygame direct-to-framebuffer, not another browser attempt.** Prototyped since (see the checked-off items below) but not finally decided — real Pi 3 B hardware validation is still the open step. The reasoning: every other device-side piece (`wake_word_listener.py`, `voice_worker.py`, `pi_companion.py`) is already Python, so a Python renderer means wake-word → state → amplitude is a same-process function call/shared variable instead of a WebSocket hop into a browser page (the scrapped attempt's browser-connects-directly-to-`/ws/pi` pattern was explicitly a testing shortcut, not the real design — see Phase 4.5). pygame's SDL2 backend can run `SDL_VIDEODRIVER=kmsdrm` straight to DRM/KMS with no X11/Wayland compositor, mirroring the no-compositor constraint Phase 2 already proved out for `cog`. This sidesteps the WPE WebKit CPU-cost risk that never got validated on real Pi 3 B hardware before the scrap.

- [x] Prototype standalone on a dev machine first: a simple amplitude-reactive shape (ring or blob — cheap primitives, no image assets) in pygame, `SDL_VIDEODRIVER=kmsdrm` on the Pi once it's on real hardware
      *(built: `pi-client/face_renderer/renderer.py` — a filled circle whose radius reacts to a live `amplitude` value, keyboard-driven state switching (1-5) for manual testing without the server wired up. Verified running on this dev machine — real window opens (`Sunny face renderer prototype`), event loop holds a steady frame rate, no crashes. Uses `pygame-ce`, not upstream `pygame` — upstream has no Python 3.14 wheel yet and fails to build from source without MSYS2; `pygame-ce` is a drop-in-compatible fork (`import pygame` unchanged) with a prebuilt 3.14 wheel. Not yet run on real Pi hardware or with `SDL_VIDEODRIVER=kmsdrm` — that's the still-open validation bullet below.)*
- [x] Amplitude source per state — same `amplitude` variable, three different feeds, no separate code paths per shape:
  - **Listening** (post-wake-word) — raw mic RMS, read directly off a `sounddevice` stream, same approach `wake_word_listener.py` used to use. Built and verified live on a dev machine (real mic input drove the shape; hit a benign "input overflow" warning under load, handled the same non-fatal way `wake_word_listener.py` handled stream status at the time). **2026-08-28 flag: this is now stale.** On real Pi 3B hardware with the SunFounder USB mic, that same "input overflow" turned out to be a real PortAudio↔ALSA bug causing continuous dropped audio, not benign at all (see Phase 5's wake-word findings) — `wake_word_listener.py` no longer uses `sounddevice` for capture at all because of it (switched to a direct `arecord` subprocess). This renderer's amplitude source will very likely hit the same problem once tested on real hardware and should get the same fix
  - **Thinking** — no real audio available yet (waiting on the server's LLM reply); synthesize it instead — sum of 2 detuned low-frequency sines at low amplitude, a "breathing" idle animation rather than a frozen face. Built (`searching` reuses the same synthesized approach at a slightly different rate/amplitude to stay visually distinct, since the plan doesn't specify a separate source for it)
  - **Speaking** — TTS playback buffer RMS as it's fed to ALSA (no true viseme/phoneme timing from Piper, so this stays the amplitude-driven substitute the README already settled on). Proven in a separate dev-only demo — `pi-client/face_renderer/tts_demo.py` plays real Piper-synthesized speech and drives `speaking` off the actual TTS playback buffer's RMS — but the main renderer prototype still reuses the mic-RMS feed as `listening`'s structural stand-in for `speaking`, since no live TTS audio exists until the device is actually wired to the server. Swapping the main renderer over to the real feed is Phase 4.5/6 work, once the renderer is wired to the device client
- [x] Tone/emotion overlay — hue/color shift composited on top of whichever shape, driven by the server's mood tag (see Emotion overlay v2 below); cheap, no extra per-frame cost
      *(built at prototype level: a 5-hue table (neutral/happy/concerned/playful/apologetic), cycled manually with the `e` key for now since the server doesn't emit a real mood tag yet — Emotion overlay v2 below is still unbuilt server-side, so there's nothing live to drive this from yet)*
- [ ] Validate actual frame timing on real Pi 3 B hardware before building out more shapes — this is the exact validation step that got skipped last time. Still open — everything above was only run on a Windows dev machine
- [x] Validate the software stack (not timing) installs cleanly on the real target OS/arch — `pi-client/Dockerfile.test` builds a QEMU-emulated arm64 Debian Bookworm image (matching Raspberry Pi OS Lite 64-bit) with the real `requirements.txt` and runs `face_renderer/smoke_test.py` headless. Every dependency installed clean, including the risky native-extension ones (`pygame-ce`, `onnxruntime`, `sounddevice`, `openwakeword`); all imports and a 120-frame headless render loop passed. This does **not** substitute for the bullet above — QEMU emulation on an x86 dev machine says nothing about Pi 3 B's real CPU budget, and there's no GPU passthrough or mic in a container, so `kmsdrm` and live mic capture are still untested

## Phase 4.5 — Wiring the renderer to the device client

Regardless of what Phase 4 turns out to be, something needs to receive `/ws/pi`'s state events and audio and hand them to the renderer + speakers. That's genuinely new work either way (the scrapped attempt had the *browser page itself* connect directly to `/ws/pi` for convenience while testing — not how it should work for real, per Phase 5 below).

## Phase 5 — Device client (Python, runs on the Pi)

- [x] Pick and install a local wake-word engine — `pi-client/wake_word_listener.py`, using openWakeWord. **No pretrained "hey sunny" model exists** — using "hey_jarvis" as a placeholder to prove the mechanism (continuous low-compute listening → trigger callback) actually works. **2026-08-28: fully verified live and working end-to-end on real Pi 3B hardware**, including a real spoken "hey jarvis" correctly firing `>>> wake word detected <<<`. Getting there required working around several real, non-obvious problems, all fixed and documented inline in the script:
  - `openwakeword`'s declared dependency `tflite-runtime` has zero prebuilt wheels for this platform on piwheels (any Python version — the package looks abandoned upstream). Fixed: install openWakeWord with `--no-deps` plus its actual runtime deps by hand (`onnxruntime`, `scipy`, `scikit-learn`, `tqdm`), forcing `inference_framework="onnx"` (already what this script targeted) instead of tflite. See `requirements.txt` for the two-step install command
  - `sounddevice`/PortAudio's ALSA backend dropped audio continuously ("input overflow" on nearly every callback) even with a zero-work callback — a PortAudio↔ALSA buffer/period negotiation bug specific to this USB mic, not a CPU or USB-bandwidth problem (both ruled out directly: plain `arecord` at the same rate ran gapless for 8s+, byte-count verified). Fixed: capture now reads raw PCM from an `arecord` subprocess directly, bypassing PortAudio for capture entirely
  - The mic's raw ALSA device only supports 44100/48000 Hz natively, not the 16kHz openWakeWord needs. Fixed: capture at 48000 (exact 3x multiple) and downsample to 16kHz in Python via `scipy.signal.decimate`
  - openWakeWord's embedding-model inference alone cost ~70ms of the 80ms/block real-time budget at its default single-threaded setting — a genuine CPU cost on the Pi 3B, not a bug. Fixed: `ncpu=2` (parallelize across 2 of the 4 cores) measured faster (~44ms) than both 1 thread (~70ms) and "auto"/4 threads (~58ms, likely contention overhead)
  - Training a real "hey sunny" model to replace the "hey_jarvis" placeholder is separate follow-up work (needs synthetic data generation via openWakeWord's own training notebooks)
- [ ] On wake-word trigger: immediately push a `listening` state to the face renderer (local, no network wait), then start streaming mic audio to the new server endpoint (Phase 6) — **not wired together yet**: the wake-word listener and the server endpoint both work independently (see Phase 6), but nothing yet connects the trigger to opening a `/ws/pi` connection and streaming mic audio into it
- [ ] Receive state events + TTS audio back from the server; forward state events to whatever Phase 4 becomes, play TTS audio through ALSA/3.5mm out — not built yet (the scrapped avatar-lab attempt connected to `/ws/pi` directly itself as a testing shortcut, not the real design — this Python client should own that connection instead)
- [x] Wake-on-LAN: `pi-client/wake_on_lan.py` — pure `socket`, no dependency, unit-tested (magic packet builds to the correct 102 bytes: 6×0xFF + 16×MAC)
- [ ] Write `pi-client/systemd/sunny-client.service`: `After=network-online.target`, `Wants=network-online.target` (this one genuinely needs WiFi up before it can reach the server, unlike the face service), `Restart=on-failure`
- [ ] `systemctl enable sunny-client.service` — confirm it waits for network before starting, and that a killed process gets restarted automatically
- [ ] Both services call `crash_reporter.report_crash_if_needed(...)` at startup and `mark_running()`/`mark_clean_shutdown()` around their main loop (see `pi-client/crash_reporter.py`) — mirrors the main server's own crash_check.py + Discord #warnings notice (already live there), but relayed through the new `POST /api/pi/crash-report` endpoint since the device has no Discord credentials of its own. Test by killing a running service with `kill -9` (an unclean death, unlike `systemctl stop`) and confirming the *next* start posts to #warnings.

## Phase 6 — Server-side endpoint (new code in `sunny_code`)

- [x] New lightweight local endpoint — `sunny_code/components/pi_companion.py`, a FastAPI WebSocket router (`/ws/pi`) matching `chatbot_ui.py`'s pattern exactly: takes the same **shared** `tasks_engine`/`briefing_engine`/`list_engine`/`scheduled_engine` instances as the Discord bot and console (not a second forked set), wired into `main.py` alongside the other routers. Separate from `voice_worker.py`'s Discord path entirely — no Opus, no DAVE encryption, no gateway heartbeats
- [x] Pipeline: receive streamed audio → Vosk STT → existing `handle_message()` → Piper TTS → stream audio + state events back — **verified end-to-end**: fed real Piper-synthesized speech ("what time is it") back in as 16kHz mono PCM, got a correct Vosk transcription, real `handle_message()` routing (hit the "no Claude API key configured locally" fallback — an existing environment gap, not a bug), and real reply audio back
- [x] State events sent at the right points — verified live: `thinking` → `speaking` → `idle` arrived in the correct order in the same test
- [ ] Dashboard feature: new function to call Anthropic's Usage & Cost Admin API (`usage_report/messages`, `cost_report`), using a **server-side-only** Admin API key, with caching (data lags ~5 min, endpoint is rate-limited to ~1 req/min for sustained polling)
- [ ] Wire "what's my Sonnet usage" (and similar) recognized intents to the dashboard function, returning a stats payload instead of a spoken-reply + state event

## Phase 7 — End-to-end integration testing

- [ ] Say the wake word → confirm instant local "listening" reaction (no visible lag)
- [ ] Confirm "thinking" shows during the server round-trip
- [ ] Confirm "speaking" plays with whatever visual talking indicator Phase 4 ends up being, synced to actual TTS audio
- [ ] Confirm return to "idle" after the reply finishes
- [ ] Ask for Sonnet usage → confirm the dashboard view appears and returns to the face afterward
- [ ] Test Wake-on-LAN command actually powers on the desktop PC
- [ ] Soak test: leave it running for a few hours, confirm no crashes, no memory creep, systemd units restart cleanly if killed

## Phase 8 — Enclosure

- [ ] 3D-print the case, sized around the GPIO-stacked Pi 3 B + screen as one fixed unit (see README's enclosure note)
- [ ] Leave the USB ports and microSD slot accessible
- [ ] Route power cable and mic placement in the design
- [ ] Final assembly

## After the desk unit works

Only then: start scoping the bedside clock variant (Phase list TBD — likely reuses Phases 4–7 largely as-is, with new work concentrated on Phases 1–3 for a smaller/different form factor and a clock-focused UI).
