# Project SUNNY

A self-hosted voice assistant for personal productivity and automation.

## Overview

Sunny is an always-on personal assistant that runs on a Lenovo mini PC today, reachable via Discord (text and live voice) and terminal chat, with a standalone `project-dashboard` app providing a web UI alongside it. Phone calls and home-device control are still planned, not built — see Core Features below. Real task/calendar/weather data drives fixed templates wherever a fact is a fact; Claude is only called for genuine judgment, all while prioritizing privacy and minimizing token usage.

## Core Features

- **Discord Voice** — Persistent live voice conversation (wake-word-gated, no join command — Sunny just stays in a configured voice channel), fully local STT/TTS (Vosk + Piper), plus one-shot `/speak` TTS
- **Morning Briefing** — Calendar, weather, tasks; genuinely open-ended questions get a real Claude answer
- **Google Calendar + Gmail** — Calendar read *and* write via natural language ("add dentist appointment..."); Gmail read-only, both via one Google Sign-In
- **Spotify Voice Control** — play/pause/skip/volume/what's-playing, from any interface
- **Class Setup** — Paste a syllabus (`/classsetup` or "set up my classes") and get recurring calendar events, due-date/exam events, and proactive Discord reminders
- **Bedside Clock + Alarm** — Battery-backed hardware device with wake word detection (not yet built — Discord voice already delivers the conversational half today)
- **Phone Integration** — Answer calls via Twilio and execute voice commands (not yet built)
- **Remote Power Control** — Wake desktop and control devices via Tailscale network (not yet built)
- **Smart Logging** — Discord activity channels (live) and Obsidian vault mirroring (live); Notion sync is not built

Beyond the hardware Clock, phone integration, and remote power control, everything above is built and live — see Current Status below and [[./phases.md]] for the full built-vs-planned breakdown.

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
- Voice: Piper TTS + Vosk STT (both live, fully local, free); Sonic API, Whisper STT, and openWakeWord are planned for the Clock hardware, not yet built
- Communication: Discord bot (live — text + voice), Tailscale (live); Twilio and MicroLink are not yet built
- Data: Google Calendar + Gmail (live via Sign-In), OpenWeatherMap (live); Traffic APIs not yet built
- Brain: Claude API (live — judgment, freeform conversation, health checks), Obsidian vault (live); Notion sync and TrueNAS integration are planned, not built

## Getting Started

**Quick Start** (30 seconds):
```bash
chmod +x run.sh
./run.sh
# Open: http://127.0.0.1:5000 (redirects to the project-dashboard web UI, if deployed)
```

See [[./QUICKSTART.md]] for full quick-start guide.

### Current Status
Phase 0 (Foundations) mostly complete — briefing engine (real task data, honest "not connected" for everything else), task system and lists (Obsidian vault, markdown), alarms/reminders (SQLite, unaffected by the vault-storage move), terminal-chat/Discord-driven, Discord bot connected and live, all working. Sunny's own web console was retired 2026-09-13 — the standalone `project-dashboard` app now owns the web UI (see [[./architecture/dashboard]]). `run.sh` manages Python dependencies automatically (no manual venv setup). Systemd autostart is done (`Restart=always`, see `SETUP_LINUX.md`).

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

**Today**: well under $1/month in practice — Piper and Vosk are fully local and free; Claude (Haiku) is only called for genuinely open-ended questions, study reviews, and the weekly health check — light, occasional traffic. Live numbers: `GET /api/dashboard/spend/today` / `/spend/month`, `/usage` in Discord, or ask "health check."

Monthly spend once phone integration (still not built) is live, on top of the above: ~$4–$5
- Twilio voice calls (~$0.01–$0.15/min)
- Traffic/location APIs (~$3–$4)
- Sonic API (hosted TTS — only if used instead of the free local Piper fallback)

Hard spending caps enforced both in-app (`daily_spend_cap`/`monthly_spend_cap` in `.env`) and at the provider account level (Anthropic).

## Security

- Caller ID allowlist + PIN for phone authentication (planned, once phone integration exists)
- API keys rotated regularly, never hardcoded
- No confirmation step today for destructive actions (delete a task, cancel a calendar event, delete a Discord channel/role) — they run immediately, matching this being a single-user personal tool
- Tailscale network keeps devices off public internet
- Hard spending caps at provider accounts

## License

Internal project.
