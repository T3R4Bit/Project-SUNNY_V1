# Project SUNNY

## A Self-Hosted Personal Assistant

Sunny is an always-on personal assistant that runs on a Lenovo mini PC, reachable over Tailscale from a Discord bot, a web console, live voice conversation, or terminal chat — all routed through the same shared logic, so behavior is identical everywhere. Real tasks/lists/calendar data, deterministic templates for facts, Claude only for judgment and genuinely open-ended questions.

A dedicated hardware companion device (Raspberry Pi, animated face, local wake word) is in active prototyping — see `sunny-companion/BUILD_PLAN.md`. Everything below already runs today without it.

---

## Core Features

**Tasks & Lists** — Natural language, no command prefix. Real, editable categories (not hardcoded); deleting or finishing a task archives it, nothing is ever actually lost. Named checkable lists (groceries, packing, anything) as a sibling system. Both stored as one markdown file per item directly in the Obsidian vault — readable/editable outside Sunny too.

**Alarms & Reminders** — Time-based, natural phrasing ("set an alarm for 7am", "remind me to call mom at 5pm"), ping Discord when due.

**Discord Bot** — The primary live interface: task dashboard (live-updating embed), health/usage dashboard, server administration (create/delete channels & roles), plus real slash commands (`/speak`, `/classsetup`, `/category`, `/service`/`/services`, `/vacation`, `/usage`, `/version`).

**Persistent Live Voice** — Sunny stays connected to a configured voice channel and has a real spoken conversation ("Hey Sunny" still wakes it for each request — no open-mic listening) — free, fully local STT/TTS (Vosk + Piper), streaming replies (starts speaking the first sentence while Claude is still writing), barge-in support, session-scoped conversation memory for genuine follow-ups. Toggle on/off with `/service voice_join`, no per-use join command. Runs in an isolated process so a native audio-library crash can't take down the rest of the bot — reconnects automatically after one.

**Google Calendar & Gmail** — Calendar is read *and* write (create/delete events by natural language: "add dentist appointment to my calendar at 3pm tomorrow"); Gmail is read-only (unread/important counts, subject lines, never bodies). One Google Sign-In connects both.

**Spotify Voice Control** — Play/pause/skip/volume/what's-playing from any interface, acts on whatever device Spotify itself considers active (same as the Spotify app or Siri).

**Weather & Storm Mode** — Real API data normally; "storm mode" switches to a real web-searched LLM update on a set interval/duration instead, for actively-developing weather.

**Project Wizard** — Say "new project," answer three quick questions, get a real multi-file project folder drafted under `sunny-vault/projects/` via one Claude call.

**Class Setup** — Paste a syllabus per class through a short wizard ("set up my classes" or `/classsetup`); Sunny extracts the class name, meeting times, due dates, and exams (semester start/end dates too — only a semester label like "Fall 2026" is asked for, never a date range), creates a real recurring Google Calendar event for meetings plus all-day events for deadlines, saves the syllabus and a generated summary into that class's own vault folder, and proactively pings a Discord channel 2 days before and the day of each deadline.

**Exam Prep & Spaced Review** — Reads real class notes (`sunny-vault/KSU/<semester>/<class>/*.md`), finds exam dates from Calendar (including ones created by Class Setup above), tracks per-topic review state (new/weak/mastered), and writes a focused night-before study review from actual note content.

**Weekly Health Check** (Sunday 4am, or on demand) — Compacts logs/errors/unfulfilled-request patterns/API-key expiry into an LLM-written report, now including a knowledge health check (broken wikilinks, orphaned/untagged/stale notes across the vault).

**Usage Tracking** — Self-tracked spend chart *and* Anthropic's own real-time rate-limit data (straight from API response headers), persistent Discord dashboard, daily/monthly spend-cap alerts.

**Service Orchestration** — Per-service enable/disable and autostart-on-boot toggles (`/service`, `/services`) without restarting the whole process; "vacation mode" suppresses proactive morning/evening nudging without breaking direct "good morning"/"good night" requests.

**Proactive-Architecture Foundation** — A hybrid sensors → rules-engine → context-engine → permission-check pipeline (calendar/vault-file-change detection, a compact context aggregator, confidence-gated vault-write permissions, suggestion-outcome tracking) — real, tested infrastructure with no live feature acting on it yet. First working slice of a longer-term proactive-assistant direction; see `sunny-vault/docs/architecture/personal-assistant-vision.md`.

**Location** — Phone GPS via OwnTracks (free, self-hosted, no third-party cloud), staleness-windowed rather than polled constantly.

**Web Search in Chat** — Claude can search the web from open-ended conversation when a question genuinely needs current information — it decides for itself, not on by default.

**Open-Ended Q&A** — Anything that doesn't match a real command/data topic gets a real Claude answer instead of a canned "I don't know," with an honest "not connected" instead of a faked answer for anything genuinely missing (weather/calendar/etc. before they're set up). Questions about Sunny itself ("how does class setup work") are grounded in Sunny's own current architecture docs via a keyword search, not answered from a guess.

---

## Design Philosophy

**Templates First, Tokens Last**
Real API/vault data in fixed templates wherever a fact is a fact. No LLM overhead for lookups.

**LLM Only for Judgment**
Claude handles freeform conversation, study-review writing, and anything else that genuinely needs reasoning — never for retrieving a fact something else already has.

**Fail Quietly**
An unconnected or failing integration says so honestly instead of faking data. The system degrades section-by-section, never crashes as a whole.

**Local-First, Secure**
Tailscale mesh keeps every device off the public internet — no port forwarding, no exposed APIs, reachable from anywhere via DERP relays. Secrets live in a gitignored, `chmod 600` `.env`, never hardcoded or committed.

---

## Current Status

Foundations, networking, and the briefing engine (Phase 0-2) are essentially complete, well beyond their original scope — see the Core Features list above for what actually shipped on top of the original plan. The Sunny Companion hardware device (Phase 3+ equivalent: wake word, animated face, dedicated speaker/mic) is in active standalone prototyping, tracked separately in `sunny-companion/BUILD_PLAN.md` since it has its own phase structure.

See `sunny-vault/docs/phases.md` for the full build timeline and `sunny-vault/docs/CHANGELOG.md` for a dated history of what shipped when.

---

## By the Numbers

- **~14,300 lines of Python** across 70 components (`sunny_code/components/`)
- **200+ commits** since the project started (2026-08-17) — roughly a week of active development
- **8 Discord slash commands** (`/speak`, `/classsetup`, `/category`, `/service`, `/services`, `/vacation`, `/usage`, `/version`) on top of natural-language everywhere else
- **27 architecture docs**, one per major component, cross-referenced (`sunny-vault/docs/architecture/`)
- **Under $1/month** in practice — see Estimated Costs below

Ask "what version are you running" (any interface) or `/version` in Discord for the exact commit currently deployed.

---

## Documentation

- **System overview** — `sunny-vault/docs/architecture/Mind-Map.md` (every component, one page)
- **Architecture** — `sunny-vault/docs/architecture/` (one doc per component, cross-referenced)
- **Build Timeline** — `sunny-vault/docs/phases.md`
- **Changelog** — `sunny-vault/docs/CHANGELOG.md` (dated history of real changes)
- **Backlog** — `sunny-vault/docs/BACKLOG.md` (what's next, and why some items are blocked on external accounts/API keys)
- **Task System** — `sunny-vault/docs/TASK_SYSTEM.md`
- **Sunny Companion hardware** — `sunny-companion/BUILD_PLAN.md`

---

## Estimated Costs

**Today**: well under $1/month in practice — Piper (TTS) and Vosk (STT) are fully local and free, and Claude is only called for genuinely open-ended questions, study reviews, and the weekly health check — light, occasional traffic, mostly on the cheaper Haiku tier. Live numbers: `GET /api/dashboard/spend/today` / `/spend/month`, `/usage` in Discord, or ask "health check." Spend caps enforced both in-app (`daily_spend_cap`/`monthly_spend_cap` in `.env`) and at the Anthropic account level.

Tasks, lists, weather, and calendar/email (once each is connected) are real data, never LLM-guessed. Commute/health/news/motorsports still say "not connected" honestly instead of faking an answer.

---

## Security

- API keys and tokens in `.env`/`*_token.json` only — gitignored, `chmod 600`, never hardcoded or committed
- Google/Spotify OAuth scopes kept as narrow as each real feature needs (e.g. Gmail stays read-only even though Calendar writes)
- Tailscale network (no open ports); HTTPS via a Tailscale-issued cert for endpoints that need it (OAuth callbacks)
- Destructive actions (delete a task, cancel a calendar event, delete a channel/role) run immediately with no confirmation step, matching this being a single-user personal tool — worth knowing if you're evaluating it for anything less trusted

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

### Production Deployment
1. Install Ubuntu Server 26.04 LTS on the target machine
2. Clone this repo
3. `chmod +x run.sh && ./run.sh server` to start everything together
4. Set up the systemd unit for auto-start on boot (see `SETUP_LINUX.md`)
5. Access via Tailscale from anywhere

Say "setup" (or "setup weather"/"setup calendar"/etc.) to any interface once running — it walks through exactly what's connected and what still needs an API key.

---

## Repository

- **GitHub**: https://github.com/T3R4Bit/Project-SUNNY (Private)
- **Vault**: `sunny-vault/` — Local Obsidian storage (docs, instructions, state, logs); real class notes and a few other personal-content folders are gitignored
- **Source**: Python async (FastAPI), Discord.py, googleapiclient, Piper/Vosk for local voice, Claude API for reasoning

---

## License

Internal project.
