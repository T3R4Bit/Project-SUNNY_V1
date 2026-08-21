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

- **Discord Voice** — `/speak`, `/join`, `/leave`. Live, wake-word-gated spoken conversation over Discord, fully local STT/TTS (Vosk + Piper), routed through the same brain as text chat. Built and live ahead of the bedside-clock hardware below.
- **Bedside Clock + Alarm** — Battery-backed hardware with wake word detection (not yet built — Discord voice already delivers the conversational half of this today)
- **Morning Briefing** — Calendar, weather, tasks; genuinely open-ended questions get a real Claude answer instead of a canned "not connected"
- **Phone Integration** — Answer calls via Twilio and execute voice commands (not yet built)
- **Remote Power Control** — Wake desktop and control devices via Tailscale network
- **Smart Logging** — Discord activity channels, Notion sync, Obsidian vault mirroring

## Architecture

### Hardware
- **Brain**: Lenovo mini PC (always-on, Ubuntu Server 26.04 LTS, headless — no GUI, CPU-only — no discrete GPU)
- **Clock**: ESP32-S3 with OLED display, LiFePO4 battery, microphone, speaker (not yet built)
- **Network**: Tailscale mesh connecting all devices securely

### Software Stack
- **Voice**: Piper TTS (`/speak`, `/join`), Vosk STT (`/join`) — both fully local, CPU-only, free. Fast enough that TTS runs at roughly 16x real-time on this hardware (verified live, 2026-08-21) — real-world benchmarks for larger/GPU-oriented alternatives (Qwen3-TTS, Kokoro) don't hold up on this specific CPU, tested directly rather than assumed.
- **Backend**: FastAPI, SQLite, Python asyncio
- **UI**: Console-style web dashboard (green-on-black terminal aesthetic)
- **Communication**: Twilio (planned), Discord bot (live — text + voice), Tailscale mesh network
- **Data**: Google Calendar + Gmail (Sign-In), OpenWeatherMap, Traffic APIs (planned)
- **Brain**: Claude API (Haiku, judgment/freeform-conversation fallback only — never for data lookups), Notion, Obsidian vault, TrueNAS

## Current Status

**Phase 0 (Foundations)** — Complete
- Briefing system with real task/weather/calendar data where connected, honest gaps elsewhere, and a Claude-backed fallback for anything genuinely open-ended
- Task/list/alarm/reminder management — natural language, no command prefix needed, driven identically from the console, Discord text, and Discord voice (see [[./TASK_SYSTEM.md]])
- Discord bot live: text commands plus `/speak`, `/join`, `/leave` voice commands
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

- Caller ID allowlist + PIN for phone authentication
- API keys rotated regularly, never hardcoded
- Confirmation required for irreversible actions
- Tailscale network keeps devices off public internet
- Hard spending caps at provider accounts

## Getting Started

Quick start: [[./QUICKSTART.md]]

Full setup guide: [[../SETUP_LINUX.md]]

---

Built with privacy and efficiency in mind.

