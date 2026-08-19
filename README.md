# Project SUNNY

## A Self-Hosted Voice Assistant

Sunny is an always-on personal voice assistant that lives on a bedside clock and Lenovo mini PC. It wakes you with personalized briefings, answers phone calls, and automates routine tasks—all while respecting privacy and minimizing API costs through deterministic logic.

---

## Core Features

**Bedside Clock** — Battery-backed ESP32 device with wake word detection, voice I/O, and an alarm that survives power cuts.

**Morning & Evening Briefings** — Personalized summaries pulled from calendar, weather, tasks, and email. No LLM calls for facts—just API data in a fixed template.

**Phone Interface** — Callable via Twilio. Execute voice commands, create tasks, and have real-time conversations while you hold the line.

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
Clock (ESP32-S3)        Brain (Lenovo Mini PC)      External APIs
   |                          |                            |
   +-- Wake word ------+      |      +-- Calendar API -----+
   |                   |      |      |
   +-- Microphone ---> |      |  +-- Weather API
   |                   | ---> |  |
   +-- Speaker <------ |      |  +-- Email API
   |                   |      |  |
   +-- Battery Monitor |      +-- Traffic API
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

**Phase 0** — Foundations (✓ Complete)
- ✓ Ubuntu Server 26.04 LTS on Lenovo mini PC
- ✓ Briefing system with Q&A engine (mock data)
- ✓ Task management system
- ✓ Web chatbot UI over Tailscale (served at site root)
- ✓ Live system console (`/console`) — CPU, RAM, disk, network, temp
- ✓ Comprehensive documentation

**Next** — Phase 1: Tailscale networking verified, Phase 2: Clock hardware & voice I/O

See `sunny-vault/docs/phases.md` for full build timeline.

---

## Documentation

- **Architecture** — `sunny-vault/docs/architecture/` (7 component docs with cross-references)
- **Build Timeline** — `sunny-vault/docs/phases.md` (phases 0-7 with checklists)
- **Task System** — `sunny-vault/docs/TASK_SYSTEM.md` (Discord task dashboard design)
- **Dashboard** — `sunny-vault/docs/architecture/dashboard.md` (monitoring UI with Tailscale panel)

---

## Estimated Costs

~USD 5-8/month
- Claude API (Haiku): $1.50
- Sonic API (TTS): $0.12+
- Twilio (phone calls): <$1
- Traffic APIs: $3-4
- Others: Free tier or self-hosted

Hard spending caps enforced at provider accounts.

---

## Security

- Caller ID allowlist + PIN for phone authentication
- API keys rotated regularly, never hardcoded
- Confirmation required for irreversible actions
- Tailscale network (no open ports)
- Hard spending caps at provider level

---

## Getting Started

### Linux/macOS Quick Start
```bash
chmod +x run.sh
./run.sh                    # Starts chatbot at http://127.0.0.1:5000
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
