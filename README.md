# Project SUNNY

A self-hosted voice assistant for personal productivity and automation.

## Overview

Sunny is an always-on voice assistant that lives on a bedside device and Lenovo mini PC. It wakes you up with personalized briefings, handles phone calls, and can control your home devices—all while prioritizing privacy and minimizing token usage through deterministic APIs over LLM calls.

## Core Features

- **Bedside Clock + Alarm** — Battery-backed hardware device with wake word detection
- **Morning Briefing** — Calendar, weather, tasks, commute info, email triage
- **Phone Integration** — Answer calls via Twilio and execute voice commands
- **Remote Power Control** — Wake desktop and control devices via Tailscale network
- **Smart Logging** — Discord activity channels, Notion sync, Obsidian vault mirroring

## Design Principles

- **Templates first, tokens last** — Fixed briefings with API-filled slots, no LLM overhead
- **LLM only for judgment** — Email triage, task interpretation, freeform conversation
- **No LLM for lookups** — Direct API calls for calendar, weather, traffic, financial data
- **Fail quietly** — System degrades gracefully if individual services are down

## Architecture

### Hardware
- **Brain**: Lenovo mini PC (always-on, Debian stable, headless)
- **Clock**: ESP32-S3 with OLED display, LiFePO4 battery, microphone, speaker
- **Network**: Tailscale mesh connecting all devices securely

### Services
- Voice: Sonic API, Piper TTS, Whisper STT, openWakeWord
- Communication: Twilio, Discord bot, Tailscale/MicroLink
- Data: Calendar, Weather API, Email, Traffic APIs
- Brain: Claude API, Notion, Obsidian vault, TrueNAS

## Getting Started

Documentation and build timeline are maintained in Notion:
- [Project Overview](https://app.notion.com/p/3bfd176c80f28176a2b7cbd5f9ff0a74)
- [The Plan](https://app.notion.com/p/3bfd176c80f2806fa5a0d727cc6550d3)
- [Architecture](https://app.notion.com/p/3bfd176c80f280bab9f2fe34f4199a98)

### Current Status
Phase 0 (Foundations) in progress — Debian setup, systemd configuration, local dashboard skeleton.

## Development

```bash
# Set up Python environment
python3 -m venv venv
source venv/bin/activate

# Dependencies to be added
pip install -r requirements.txt
```

## Costs

Estimated monthly spend: ~$5–$8
- Claude API (primary: Haiku ~$1.50, Sonnet ~$3)
- Twilio voice calls (~$0.01–$0.15/min)
- Sonic API (hosted TTS)
- Traffic/location APIs (~$3–$4)

Hard spending caps enforced at the provider level (Anthropic, Twilio).

## Security

- Caller ID allowlist + PIN for phone authentication
- API keys rotated regularly, never hardcoded
- Confirmation required for irreversible actions
- Tailscale network keeps devices off public internet
- Hard spending caps at provider accounts

## License

Internal project.
