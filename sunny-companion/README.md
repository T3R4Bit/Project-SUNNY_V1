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

## Open questions

- Confirm audio jack size (3.5mm TRRS most likely)
- Main board choice: Pi-class SBC (for the JS-based avatar) vs. microcontroller + separate display driver — depends on how much of the avatar-lab rendering approach we keep vs. reimplement in something lighter
- Screen part number / driver (SPI vs HDMI vs DSI) — depends on board choice above
- How this talks to the existing Sunny backend (`sunny_code/`) — presumably over the local network, reusing the existing voice pipeline rather than duplicating it on-device
- Enclosure design for the desk form factor

## Status

Planning stage — no hardware ordered yet, no code in this folder yet.
