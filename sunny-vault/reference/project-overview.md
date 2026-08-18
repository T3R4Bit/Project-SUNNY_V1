---
id: sunny-overview
type: reference
status: active
source: notion
created: 2026-08-18
tags: [project, architecture, overview]
---

# Project SUNNY — Personal Voice Assistant

## Smart Unified Network Navigating Yond

A self-hosted voice assistant that lives on a bedside device (the Clock), wakes you up, briefs you, answers the phone, and can power on your desktop remotely. Deterministic where possible, LLM only where judgment is genuinely needed.

## What This Is

Sunny is an always-on program on a Lenovo mini PC, listening concurrently across all input surfaces rather than one at a time. Wake word audio from the Clock (over Tailscale), incoming Twilio webhooks for phone calls, Discord bot messages, and scheduled jobs like the morning and nightly briefings running on timers. Each input source runs as its own background process or async task, all feeding into a shared priority system that decides what gets LLM attention first based on which surface you are actively using.

## Design Principles

- **Templates first, tokens last** — The briefing is a fixed script with slots filled from APIs. No LLM call needed for facts.
- **LLM only for judgement** — Email triage, task interpretation, freeform phone conversation.
- **No LLM for information lookups** — Any time Sunny is checking or fetching information (calendar, weather, traffic, location, financial emails, API status, etc.), it must use direct API calls or deterministic logic, never routing through the LLM.
- **Sonic API for fluent voice** — Local Piper TTS as a fallback if the API is down.
- **Fail quietly** — If the weather API is down, the alarm still goes off.

## The Four Core Capabilities

1. **Bedside clock + alarm** with battery backup so a power cut doesn't mean a missed alarm
2. **Morning briefing** — calendar, weather, overdue tasks, email that matters, commute, yesterday's unfinished items
3. **Callable by phone** — ring a number, tell it to start working on tasks before you get home
4. **Remote power control** for the main computer

## Core Services

**Voice pipeline**: Sonic API, Piper TTS, Whisper STT, wake word (openWakeWord or Porcupine)
**Data lookups**: Calendar, Weather, Email, Traffic
**Comms and network**: Twilio, Discord bot, Tailscale, MicroLink
**Brain and storage**: Claude API, Notion, Obsidian, TrueNAS

Of the sixteen services, only Claude, Sonic, and Twilio cost money per use. The rest are free tiers or self-hosted.

## Estimated Costs

- Claude Haiku: ~$1.50/month
- Claude Sonnet: ~$3/month
- Twilio voice: ~$0.01-0.15/min
- Sonic API: variable
- Traffic/location APIs: ~$3-4/month

**Total: ~$5–$8/month with hard spending caps at provider level**

## Security & Cost Safety

- Hard spending caps set directly on provider accounts (Anthropic, Twilio), not just in code
- Twilio webhook properly authenticated
- API keys rotated periodically, never hardcoded
- Phone authentication: caller ID allowlist + PIN
- Confirmation required before irreversible actions
- Tailscale network keeps Clock and mini PC off the open internet
