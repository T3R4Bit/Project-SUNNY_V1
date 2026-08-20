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

- **Bedside Clock + Alarm** — Battery-backed hardware with wake word detection
- **Morning Briefing** — Calendar, weather, tasks, commute info, email triage
- **Phone Integration** — Answer calls via Twilio and execute voice commands
- **Remote Power Control** — Wake desktop and control devices via Tailscale network
- **Smart Logging** — Discord activity channels, Notion sync, Obsidian vault mirroring

## Architecture

### Hardware
- **Brain**: Lenovo mini PC (always-on, Ubuntu Server 26.04 LTS, headless — no GUI)
- **Clock**: ESP32-S3 with OLED display, LiFePO4 battery, microphone, speaker
- **Network**: Tailscale mesh connecting all devices securely

### Software Stack
- **Voice**: Sonic API, Piper TTS, Whisper STT, openWakeWord
- **Backend**: FastAPI, SQLite, Python asyncio
- **UI**: Console-style web dashboard (green-on-black terminal aesthetic)
- **Communication**: Twilio, Discord bot, Tailscale mesh network
- **Data**: Calendar, Weather API, Email, Traffic APIs
- **Brain**: Claude API, Notion, Obsidian vault, TrueNAS

## Current Status

**Phase 0 (Foundations)** — Mostly complete (systemd autostart still outstanding)
- Briefing system with 9-section morning and 7-section evening templates, running on mock data
- Task management with Discord-style command parsing, driven today through the console chat/REST API (Discord bot itself not yet built — see [[./TASK_SYSTEM.md]])
- One combined console at `/console` (`/` and the old `/chatbot` redirect there) — chat, live system stats, and Google sign-in status, accessible over Tailscale

**Phase 1-7** — In planning

See [[./phases.md]] for detailed build timeline.

## Estimated Costs

Monthly spend once voice/phone phases are live: ~$5–$8
- Claude API (primary: Haiku ~$1.50, Sonnet ~$3)
- Twilio voice calls (~$0.01–$0.15/min)
- Sonic API (hosted TTS)
- Traffic/location APIs (~$3–$4)

**Today**: $0 — no LLM or paid API is called yet.

Hard spending caps enforced at the provider level.

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

