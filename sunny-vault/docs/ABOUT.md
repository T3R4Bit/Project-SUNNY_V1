---
id: sunny-about
type: guide
status: active
created: 2026-08-18
tags: [project, vision, overview]
---

# About Project SUNNY

```
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                                                                                    
                                       # #
                                       ## ### #
                                      ## # ## # ###
                                     ## # ### ## ## ##
                                     # # ### ## ### ##
                         ##### ## #### #### #
                           ## ## # ## ####### ## ######
                            ## ## ## ####### ############### ##
                             # ###### #### ##
                             ## ## ## ##
                              ##### ## ##
                               ## ####
              ### ########## ## ####### ###
                   ## ########################################### ###
                     ## ######## # ################# # ######## ###
                      ### ### #### # ######### ###### ####### ######
                        ###### ## # ######### #### # ######## ####
              ## ###### ## #### ######### ### # ######## ## ###
                ### ## ########### ########### ## #######
                   ###### ## # ###
                          # ## ## ## ## #######
                           ##### ###### ### #
                          ## ## ## ##
                       #### ### ### #
                     ### #### ### ##
                            ##### ###### ##### #
                                 ## ##### ##### ## ###### #
                                ## ############## #
                               ## ####### ## # ### #
                               #### ## ## #### #
                               ## ## ## ###
                                               ## #
                                                ##
                                                 #
                                                                                                    
```

## Vision

Project SUNNY is a self-hosted voice assistant for personal productivity and automation. It prioritizes privacy, efficiency, and smart defaults over LLM overhead.

## Key Principles

- **Templates first, tokens last** — Fixed briefings with API-filled slots, no LLM overhead
- **LLM only for judgment** — Email triage, task interpretation, freeform conversation
- **No LLM for lookups** — Direct API calls for calendar, weather, traffic, financial data
- **Fail quietly** — System degrades gracefully if individual services are down

## Core Features

- **Discord Voice** — `/speak` for one-shot TTS; persistent live conversation (wake-word-gated, no join command — Sunny just stays in a configured voice channel) fully local STT/TTS (Vosk + Piper), routed through the same brain as text chat, with session-scoped conversation memory. Built and live ahead of the bedside-clock hardware below.
- **Bedside Clock + Alarm** — Battery-backed hardware with wake word detection (not yet built — Discord voice already delivers the conversational half of this today)
- **Morning Briefing** — Calendar, weather, tasks; genuinely open-ended questions get a real Claude answer, with real web search when the question needs current info (see [[architecture/llm-integration]])
- **Google Calendar + Gmail** — read via Sign-In; Calendar also supports natural-language create/delete ("add dentist appointment to my calendar at 3pm tomorrow") — see [[architecture/google-integration]]
- **Spotify Voice Control** — "play `<song>`", "pause", "skip", "volume up", "what's playing" — from any interface — see [[architecture/spotify-integration]]
- **Phone Integration** — Answer calls via Twilio and execute voice commands (not yet built)
- **Remote Power Control** — Wake desktop and control devices via Tailscale network (not yet built — deprioritized, see [[./phases.md]] Phase 6)
- **Smart Logging** — Discord activity channels (live — task updates, warnings, chat, briefings, health/usage) and Obsidian vault mirroring (live — see [[architecture/vault-storage]]). Notion sync is not built — no Notion integration exists yet

## Architecture

### Hardware
- **Brain**: Lenovo mini PC (always-on, Ubuntu Server 26.04 LTS, headless — no GUI, CPU-only — no discrete GPU)
- **Clock**: ESP32-S3 with OLED display, LiFePO4 battery, microphone, speaker (not yet built)
- **Network**: Tailscale mesh connecting all devices securely

### Software Stack
- **Voice**: Piper TTS (`/speak`, persistent voice conversation), Vosk STT (persistent voice conversation) — both fully local, CPU-only, free. Fast enough that TTS runs at roughly 16x real-time on this hardware (verified live, 2026-08-21) — real-world benchmarks for larger/GPU-oriented alternatives (Qwen3-TTS, Kokoro) don't hold up on this specific CPU, tested directly rather than assumed.
- **Backend**: FastAPI, Python asyncio. Storage is split: tasks/lists live as vault-markdown (one file per item, directly readable/editable in Obsidian — see [[architecture/vault-storage]]); alarms/reminders and usage/spend metrics still use SQLite (`sunny.db`) since they need reliable automatic background writes, not a hand-browsable file
- **UI**: Console-style web dashboard
- **Communication**: Twilio (planned), Discord bot (live — text + voice), Tailscale mesh network
- **Data**: Google Calendar + Gmail (Sign-In), OpenWeatherMap, Traffic APIs (planned)
- **Brain**: Claude API (Haiku by default — judgment, freeform conversation, storm-mode weather updates, health-check reports, project scaffolding; never for data lookups), Obsidian vault. Notion sync and TrueNAS integration are planned, not built.

## Current Status

**Phase 0 (Foundations)** — Mostly complete (a couple of small OS-config items open — see [[./phases.md]])
- Briefing system with real task/weather/calendar data where connected, honest gaps elsewhere, and a Claude-backed fallback for anything genuinely open-ended
- Task/list/alarm/reminder management — natural language, no command prefix needed, driven identically from the console, Discord text, and Discord voice (see [[./TASK_SYSTEM.md]])
- Discord bot live: text commands, `/speak` one-shot TTS, and persistent live voice conversation (no join command — `/service voice_join` toggles it)
- One combined console at `/console` (`/` and the old `/chatbot` redirect there) — chat, live system stats, and Google sign-in status, accessible over Tailscale

**Phase 1-7** — In planning (hardware phases; voice I/O itself is already live via Discord)

See [[./phases.md]] for detailed build timeline.

## Estimated Costs

**Today**: well under $1/month in practice — Piper and Vosk are fully local and free; Claude (Haiku) is only called for genuinely open-ended questions, which is light personal-assistant traffic. Live numbers: `GET /api/dashboard/spend/today` / `/spend/month`, or ask "health check" for the weekly summary.

Monthly spend once phone (Phase 3-5) is live, on top of the above: ~$4-5
- Twilio voice calls (~$0.01–$0.15/min)
- Traffic/location APIs (~$3–$4)
- Sonic API (hosted TTS — only if used instead of the free local Piper fallback)

Hard spending caps enforced both in-app (`daily_spend_cap`/`monthly_spend_cap` in `.env`) and at the provider account level.

## Security

- Caller ID allowlist + PIN for phone authentication (planned, once phone integration exists)
- API keys rotated regularly, never hardcoded
- No confirmation step today for destructive actions (delete a task, cancel a calendar event, delete a Discord channel/role) — they run immediately, matching this being a single-user personal tool
- Tailscale network keeps devices off public internet
- Hard spending caps at provider accounts

## Getting Started

Quick start: [[./QUICKSTART.md]]

Full setup guide: [[../SETUP_LINUX.md]]

---

Built with privacy and efficiency in mind.

