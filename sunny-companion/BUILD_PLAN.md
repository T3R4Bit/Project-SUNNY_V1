# Sunny Companion — Build Plan (Desk Unit v1)

Step-by-step, in dependency order. Check items off as they're done. Each phase assumes the previous one works before moving on — don't build the avatar app against a kiosk stack that hasn't been proven to boot yet.

## Phase 0 — Parts arrival

- [x] Board bought (Pi 3 Model B, $32)
- [ ] Rest of BOM ordered (screen, mic, SD card, PSU — see [README.md](README.md) for links)
- [ ] Parts arrive

## Phase 1 — Base OS

- [ ] Flash **Raspberry Pi OS Lite (64-bit, Bookworm)** to the microSD card — headless, no desktop environment
- [ ] First boot: enable SSH, set WiFi credentials, set hostname (e.g. `sunny-companion.local` via avahi) so the server can find it by name
- [ ] `sudo apt update && sudo apt upgrade`
- [ ] Confirm the board is reachable over SSH on the home WiFi network before doing anything else

## Phase 2 — Kiosk display stack

- [ ] `sudo apt install cog libwpewebkit-1.1-0`
- [ ] Test: `cog --platform=drm https://example.com` renders full-screen with no X11/Wayland compositor running — confirms the screen (once attached) and DRM/KMS path work
- [ ] Attach the Waveshare screen (GPIO + HDMI direct-connect) and repeat the test on real hardware
- [ ] Write a systemd unit that launches `cog --platform=drm <local avatar app URL>` at boot, restarts on crash
- [ ] Confirm boot-to-face works with no login prompt, no manual steps

## Phase 3 — Audio I/O

- [ ] Confirm 3.5mm audio out works: `speaker-test` or `aplay` a test WAV through the Pi's onboard jack
- [ ] Plug in the USB mic, confirm it's detected: `arecord -l`
- [ ] Record a short clip and play it back to confirm mic quality/levels: `arecord -d 5 test.wav && aplay test.wav`
- [ ] Set explicit default ALSA input/output devices (`/etc/asound.conf` or `.asoundrc`) so they don't shift if USB device order changes on reboot

## Phase 4 — Avatar app (built on a dev machine, deployed to the Pi)

- [ ] Design the character in the bible-strong-avatar-lab editor; export the `.avatar.json`
- [ ] Build the expression set: idle, listening, thinking, speaking, plus 2–4 emotion presets (see README's open question — nail down the exact list here)
- [ ] Wire up `@bible-strong/avatar-web` (vanilla JS/ESM, no React needed) to load the character and play the animations designed above, using the library's loop / play-once / ping-pong playback modes
- [ ] Add amplitude-driven mouth movement for the "speaking" state (sample the live audio's volume envelope, map to mouth-open amount)
- [ ] Add a small local WebSocket client in the page's JS that listens for state messages (`{"state": "listening"}` etc.) and drives the animation state machine
- [ ] Bundle as a static build (Vite or similar) — confirm it doesn't need a server, so Cog can load it via `file://` or a trivial local static server
- [ ] Copy the built static bundle onto the Pi; point the Phase 2 systemd unit's Cog invocation at it
- [ ] **Validation checkpoint** (flagged as a risk earlier): confirm this renders smoothly via Cog's DRM backend on the actual Pi 3 B hardware before investing more time in the expression set

## Phase 5 — Device client (Python, runs on the Pi)

- [ ] Pick and install a local wake-word engine (openWakeWord or a small Vosk grammar) listening on the USB mic
- [ ] On wake-word trigger: immediately push a `listening` state to the avatar app (local, no network wait), then start streaming mic audio to the new server endpoint (Phase 6)
- [ ] Receive state events + TTS audio back from the server; forward state events to the avatar app's WebSocket, play TTS audio through ALSA/3.5mm out
- [ ] Wake-on-LAN: small script sending a UDP magic packet to the desktop PC's MAC address, triggered by a specific recognized command from the server
- [ ] Wire this client into its own systemd unit, started after `network-online.target` (needs WiFi up first)

## Phase 6 — Server-side endpoint (new code in `sunny_code`)

- [ ] New lightweight local endpoint (WebSocket or similar) — separate from `sunny_code/voice_worker.py`'s Discord path, reusing the existing `stt.py`/`tts.py` components directly
- [ ] Pipeline: receive streamed audio → Vosk STT → existing LLM/`handle_message` logic → Piper TTS → stream audio + state events back
- [ ] State events sent at the right points: `thinking` right after audio is received, `speaking` (with optional `emotion` tag) when TTS starts streaming, `idle` when done
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
