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

**Quick Start** (30 seconds):
```bash
chmod +x run.sh
./run.sh
# Open: http://127.0.0.1:5000
```

See [[./QUICKSTART.md]] for full quick-start guide.

### Current Status
Phase 0 (Foundations) complete — Briefing system, task management, web chatbot UI, and live system console all working. `run.sh` manages Python dependencies automatically (no manual venv setup).

### Documentation
- [[./QUICKSTART.md]] — Get started in 30 seconds
- [[./architecture/index.md]] — System architecture
- [[./phases.md]] — Build timeline (phases 0-7)
- [[./TASK_SYSTEM.md]] — Task management system
- [[./BACKLOG.md]] — Deferred items not tied to a specific phase

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
