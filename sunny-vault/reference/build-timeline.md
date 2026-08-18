---
id: sunny-timeline
type: reference
status: active
source: notion
created: 2026-08-18
tags: [timeline, phases, planning]
---

# Build Timeline & Phases

## Phase 0 — Foundations (IN PROGRESS)

**Status**: Debian replaced with Ubuntu Server 20.04, BIOS configured

- [x] Decide on headless Linux (Debian → Ubuntu Server 20.04)
- [x] Decide on LiFePO4 battery swap and charger (TP5000)
- [x] Decide on BIOS restore-on-AC-loss requirement
- [x] Install Ubuntu Server 20.04 on Lenovo mini PC
- [x] Configure BIOS (power restore, boot order, disable PXE)
- [ ] Python env setup (venv, requirements.txt)
- [ ] Secrets via env vars + config file
- [ ] Git repo + folder structure (in progress)
- [ ] Logging from the start (structured logging module)
- [ ] Set up Obsidian vault (inbox/staging/archive/log/state/reference)
- [ ] Set up systemd unit with Restart=always
- [ ] Disable unattended-upgrades auto-reboot
- [ ] Local dashboard skeleton (FastAPI, bound to Tailscale, sunny.db)

**Deliverable**: Sunny process running with basic logging, systemd autostart, zero LLM calls yet.

---

## Phase 1 — Networking

- [ ] Join Lenovo to Tailscale
- [ ] Join TrueNAS to Tailscale
- [ ] Set up MicroLink on future ESP32 Clock
- [ ] Test: Lenovo ↔ TrueNAS ↔ Phone connectivity via Tailnet

**Deliverable**: All devices on same secure mesh, can ping each other.

---

## Phase 2 — Briefing Engine

- [ ] Template-based briefing structure (morning + evening)
- [ ] Data fetchers: calendar, weather, tasks, yesterday's incomplete, commute
- [ ] LLM-based email triage pass only (not lookups)
- [ ] Scheduled job: run at 7am + 9pm
- [ ] Output: voice to Clock + Discord log

**Deliverable**: Wake to personalized briefing with zero hallucinations.

---

## Phase 3 — Voice Out / Clock Hardware

- [ ] Sonic API integration + Piper TTS fallback
- [ ] ESP32-S3 brain, wake word detection
- [ ] OLED display (time, status, simple messages)
- [ ] LiFePO4 battery + TP5000 charger + boost converter
- [ ] Adaptive volume (measure ambient noise, scale output)
- [ ] Talk-over ducking (pause output if user talks)
- [ ] Alarm scheduling + battery-backed clock
- [ ] 3D-printed enclosure

**Deliverable**: Clock device with voice in/out, battery backup, local hardwired commands.

---

## Phase 4 — Voice In

- [ ] Wake word detection (openWakeWord/Porcupine)
  - Variants: "Hey Sunny", "Hello Sunny", "Sunny [command]"
- [ ] STT (Whisper local or hosted)
- [ ] Intent routing (hardcoded patterns for common commands)

**Deliverable**: Say "Hey Sunny, what's the weather?" → real-time voice response.

---

## Phase 5 — Telephony

- [ ] Twilio phone number + webhook (authenticated)
- [ ] Caller ID allowlist (primary auth) + PIN (backup)
- [ ] Live in-call STT → LLM → action while you hold the line
- [ ] Example: "Call Sunny, tell it to start the coffee maker"

**Deliverable**: Answer phone calls, execute voice commands, stay on line during execution.

---

## Phase 6 — Remote Power Control (Deprioritized)

- [ ] Wake-on-LAN or smart plug for desktop PC
- [ ] Wrapped in `power_on_desktop()` function
- [ ] Triggered by voice command or scheduled action

---

## Phase 7 — Custom Hardware Finalization

- [ ] Move from off-the-shelf breakout boards to custom PCB
- [ ] Refinement once design is proven

---

## Ongoing / Cross-Cutting

Work alongside phases above, not separate:

- [ ] Discord activity log server
  - Channels by action type (calendar, email, reminders, state, warnings, direct chat, Notion sync)
  - Permanent searchable audit trail
- [ ] Priority scheduler across input surfaces
- [ ] Token usage circuit breaker
  - Track real-time usage during tasks
  - Pause if crossing threshold, ask to continue or halt
- [ ] Spending caps at provider level (hard limits on Anthropic, Twilio accounts)
- [ ] TrueNAS media update logging to Discord
- [ ] Storage warning in briefing if space low
- [ ] Tagged FileZilla pull pipeline
  - External server → Lenovo → TrueNAS
  - Auto-pull files tagged with specific prefixes
- [ ] Proactive call engine (sleep-aware)
  - Ring if package fails, professor emails, etc.
  - Sleep mode: "good night" suppresses calls until "good morning"
- [ ] Location-aware departure nudges
  - Track rough location (Tailscale or location API)
  - Compare against calendar + live travel time
  - Nudge on Discord when to leave
- [ ] Nightly wind-down briefing
  - Evening counterpart to morning
  - Recap today, preview tomorrow
- [ ] Auto-draft email replies
  - Draft (not send) replies to routine emails
  - Ready for review before sending
- [ ] Auto-reschedule overdue tasks
  - If task clearly not getting done today, move to tomorrow
  - Instead of silent overdue
- [ ] Scan financial emails for upcoming bills
  - Proactively create reminder before due date
- [ ] Proactive calendar updates
  - Detect schedule changes (professor cancels, time shift)
  - Auto-update calendar event instead of just mentioning

---

## Estimated Completion

- **Phase 0**: This week (foundational setup)
- **Phase 1**: Week 2 (networking)
- **Phase 2**: Week 3-4 (briefing, first real feature)
- **Phase 3**: Week 5-6 (hardware, voice out)
- **Phase 4-5**: Week 7-9 (voice in, phone)
- **Phases 6-7 + cross-cutting**: Ongoing refinement

**MVP target**: End of September 2026 (Phases 0-5 complete, Clock device working, phone callable)
