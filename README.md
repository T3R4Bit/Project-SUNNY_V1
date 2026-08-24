# Project SUNNY

## A Self-Hosted Voice Assistant

Sunny is an always-on personal voice assistant that lives on a bedside clock and Lenovo mini PC. It wakes you with personalized briefings, answers phone calls, and automates routine tasks—all while respecting privacy and minimizing API costs through deterministic logic.

---

## Core Features

**Discord Voice** — `/speak`, `/join`, `/leave`. Say "Hey Sunny" and have a real spoken conversation with the exact same brain as text chat — fully local and free (Piper TTS, Vosk STT), no clock hardware required. Built and live ahead of the bedside-clock hardware below — see `sunny-vault/docs/architecture/voice-join.md`.

**Bedside Clock** — Battery-backed ESP32 device with wake word detection, voice I/O, and an alarm that survives power cuts. (Hardware phase, not yet built — Discord voice already delivers the same conversational capability today.)

**Morning & Evening Briefings** — Personalized summaries pulled from calendar, weather, and tasks. No LLM calls for facts — just real API data in a fixed template; genuinely open-ended questions that don't fit a template get a real answer from Claude instead of a canned "I don't know."

**Phone Interface** — Callable via Twilio. Execute voice commands, create tasks, and have real-time conversations while you hold the line. (Not yet built.)

**Smart Logging** — All actions logged to Discord, Obsidian, and Notion. Permanent audit trail, searchable, always in sync.

---

## Design Philosophy

**Templates First, Tokens Last**
Briefings are fixed scripts with API-filled slots. No LLM overhead for facts.

**LLM Only for Judgment**
Claude API handles email triage, task interpretation, and freeform conversation. Never for lookups.

**Fail Quietly**
If weather API is down, briefing continues without it. Alarm still fires. System degrades, never crashes.

**Local-First, Secure**
Tailscale mesh keeps all devices off the public internet. No port forwarding, no exposed APIs, works from anywhere via DERP relays.

---

## Architecture at a Glance

```
Clock (ESP32-S3) Brain (Lenovo Mini PC) External APIs
   | | |
   +-- Wake word ------+ | +-- Calendar API -----+
   | | | |
   +-- Microphone ---> | | +-- Weather API
   | | ---> | |
   +-- Speaker <------ | | +-- Email API
   | | | |
   +-- Battery Monitor | +-- Traffic API
                       |
                    Tailscale Mesh
                       |
                   Priority Queue
                       |
    +-- LLM (Claude) --+-- Direct APIs
    |
    +-- TTS (Sonic/Piper)
    |
    +-- Obsidian Staging --> Notion Sync
    |
    +-- Discord Logging
```

---

## Current Status

**Phase 0** — Foundations (Complete)
- Ubuntu Server 26.04 LTS on Lenovo mini PC
- Briefing system with Q&A engine (real task data, real weather/calendar once connected, honest gaps elsewhere) plus a Claude-backed fallback for genuinely open-ended questions
- Task management system — natural language, no command prefix needed
- Lists (groceries, packing, anything checkable) — see `sunny-vault/docs/architecture/lists.md`
- Alarms & Reminders — time-based, ping Discord when due — see `sunny-vault/docs/architecture/alarms-reminders.md`
- Device/source tracking (web/discord/api) on every task, list item, and alarm
- Discord bot for tasks/lists/alarms/reminders, plus three voice commands (`/speak`, `/join`, `/leave` — live spoken conversation, wake-word gated, fully local STT/TTS) — see `sunny-vault/docs/architecture/discord-bot.md` and `voice-join.md`
- Console over Tailscale (`/console`, `/` and `/chatbot` redirect there) — chat plus live system stats (CPU, RAM, disk, network, temp) and Google sign-in status in one page
- Weather (OpenWeatherMap) and Calendar/Gmail (Google Sign-In) connected with real data
- Comprehensive documentation

**Next** — Phase 1: Tailscale networking verified, Phase 2: Clock hardware (voice I/O itself is already live via Discord, ahead of the hardware)

See `sunny-vault/docs/phases.md` for full build timeline.

---

## Documentation

- **Architecture** — `sunny-vault/docs/architecture/` (component docs with cross-references)
- **Build Timeline** — `sunny-vault/docs/phases.md` (phases 0-7 with checklists)
- **Task System** — `sunny-vault/docs/TASK_SYSTEM.md` (natural-language commands + Discord bot)
- **Lists** — `sunny-vault/docs/architecture/lists.md` (groceries, packing, anything checkable)
- **Alarms & Reminders** — `sunny-vault/docs/architecture/alarms-reminders.md` (time-based, ping Discord when due)
- **Dashboard** — `sunny-vault/docs/architecture/dashboard.md` (monitoring UI with Tailscale panel)
- **Voice conversation (`/join`)** — `sunny-vault/docs/architecture/voice-join.md` (Vosk STT, wake word, the full pipeline and its history)
- **Text-to-speech (`/speak`)** — `sunny-vault/docs/architecture/tts-piper.md`
- **LLM integration** — `sunny-vault/docs/architecture/llm-integration.md` (what's judgment-only vs. real API data, and why)

---

## Estimated Costs

**Today**: well under $1/month in practice — Piper (TTS) and Vosk (STT) are fully local and free, and Claude (Haiku) is only called for genuinely open-ended questions nothing else can answer, which is light, occasional personal-assistant traffic. Live numbers: `GET /api/dashboard/spend/today` / `/spend/month`, or ask "health check" for the weekly summary. Hard spend caps enforced both in-app (`daily_spend_cap`/`monthly_spend_cap` in `.env`) and at the Anthropic account level.

Tasks, weather, and calendar/email (once each is connected — see "setup") are real API data, never LLM-guessed. Commute/health/news/motorsports still say "not connected" honestly instead of faking an answer (see `sunny-vault/log/requests.md` for what's actually being asked for).

~USD 5-8/month additional once Phases 3-5 (phone) are live:

- Twilio (phone calls): <$1
- Traffic APIs: $3-4
- Sonic API (hosted TTS, only if used instead of the free local Piper fallback): $0.12+

---

## Security

- Caller ID allowlist + PIN for phone authentication
- API keys in `.env` only — gitignored, `chmod 600`, never hardcoded or committed
- Confirmation required for irreversible actions
- Tailscale network (no open ports)
- Hard spending caps at provider level

---

## Getting Started

### Linux/macOS Quick Start
```bash
chmod +x run.sh
./run.sh # Starts the console at http://127.0.0.1:5000
```

`run.sh` creates and manages its own Python virtual environment automatically — there's nothing to set up by hand.

### Full Setup
See [SETUP_LINUX.md](SETUP_LINUX.md) for complete installation guide.

### Lenovo Brain Deployment
1. Install Ubuntu Server 26.04 LTS on Lenovo mini PC
2. Clone this repo
3. `chmod +x run.sh && ./run.sh` to start
4. Create systemd service for auto-start (see SETUP_LINUX.md)
5. Access via Tailscale from anywhere

See `sunny-vault/docs/phases.md` for full build timeline.

---

## Repository

- **GitHub**: https://github.com/T3R4Bit/Project-SUNNY (Private)
- **Vault**: `sunny-vault/` — Local Obsidian storage (inbox, staging, archive, logs, docs)
- **Source**: Python async with FastAPI, SQLite, systemd integration

---

## License

Internal project.
