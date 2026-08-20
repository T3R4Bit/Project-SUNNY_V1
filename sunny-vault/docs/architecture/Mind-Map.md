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
- [[briefing-engine]] — Morning/evening briefings from calendar, weather, tasks
- [[email-processing]] — Email triage and filtering
- [[calendar-integration]] — Calendar sync and event tracking
- [[../TASK_SYSTEM.md|task-system]] — Task management; Discord bot dashboard is the planned primary interface (not yet built), web chatbot is the working fallback today

### Intelligence & Control
- [[llm-integration]] — Claude API for reasoning and judgment
- [[priority-queue]] — Concurrent request handling, foreground priority
- [[token-circuit-breaker]] — Real-time token tracking and spending limits

### Logging & Storage
- [[obsidian-vault]] — Local markdown staging and logging
- [[discord-bot]] — Activity log, chat interface, notifications
- [[notion-sync]] — Cloud storage for finalized items
- [[dashboard]] — Local web UI for monitoring and control

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

**Monthly spend**: ~$5-8
- Claude API: $1.50-8 (depending on model)
- Twilio: <$1/month typical
- Sonic API: $0.12+
- Traffic APIs: $3-4
- Others: Free tier or self-hosted

**Hard spending caps** at provider level (Anthropic, Twilio).

**Storage**:
- Obsidian vault: Local, unlimited
- Notion: Free tier
- SQLite (sunny.db): Metrics, ~1KB/day

## External Services

| Service | Type | Cost | Fallback |
|---------|------|------|----------|
| Claude API | LLM | $1.50-8/mo | Haiku for cheaper option |
| Sonic API | TTS | $0.12+ | Piper TTS (local, free) |
| Twilio | Phone | <$1/mo | N/A (required for phone) |
| Whisper | STT | Free or $0.02/min | Local Vosk (lower quality) |
| Tailscale | VPN | Free personal | WireGuard (manual setup) |
| Calendar API | Calendar | Free | Local file sync |
| Weather API | Weather | Free tier | Hardcoded fallback forecast |
| Traffic API | Maps | $3-4/mo | Hardcoded travel times |

## Next Steps

1. **Phase 0**: Set up Sunny as a systemd unit (currently runs via `./run.sh`, not yet auto-starting on boot)
2. **Phase 1**: Verify phone dashboard access over Tailscale specifically, optional ACLs
3. **Phase 2**: Replace mock data sources (calendar, weather, traffic, email) with real APIs
4. **Phase 3+**: ESP32 Clock hardware assembly, voice I/O, phone integration, Discord bot

See individual component docs and [[../phases.md]] for implementation details.
