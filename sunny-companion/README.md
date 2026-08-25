# Sunny Companion (hardware)

Physical device(s) for talking to Sunny — full conversational capability (wake word, voice in/out, LLM) in a dedicated piece of hardware instead of a phone/laptop. Two variants planned, built in this order:

1. **Desk unit (build first)** — hardwired, ~4"x4" screen, sits on the desk.
2. **Bedside clock** — later revision, likely reuses most of the desk unit's design with a clock-focused UI.

## Face / personality

Want an animated face on-screen to give Sunny personality — reactions, not just a static display or an LED ring.

**2026-08-23: the first implementation attempt (bible-strong-avatar-lab, an SVG/browser-rendered avatar) was built, tested, and scrapped.** The underlying state-machine design it was driven by (idle/listening/thinking/speaking, below) is independent of that library and stays — the server already emits exactly those state events over `/ws/pi` regardless of what renders them. What's genuinely open again: **which rendering approach replaces it.** That choice was also the reason WPE WebKit + Cog got picked for the board (needing a full browser engine) — if the replacement doesn't need a browser at all (e.g. a framebuffer/LVGL-style approach a microcontroller or a much lighter Pi could drive), the board choice may be worth revisiting too, not just the visuals. See Open Questions below.

## Desk unit — target hardware capabilities

- Screen: ~4in x 4in, drives the animated face
- Microphone: for wake word + voice capture
- Audio out: jack for speaker/headphones — user specified "8mm jack," which isn't a standard size (standard is 3.5mm/TRRS or 6.35mm/TRS) — **needs clarifying** before parts get ordered
- WiFi: connects to the home server running Sunny over the local network
- Wake-on-LAN: power on the desktop PC from the device — via an Ethernet port, or possibly offloaded to a small MCU (STM32) so it works even if the main board is asleep
- Hardwired power (no battery for v1)

## Hardware plan (2026-08-22 research pass)

Budget target: under $100 total including screen (case is 3D-printed separately, not counted). Boards considered along the way, cheapest to most capable: Pico/Pico 2 W (ruled out — microcontroller, KB of RAM, can't run any browser engine), Pi 1 Model B (ruled out — ARMv6, below WPE WebKit's ARMv7+ minimum), Pi Zero 2 W ($15, 512MB RAM), Pi 3 A+ ($25, 512MB RAM, built-in 3.5mm jack), **Pi 3 Model B ($32 as bought — chosen)**, Pi 4 2GB ($55, safe but blows the budget once SD card/PSU are counted).

**Board: Raspberry Pi 3 Model B, 1GB RAM.** Beats the Zero 2 W and 3 A+ on RAM (double, which directly helps the WPE WebKit rendering headroom) and has 4 full-size USB ports, full-size HDMI, and a built-in 3.5mm jack — no hub, no HDMI adapter, no USB audio dongle needed, unlike the smaller boards. Quad-core Cortex-A53 (ARMv8) clears the WPE WebKit + Cog requirement (Chromium itself is too heavy for 1GB RAM — WPE WebKit/Cog remains the plan, same as for the smaller boards; not yet benchmarked against the specific `avatar-web` SVG output, so still worth prototyping before writing much client code).

**Amazon-pricing caveat:** the "official" $15/$25/$35 board prices only hold at authorized resellers (PiShop, Adafruit, CanaKit's own site, Micro Center). Amazon's listings are mostly bundled starter kits at 2-3x that price (confirmed live: Pi Zero 2 W kits at $90-110, Pi 4 2GB at $84-90 "Typical: $98.91") — check off-Amazon if buying the bare board matters.

### Bill of materials (final)

| Part | Price | Link |
|---|---|---|
| Raspberry Pi 3 Model B (1GB) | $32 | (bought) |
| Waveshare 4" HDMI LCD, 800×480, resistive touch — **GPIO + HDMI direct-connect**, no cables needed | $38.99 | [amazon.com/dp/B07P5H2315](https://www.amazon.com/dp/B07P5H2315) |
| SunFounder USB 2.0 Mini Microphone | $7.99 | [amazon.com/dp/B01KLRBHGM](https://www.amazon.com/dp/B01KLRBHGM) |
| SanDisk 32GB microSD | $17.50 | [amazon.com/dp/B08HYDH7JF](https://www.amazon.com/dp/B08HYDH7JF) |
| Micro-USB 5V/2.5A power supply | $9.10 | [amazon.com/dp/B0FFS9X1DH](https://www.amazon.com/dp/B0FFS9X1DH) |
| **Total** | **~$105.58** | ~$5.58 over the $100 target — closest achievable with verified, genuinely Pi-compatible parts |

No additional cables needed: the screen direct-connects via HDMI port + 40-pin GPIO header (video, touch, and power all through that one connection), the mic is a self-contained USB plug, the PSU has its own attached cable, and the SD card slots straight into the board.

**Enclosure implication:** GPIO-stacking means the screen sits directly on/against the board — it's not something that can be cable-separated into different parts of the case. The 3D-printed enclosure needs to treat the Pi + screen as one fixed stacked unit, while still leaving the USB ports (for the mic) and microSD slot accessible (they're on the opposite edges of the board from the GPIO header, so no physical conflict with the stacked screen).

## Software architecture (decided)

The device is a **thin client** — no local LLM, no Discord voice client. The server is the brain:

- **Local on the Pi:** a lightweight wake-word engine (e.g. openWakeWord or a small Vosk grammar) listens continuously on the USB mic. On trigger, the device switches to "listening" **instantly, before any network round-trip**, then streams audio to a **new local endpoint** added to the Sunny server.
- **Server-side (new code, not `voice_worker.py`):** the new endpoint reuses the existing `stt.py`/`tts.py` components directly — no Discord, no Opus/DAVE encryption, no gateway heartbeats. It runs Vosk STT → existing LLM/handle_message pipeline → Piper TTS, and streams both the TTS audio and small **state events** back to the device (`{"state": "thinking"}`, `{"state": "speaking", "emotion": "happy"}`, `{"state": "idle"}`).
- This bypasses `sunny_code/voice_worker.py`'s Discord-voice-channel design entirely for this device — that pipeline stays as-is for Discord users, this is a parallel path.

## Face behavior — state machine (implementation-agnostic, still the plan)

This part survives the scrapped avatar-lab attempt unchanged — whatever renders the face next still needs to react to these same states, since the server (`pi_companion.py`) already emits them over `/ws/pi`:

- **Idle** — resting, waiting for the wake word.
- **Listening** — triggered locally the instant the wake-word engine fires (no network wait).
- **Thinking** — while waiting on the server's LLM reply; covers the latency gap so it doesn't look frozen.
- **Searching** — a distinct state for the extra gap a live web search adds (server-side: `llm_client.ask_claude_stream`'s `on_search_start`), rather than lumping it into "thinking."
- **Speaking** — while TTS audio plays; some kind of "talking" indicator driven by the **audio's live amplitude** is the plan (no phoneme/viseme timing available from Vosk or Piper, so true lip-sync isn't on the table regardless of renderer — amplitude-driven is the cheap, well-worn substitute).
- **Emotion overlay (v2)** — server can tag a reply with a coarse mood (happy/concerned/playful/apologetic); device shows some renderer-specific expression for it. Not built yet.

## Stat dashboard feature (e.g. "what's my Sonnet usage")

A second display mode alongside the face, not bolted onto it — Cog swaps from the avatar view to a small stats view for a few seconds on request, then back to idle.

- Backed by Anthropic's **Usage & Cost Admin API** (`GET /v1/organizations/usage_report/messages` for token counts by model/time-bucket, `GET /v1/organizations/cost_report` for USD cost, daily granularity). Confirmed Sunny's org already has API billing set up (`anthropic` package is in [requirements.txt](../requirements.txt)), so minting an Admin key is straightforward.
- **Security constraint:** the Admin API key (`sk-ant-admin01-...`) is far more powerful than Sunny's regular API key (full org usage/cost visibility) and **must live server-side only** — never on the physical device. The server fetches and formats the numbers; the device only ever receives a rendered stats payload, never the credential.
- Data lags ~5 min and the endpoint is rate-limited to roughly 1 request/minute for sustained polling — server should poll occasionally and cache, not fetch live on every request.
- Two dashboard presets planned to start: "today's usage" and "cost this month."

## Open questions

- **What replaces the scrapped avatar-lab renderer.** Options span a wide range — another SVG/browser-based library, a simpler framebuffer/LVGL-style approach, hand-drawn sprite animations, something else entirely — and the choice feeds back into whether a full browser engine (and therefore the current board) is even needed. **2026-08-23: leaning candidate — Python/pygame direct-to-framebuffer (`SDL_VIDEODRIVER=kmsdrm`), not another browser attempt**, so the renderer lives in the same process as the rest of the Python device client instead of behind a WebSocket hop; see [BUILD_PLAN.md](BUILD_PLAN.md)'s Phase 4 for the amplitude-reactive shape plan (mic RMS while listening, synthesized sine "breathing" while thinking, TTS buffer RMS while speaking, hue shift for the emotion overlay). Built as a standalone prototype and verified running on a dev machine, with its dependency stack also validated to install cleanly on emulated Pi arm64 — but not yet validated for real frame timing on actual Pi 3 B hardware, and not yet wired into the device client.
- Whether the board choice (Pi 3 B, picked partly to run WPE WebKit + Cog) still holds once the above is decided, or whether a lighter/cheaper board becomes viable again.
- Enclosure design for the desk form factor (3D printed, separate from the BOM) — needs to account for the GPIO-stacked screen geometry once a renderer is chosen.
- Exact expression/mood set for the emotion overlay (how many, what triggers each) — deferred until there's a renderer to define them against.

## Status

Board bought (Pi 3 Model B, $32). Server-side is real and working: `/ws/pi` (Vosk STT → LLM → Piper TTS, with idle/listening/thinking/searching/speaking state events), the Anthropic usage dashboard's Admin API design, and crash detection + Discord alerting for the device's future services are all built server-side (see [BUILD_PLAN.md](BUILD_PLAN.md)). The avatar-lab-based face implementation was built, tested, and scrapped (2026-08-23); its pygame-based replacement has since been prototyped and verified on a dev machine (amplitude-reactive shape, emotion overlay), with the dependency stack also validated on emulated Pi arm64 — but it's not yet validated for real frame timing on actual Pi 3 B hardware, and not yet wired into the device client. That's the open piece now.
