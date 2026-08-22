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

Budget target: under $100 total including screen (case is 3D-printed separately, not counted). Two board options were researched:

- **Pi 4 (2GB), $55** — safe bet, Chromium kiosk is proven for this kind of UI, but all-in cost (board + screen + mic + SD card + PSU) lands around $103-111, slightly over budget.
- **Pi Zero 2 W, $15** — chosen path. Full Chromium is reportedly "painfully slow" on its 512MB RAM (swaps to the SD card), so this only works by using **WPE WebKit + Cog** instead — a lightweight, hardware-accelerated kiosk browser stack built for exactly this class of board. Not yet benchmarked against the specific `avatar-web` SVG output this project wants to use — **prototype this before buying the screen**, since it's the one unproven piece of the plan and the screen is the priciest single item.

### Bill of materials (Pi Zero 2 W path)

| Part | Price |
|---|---|
| Raspberry Pi Zero 2 W | $15 |
| 4" square HDMI touchscreen, 720×720 | $33 |
| USB mini microphone | $7 |
| microSD card (32GB) | $8 |
| Micro-USB power supply (5V/2.5A) | $7 |
| Mini-HDMI → HDMI cable/adapter | $5 |
| Micro-USB OTG hub (Zero 2 W has only one USB data port; mic + touchscreen both need it) | $6 |
| **Total** | **~$81** (+ ~$4 for a USB audio dongle, since the Zero 2 W has no onboard 3.5mm jack) |

Notes:
- User confirmed audio jack should be **3.5mm**, not 8mm as originally stated.
- Wake-on-LAN needs no special hardware — it's a UDP magic packet sent over WiFi to the target PC's MAC address, doable in a few lines of Python from whatever board ends up in the device. No STM32/Ethernet required for this specifically.
- If the screen doesn't need to be tappable, dropping touch removes the USB hub requirement (mic gets the single data port to itself) and likely finds a cheaper panel too.
- No spare parts (SD card, PSU) on hand — full BOM applies as priced.

## Open questions

- Validate WPE WebKit/Cog can render the `avatar-web` SVG output smoothly on the Zero 2 W before buying the screen
- Does the desk unit need touch, or just display? Affects screen pick and whether the USB hub is needed at all
- **Software architecture note:** the existing voice pipeline (`sunny_code/voice_worker.py`) is built around joining a **Discord voice channel** (`/join`), with Vosk STT + Piper TTS running server-side over Discord's voice transport. Need to decide whether the desk unit connects the same way (acts as a Discord voice client) or whether a new direct local audio channel to the backend gets built instead, bypassing Discord entirely. Doesn't change the hardware picked above, but is a real fork for the client software that talks to `sunny_code`.
- Enclosure design for the desk form factor (3D printed, separate from this BOM)

## Status

Planning stage — board path chosen (Pi Zero 2 W + WPE WebKit/Cog), no hardware ordered yet, no code in this folder yet.
