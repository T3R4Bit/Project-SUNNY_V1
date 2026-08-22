# Sunny Companion (hardware)

Physical device(s) for talking to Sunny — full conversational capability (wake word, voice in/out, LLM) in a dedicated piece of hardware instead of a phone/laptop. Two variants planned, built in this order:

1. **Desk unit (build first)** — hardwired, ~4"x4" screen, sits on the desk.
2. **Bedside clock** — later revision, likely reuses most of the desk unit's design with a clock-focused UI.

## Face / personality

Reference: [avatars.bible-strong.app](https://avatars.bible-strong.app/) / [smontlouis/bible-strong-avatar-lab](https://github.com/smontlouis/bible-strong-avatar-lab) — want an animated face on-screen to give Sunny more personality, similar visual style to that avatar system.

**Technical constraint to plan around:** that avatar renderer is SVG + React/DOM (`@bible-strong/avatar-web` for vanilla JS/ESM, portable `.avatar.json` character definitions), running in a browser engine — not something a bare microcontroller (ESP32/STM32) can drive. It implies the screen needs to be driven by something that can run a JS/browser runtime (e.g. a Pi-class SBC in kiosk mode), rather than a microcontroller pushing raw framebuffer graphics. Worth confirming before locking in a board — if we want the exact SVG avatar-web output, plan for a Linux SBC as the display driver; a microcontroller could still own lower-level jobs (power, WoL, audio amp control) alongside it.

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

## Open questions

- **Software architecture note:** the existing voice pipeline (`sunny_code/voice_worker.py`) is built around joining a **Discord voice channel** (`/join`), with Vosk STT + Piper TTS running server-side over Discord's voice transport. Need to decide whether the desk unit connects the same way (acts as a Discord voice client) or whether a new direct local audio channel to the backend gets built instead, bypassing Discord entirely. Doesn't change the hardware picked above, but is a real fork for the client software that talks to `sunny_code`.
- Validate WPE WebKit/Cog can render the `avatar-web` SVG output smoothly on the Pi 3 B before writing much client code
- Enclosure design for the desk form factor (3D printed, separate from this BOM) — needs to account for the GPIO-stacked screen geometry above

## Status

Board bought (Pi 3 Model B, $32). Rest of the BOM picked with real Amazon links, not yet ordered. No code in this folder yet.
