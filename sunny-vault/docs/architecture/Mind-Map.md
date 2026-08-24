---
id: sunny-arch-index
type: reference
status: active
created: 2026-08-18
tags: [architecture, overview, system-design]
---

# System Architecture

Overview of Project SUNNY's major components and how they interact.

## Core Components

### Compute & Hardware
- [[brain]] — Lenovo mini PC, always-on, runs Sunny core
- [[clock]] — ESP32-S3 bedside device, wake word detection, voice output
- [[networking]] — Tailscale mesh connecting all devices

### Audio & Voice
- [[voice-io]] — Speech-to-text, text-to-speech pipeline
- [[wake-word]] — Local wake word detection
- [[phone]] — Twilio integration for phone calls

### Features
- [[briefing-engine]] — Morning/evening briefings from calendar, weather, tasks; freeform Q&A with real web search when needed
- [[../TASK_SYSTEM.md|task-system]] — Task management, real editable categories, archive-not-delete. Discord bot is the live primary interface; console chat is the fallback
- [[lists]] — Named checkable lists (groceries, packing, etc.) — sibling to tasks, not part of them
- [[alarms-reminders]] — Time-triggered alarms/reminders, ping Discord when due
- [[project-system]] — "New project" wizard, drafts a real multi-file folder from one LLM call
- [[google-integration]] — Google Sign-In: Calendar (read + create/delete), Gmail (read-only headers)
- [[spotify-integration]] — Voice-controlled Spotify playback
- [[voice-join]] — Live, real-time Discord voice conversation (`/join`), streaming replies, barge-in
- [[tts-piper]] — Local TTS, `/speak` one-shot attachments
- [[health-check]] — Weekly (and on-demand) system health report
- [[usage-tracking]] — Claude spend tracking, spend caps, persistent Discord usage dashboard
- [[location]] — Phone GPS via OwnTracks, staleness-windowed

### Intelligence & Control
- [[llm-integration]] — Claude API for reasoning, judgment, and real web search
- [[llm-instructions]] — Hand-editable per-purpose system prompts in the vault
- Priority queue — not a real scheduler; `llm_client.py`'s `asyncio.Semaphore(1)` is a lightweight stand-in, sufficient for a single-user assistant with no concurrent-call scenario yet (see [[llm-integration]])

### Logging & Storage
- [[vault-storage]] — Tasks/lists as one markdown file per item, directly readable/editable in Obsidian
- [[discord-bot]] — Live text + voice interface, task dashboard, health/usage channel, warnings
- [[dashboard]] — Local web UI for monitoring and control

Not built: email triage/filtering, dedicated calendar-sync component beyond Google Sign-In's read/write, Notion sync, a dedicated "token circuit breaker" doc (folded into [[llm-integration]] and [[usage-tracking]] instead).

## Component Dependency Graph

```
Input Surfaces (Clock, Phone, Discord)
    ↓
Priority Queue
    ├→ Token Circuit Breaker
    ├→ Intent Router
    │   ├→ Direct APIs (no LLM)
    │   │   ├→ Calendar API
    │   │   ├→ Weather API
    │   │   ├→ Traffic API
    │   │   └→ Email API
    │   │
    │   └→ Claude API (judgment only)
    │       ├→ Email Triage
    │       ├→ Task Interpretation
    │       └→ Freeform Conversation
    │
    ├→ Action Executor
    │   ├→ Voice Output (Sonic/Piper TTS)
    │   ├→ Discord Messaging
    │   └→ Calendar Update
    │
    └→ Obsidian Staging
        ↓
    Notion Sync (finalized items only)

Scheduled Jobs
    ├→ Morning Briefing (7am)
    ├→ Evening Briefing (9pm)
    └→ Background Checks (battery, API health)
        ↓
    Dashboard Update
```

## Design Principles

See [[design-principles]] for core philosophy:
- **Templates first, tokens last** — No LLM for facts
- **LLM only for judgment** — Never for lookups
- **Fail quietly** — Partial degradation over total failure
- **Deterministic** — Hardcoded rules over heuristics

## Current Phase

See [[../phases.md]] for the authoritative, detailed phase breakdown and checklists — this section is just a summary and can drift, so treat phases.md as the source of truth.

**Phase 0 (Foundations)**: Mostly complete — Ubuntu Server 26.04 LTS (headless) installed and running under a systemd unit (autostart, `Restart=always`), briefing engine + task system + chatbot UI + system console + Discord bot (connected and live) all built.

**Phase 1 (Networking)**: Mostly complete — Lenovo, TrueNAS, phone, and workstation all joined to the Tailscale mesh, now also serving HTTPS (Tailscale-issued cert) alongside plain HTTP. Phone-specific verification and ACLs still outstanding.

**Phase 2 (Briefing Engine)**: Templates and Q&A engine fully built. Tasks and weather are live; Calendar/Gmail are wired via Google Sign-In (client configured, sign-in not yet confirmed working end-to-end); traffic/commute not started.

**Phase 3+ (Clock hardware, voice I/O, phone, Discord bot)**: Not yet started.

## Cost & Resources

**Today**: well under $1/month in practice — Piper/Vosk are free and local, Claude (Haiku) only runs for genuinely open-ended questions. Live numbers: `GET /api/dashboard/spend/today`/`/spend/month`, or see [[usage-tracking]].

**Once phone/traffic phases are live**, on top of the above: ~$4-5/mo (Twilio, traffic/routing API, optionally Sonic TTS instead of the free Piper fallback).

**Hard spending caps** enforced in-app (`token_tracker.check_budget()`) and, separately, at the provider account level (a manual step, see [[llm-integration]]).

**Storage**:
- Obsidian vault: tasks/lists as markdown, unlimited, local — see [[vault-storage]]
- `sunny.db` (SQLite): alarms/reminders, token-usage metrics — small, local

## External Services

| Service | Type | Cost | Status |
|---------|------|------|--------|
| Claude API | LLM | Well under $1/mo in practice (Haiku default) | Live |
| Piper + Vosk | TTS + STT | Free, local, CPU-only | Live (`/speak`, `/join`) |
| Discord | Bot platform | Free | Live |
| Tailscale | VPN | Free personal | Live |
| Google Calendar + Gmail | Calendar/email | Free | Live via Sign-In (read + Calendar write) |
| Spotify | Music control | Free (Premium required for playback control) | Live |
| OpenWeatherMap | Weather | Free tier | Code-complete, needs API key + location |
| Sonic API | TTS | $0.12+/mo | Not built — Piper is the live local fallback, already ahead of it |
| Twilio | Phone | <$1/mo | Not built |
| Traffic/routing API | Maps | $3-4/mo | Not built |
| Notion | Sync | Free tier | Not built |

## Next Steps

1. **Phase 0**: Disable unattended-upgrades auto-reboot / pin to a window; skip Featured Server Snaps at install
2. **Phase 1**: Verify phone dashboard access over Tailscale specifically, optional ACLs
3. **Phase 2**: Confirm Google Sign-In end-to-end; traffic/commute still needs an API key
4. **Backlog**: Service orchestration (per-service toggle, autostart config, vacation mode), then the foundational proactive-assistant architecture in [[personal-assistant-vision]] — see [[../BACKLOG.md]]
5. **Phase 3+**: ESP32 Clock hardware assembly, voice I/O beyond Discord, phone integration (`sunny-companion/BUILD_PLAN.md` tracks the Pi companion device build separately)

See individual component docs and [[../phases.md]] for implementation details.
