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

None of the above beyond the briefing engine, task system, lists, and alarms/reminders are built yet — see Current Status below and [[./phases.md]] for what's actually working today versus planned.

## Design Principles

- **Templates first, tokens last** — Fixed briefings with API-filled slots, no LLM overhead
- **LLM only for judgment** — Email triage, task interpretation, freeform conversation
- **No LLM for lookups** — Direct API calls for calendar, weather, traffic, financial data
- **Fail quietly** — System degrades gracefully if individual services are down

## Architecture

### Hardware
- **Brain**: Lenovo mini PC (always-on, Ubuntu Server 26.04 LTS, headless — no GUI)
- **Clock**: ESP32-S3 with OLED display, LiFePO4 battery, microphone, speaker (not yet built)
- **Network**: Tailscale mesh connecting all devices securely

### Services
- Voice: Sonic API, Piper TTS, Whisper STT, openWakeWord (not yet built)
- Communication: Twilio, Discord bot, Tailscale/MicroLink (Tailscale is live; Twilio and Discord bot are not yet built)
- Data: Calendar, Weather API, Email, Traffic APIs (not yet built — briefing engine runs on mock data)
- Brain: Claude API, Notion, Obsidian vault, TrueNAS (not yet built — no LLM calls are wired up)

## Getting Started

**Quick Start** (30 seconds):
```bash
chmod +x run.sh
./run.sh
# Open: http://127.0.0.1:5000 (redirects to /chatbot)
```

See [[./QUICKSTART.md]] for full quick-start guide.

### Current Status
Phase 0 (Foundations) mostly complete — briefing engine (real task data, honest "not connected" for everything else), task system, lists, and alarms/reminders (all SQLite + chatbot/Discord-driven), web chatbot UI (at `/chatbot`, `/` redirects there), Discord bot (code complete, needs a bot token connected), and live system console (`/console`) all working. `run.sh` manages Python dependencies automatically (no manual venv setup). Systemd autostart is the main piece still outstanding.

### Documentation
- [[./QUICKSTART.md]] — Get started in 30 seconds
- [[./architecture/Mind-Map.md]] — System architecture overview
- [[./phases.md]] — Build timeline (phases 0-7)
- [[./TASK_SYSTEM.md]] — Task management system
- [[./architecture/lists.md]] — Lists (groceries, packing, anything checkable)
- [[./architecture/alarms-reminders.md]] — Alarms & Reminders (ping Discord when due)
- [[./architecture/discord-bot.md]] — Discord bot setup (drives all three subsystems above)
- [[./BACKLOG.md]] — Deferred items not tied to a specific phase

## Costs

Estimated monthly spend once the voice/phone phases are live: ~$5–$8
- Claude API (primary: Haiku ~$1.50, Sonnet ~$3)
- Twilio voice calls (~$0.01–$0.15/min)
- Sonic API (hosted TTS)
- Traffic/location APIs (~$3–$4)

**Today**: $0 — no LLM or paid API is called yet. Tasks, lists, and alarms/reminders are real data; weather/calendar/email/commute/health/news say "not connected" instead of faking an answer.

Hard spending caps enforced at the provider level (Anthropic, Twilio).

## Security

- Caller ID allowlist + PIN for phone authentication (planned, once phone integration exists)
- API keys rotated regularly, never hardcoded
- Confirmation required for irreversible actions
- Tailscale network keeps devices off public internet
- Hard spending caps at provider accounts

## License

Internal project.
