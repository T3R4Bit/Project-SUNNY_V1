# Sunny Companion — Build Plan (Desk Unit v1)

Step-by-step, in dependency order. Check items off as they're done. Each phase assumes the previous one works before moving on — don't build the avatar app against a kiosk stack that hasn't been proven to boot yet.

## Repo layout

Everything lives in this one repo (Project-SUNNY) — no separate repo for the Pi side. The Pi gets a plain `git clone` of the whole thing (the tracked repo is ~7MB; all the bulky stuff — `venv/`, `piper_voices/`, `vosk_models/`, `*.db` — is gitignored, so cloning it onto the Pi doesn't pull any of that):

```text
sunny-companion/
├── README.md / BUILD_PLAN.md
└── pi-client/                          ← everything that runs ON the Pi
    ├── wake_word_client.py             (Phase 5)
    ├── systemd/
    │   ├── sunny-face.service          (Phase 2 — Cog kiosk)
    │   └── sunny-client.service        (Phase 5 — wake-word + network client)
    └── avatar-app/
        ├── src/                        (edited on a dev machine)
        └── dist/                       (built static bundle, committed — Pi never runs Node/Vite)
```

The new server-side endpoint (Phase 6) stays in `sunny_code/`, alongside the existing `stt.py`/`tts.py`/`voice_worker.py` — not in `sunny-companion/`.

Updating the device going forward is just `git pull` on the Pi + restarting the two systemd services below. Set up a dedicated read-only deploy key / fine-grained PAT for the Pi to clone and pull with (same pattern as the existing Lenovo server SSH key) rather than putting personal GitHub credentials on a physically-accessible embedded device.

## Phase 0 — Parts arrival

- [x] Board bought (Pi 3 Model B, $32)
- [ ] Rest of BOM ordered (screen, mic, SD card, PSU — see [README.md](README.md) for links)
- [ ] Parts arrive

## Phase 1 — Base OS

- [ ] Flash **Raspberry Pi OS Lite (64-bit, Bookworm)** to the microSD card — headless, no desktop environment
- [ ] First boot: enable SSH, set WiFi credentials, set hostname (e.g. `sunny-companion.local` via avahi) so the server can find it by name
- [ ] `sudo apt update && sudo apt upgrade`
- [ ] Confirm the board is reachable over SSH on the home WiFi network before doing anything else
- [ ] Set up a dedicated read-only deploy key / fine-grained PAT, `git clone` this repo onto the Pi (see Repo layout above)

## Phase 2 — Kiosk display stack

- [ ] `sudo apt install cog libwpewebkit-1.1-0`
- [ ] Test: `cog --platform=drm https://example.com` renders full-screen with no X11/Wayland compositor running — confirms the screen (once attached) and DRM/KMS path work
- [ ] Attach the Waveshare screen (GPIO + HDMI direct-connect) and repeat the test on real hardware
- [ ] Write `pi-client/systemd/sunny-face.service`: launches `cog --platform=drm <local avatar app URL>`, `WantedBy=multi-user.target` (no network dependency — static files are already on disk, so the face should appear immediately on boot rather than waiting on WiFi), `Restart=on-failure`
- [ ] `systemctl enable sunny-face.service` — confirm boot-to-face works with no login prompt, no manual steps, and that it survives a crash (kill the process, confirm systemd restarts it)

## Phase 3 — Audio I/O

- [ ] Confirm 3.5mm audio out works: `speaker-test` or `aplay` a test WAV through the Pi's onboard jack
- [ ] Plug in the USB mic, confirm it's detected: `arecord -l`
- [ ] Record a short clip and play it back to confirm mic quality/levels: `arecord -d 5 test.wav && aplay test.wav`
- [ ] Set explicit default ALSA input/output devices (`/etc/asound.conf` or `.asoundrc`) so they don't shift if USB device order changes on reboot

## Phase 4 — Avatar app (built on a dev machine, deployed to the Pi)

- [ ] Design the character in the bible-strong-avatar-lab editor; export the `.avatar.json` (currently using the library's own sample character, "Strobi", recolored yellow — not a custom design yet)
- [x] Build the expression set: idle, listening, thinking, speaking, plus emotion presets — done using expressions already on the placeholder character (idle/listening/thinking/speaking all expanded to 4-7 step variety; happy/confused/surprised/sad/etc. emotion animations were already present)
- [x] Wire up `@bible-strong/avatar-web` to load the character and play animations using the library's loop/play-once/ping-pong modes — done in `pi-client/avatar-app/src/main.ts`
- [x] Add amplitude-driven modulation for the "speaking" state — done, but as an **external CSS pulse** on the avatar host element (`--speak-pulse`), not literal mouth movement: avatar-web's public API has no raw parameter control and this character has no mouth geometry at all, so a CSS scale pulse driven by a live `AnalyserNode` reading the actual TTS audio is the honest implementation
- [x] Add a small local WebSocket client in the page's JS that listens for state/audio messages and drives the animation state machine + audio playback — done; currently connects directly to `/ws/pi` for testing (see Phase 5 note below on where this wiring moves once the Python device client exists)
- [ ] Bundle as a static build (Vite or similar) — confirm it doesn't need a server, so Cog can load it via `file://` or a trivial local static server (still only tested via `vite dev`, haven't run a production `vite build` yet)
- [ ] Copy the built static bundle onto the Pi; point the Phase 2 systemd unit's Cog invocation at it
- [ ] **Validation checkpoint** (flagged as a risk earlier): confirm this renders smoothly via Cog's DRM backend on the actual Pi 3 B hardware before investing more time in the expression set

## Phase 5 — Device client (Python, runs on the Pi)

- [x] Pick and install a local wake-word engine — `pi-client/wake_word_listener.py`, using openWakeWord. **No pretrained "hey sunny" model exists** — using "hey_jarvis" as a placeholder to prove the mechanism (continuous low-compute listening → trigger callback) actually works; verified the model loads and stays near-zero on silence/noise, and the live audio stream opens and runs without crashing. Not yet verified against a real spoken wake word — training a real "hey sunny" model is separate follow-up work (needs synthetic data generation via openWakeWord's own training notebooks)
- [ ] On wake-word trigger: immediately push a `listening` state to the avatar app (local, no network wait), then start streaming mic audio to the new server endpoint (Phase 6) — **not wired together yet**: the wake-word listener and the server endpoint both work independently (see Phase 6), but nothing yet connects the trigger to opening a `/ws/pi` connection and streaming mic audio into it
- [ ] Receive state events + TTS audio back from the server; forward state events to the avatar app's WebSocket, play TTS audio through ALSA/3.5mm out — not built; today the avatar app connects to `/ws/pi` directly itself for testing purposes instead
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
- [ ] Confirm "speaking" plays with mouth movement synced to actual TTS audio
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
