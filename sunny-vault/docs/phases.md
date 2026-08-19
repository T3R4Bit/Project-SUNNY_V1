---
id: sunny-phases
type: planning
status: active
created: 2026-08-18
tags: [phases, timeline, deliverables, planning]
---

# Build Phases & Deliverables

Complete breakdown of Project SUNNY's build timeline with dependencies, deliverables, and current status.

---

## Phase 0: Foundations (MOSTLY COMPLETE)

**Timeline**: This week  
**Current Status**: Ubuntu Server 26.04 LTS installed and running on the Lenovo (sunshine-m700). Core app — briefing engine, task system, [[architecture/lists.md|lists]], [[architecture/alarms-reminders.md|alarms/reminders]], the combined console (chat + system status, one page at `/console`), Discord bot (code complete, token not yet connected) — all built and working over Tailscale. Systemd autostart is the main remaining piece.  
**Deliverable**: Sunny process running locally, basic logging, systemd autostart

### Setup Tasks

- [x] Decide on headless Linux OS (Ubuntu Server 26.04 LTS, switched from Debian)
- [x] Decide on LiFePO4 battery swap and matching charger/cell sizing
- [x] Decide on BIOS restore-on-AC-loss requirement
- [x] Install Ubuntu Server 26.04 LTS on Lenovo mini PC (headless, no GUI)
- [x] Python env setup on the Lenovo (`run.sh` creates/manages `venv/` automatically — no manual venv step)
- [x] Git repo + folder structure
- [x] Logging from the start
- [x] Set up local dashboard skeleton — now functional, not just skeleton: FastAPI app bound to `0.0.0.0:5000`, one combined console at `/console` (chat + live system/Google status — `/` and the old `/chatbot` both redirect there), sunny.db + tasks.db via SQLite
- [x] Set up Obsidian vault structure (inbox/staging/archive/log/state)

- [x] Set BIOS to restore power state on AC loss
- [x] Secrets via env vars + config file — `.env` (gitignored, `chmod 600` on every `run.sh` start), loaded via `sunny_code/config.py`; startup logs + Discord post what's still missing (`sunny_code/components/key_status.py`)
- [ ] Set up Sunny as a systemd unit with Restart=always
- [ ] Disable unattended-upgrades auto-reboot, or pin to a window
- [ ] Skip Featured Server Snaps at install (avoid snapd entirely rather than purging later)


---

## Phase 1: Networking

### Networking Tasks

- [x] Install Tailscale on Lenovo [[brain]] (sunshine-m700, 100.117.41.53)
- [x] Generate stable private IP for Lenovo (100.117.41.53, stable)
- [x] Install Tailscale on TrueNAS server (caliop-truenas, 100.123.58.119)
- [x] Verify TrueNAS connectivity to Lenovo (61ms latency, reachable)
- [x] Install Tailscale on phone (iphone181, 100.73.98.114)
- [x] Install Tailscale on workstation (keaton-pc, 100.82.153.78)
- [x] Fixed server binding so it's reachable over Tailscale, not just localhost (`--host 0.0.0.0`)
- [x] Confirmed cross-device access — console (chat + system status) reachable from workstation over Tailscale
- [x] Document all device IPs and hostnames (updated [[networking]] and [[dashboard]])
- [ ] Test phone dashboard access via Tailscale specifically (workstation confirmed, phone not yet verified)
- [ ] Configure Tailscale ACLs (optional, all devices trust each other for now)
- [ ] Flash MicroLink firmware on future ESP32 [[clock]] (pending hardware)

### Deliverables When Complete

```
✅ Lenovo: 100.x.x.x (stable, always-on)
✅ TrueNAS: 100.x.x.x (accessible from mesh)
✅ Phone: Joins mesh, can ping devices
✅ Firewall: No open ports exposed (all behind Tailscale)
✅ Remote access: Works even away from home (DERP relays)
```

**Next Step**: Phase 2 (Briefing Engine)

---

## Phase 2: Briefing Engine (TASKS + CALENDAR + EMAIL LIVE, REST PENDING)

**Timeline**: Week 3-4  
**Dependencies**: Phase 0-1 complete  
**Deliverable**: Working morning and evening briefings

**Current status**: The engine itself is built and working — hardcoded morning and evening templates, slot-filling text generation, and a Q&A system covering weather, calendar, email, tasks, commute, health, motorsports, news, and tomorrow. Tasks are real, queried live from `tasks.db`. Calendar and email are code-complete via Google Sign-In (OAuth) — see [[architecture/google-integration]] — but need a one-time Google Cloud OAuth client + sign-in (external setup, not code) before they go live. Weather, commute, health, motorsports, and news still have no real API behind them, so instead of showing mock data as if it were live, they say so explicitly (e.g. "Not connected — needs OPENWEATHERMAP_API_KEY") — see [[architecture/briefing-engine.md]]. Every time that happens (or a task command fails), it's logged to [[../log/requests.md|sunny-vault/log/requests.md]], so real usage tells us which integration to build next.

### Briefing Integration Tasks

- [x] Hardcoded briefing template (morning + evening)
- [x] Text generation engine (slot-filling, no LLM)
- [x] Q&A engine for freeform questions (weather, calendar, tasks, commute, etc.)
- [x] Task summary queries — live against SQLite via [[../TASK_SYSTEM.md|task system]] (no longer mock)
- [x] Honest "not connected" messaging for every section without a real source + request logging to `sunny-vault/log/requests.md`
- [x] Google Sign-In (OAuth) — one connect flow powering both Calendar and Gmail below; code complete, needs a Google Cloud OAuth client + one-time sign-in to go live — see [[architecture/google-integration]]
- [x] Calendar API integration (Google Calendar, via Google Sign-In)
- [x] Email header parsing + urgency detection (Gmail, via Google Sign-In — unread/important counts + subject lines)
- [ ] Weather API integration (OpenWeatherMap or similar)
- [ ] Traffic API integration (Google Maps — **separate from Google Sign-In**, needs its own Maps API key, see [[architecture/google-integration]])
- [ ] Scheduling (7am morning, 9pm evening) — currently manual trigger only
- [ ] Error handling per live API (fail gracefully) — applies once each API actually exists
- [ ] Optional: Email triage via LLM (simple classification)
- [ ] Obsidian staging integration (log briefings)
- [ ] Dashboard: Show last briefing time, next scheduled, status

### Test Deliverables

- [x] Manually trigger morning briefing → see formatted text
- [x] Verify unconnected sections say so instead of faking data, and get logged to requests.md
- [ ] Verify all live API calls work (blocked on API integration above)
- [ ] Test fallback behavior (API fails after being connected → briefing continues)
- [ ] Check Obsidian logging

### Deliverables When Complete

```
⏳ 7am: Briefing generated automatically (manual trigger works today)
⏳ 9pm: Evening briefing generated automatically (manual trigger works today)
⏳ All data from live APIs (tasks live today; calendar/email code-complete pending Google sign-in; weather/commute/health/news still say "not connected")
⏳ Failures logged to Discord #warnings
⏳ Obsidian staging has briefing record
✅ Briefing templates + Q&A engine fully working end-to-end, tasks real, honest gaps elsewhere
```

**Next Step**: Phase 3 (Voice Hardware & TTS)

---

## Phase 3: Voice Out / Clock Hardware

**Timeline**: Week 5-6  
**Dependencies**: Phase 0-2 complete (briefing ready to output)  
**Deliverable**: Working bedside clock with voice output, battery backup, alarm

### Hardware Assembly Tasks

- [ ] Order ESP32-S3 board
- [ ] Order OLED display (128x64 I2C)
- [ ] Order LiFePO4 26650 cell + TP5000 charger
- [ ] Order INMP441 microphone
- [ ] Order 3W speaker
- [ ] Assemble power system (charger → boost → battery)
- [ ] Solder microphone + speaker + display
- [ ] Flash MicroLink Tailscale firmware
- [ ] Test power supply stability
- [ ] 3D print enclosure

### Software Tasks

- [ ] Sonic API integration for TTS
- [ ] Piper TTS fallback (download model)
- [ ] Audio streaming from Lenovo to Clock
- [ ] Speaker amplifier control
- [ ] OLED display driver (time, status, messages)
- [ ] Alarm scheduling (systemd timer or on-device)
- [ ] Battery monitoring (voltage reading, charge state)

### Test Deliverables

- [ ] Manually send TTS to Clock → hear output
- [ ] Test alarm fires on schedule
- [ ] Battery on mains: OLED displays time
- [ ] Unplug power: Clock continues on battery for 2+ hours
- [ ] Measure battery drain rate (target: 12hr survival)

### Deliverables When Complete

```
✅ Clock device: Physical hardware working
✅ On mains: Time displayed, charging
✅ On battery: Continues for 12+ hours
✅ Alarm: Fires on schedule, survives power cut
✅ Voice output: Sonic API TTS + Piper fallback
✅ Tailscale: Clock accessible from Lenovo via mesh
```

**Next Step**: Phase 4 (Voice In / Wake Word)

---

## Phase 4: Voice In / Wake Word Detection

**Timeline**: Week 7-8  
**Dependencies**: Phase 3 complete (Clock hardware ready)  
**Deliverable**: Wake word detection, STT, intent routing

### Wake Word & STT Tasks

- [ ] openWakeWord or Porcupine setup (choose one)
- [ ] Train/tune wake word variants:
  - "Hey Sunny"
  - "Hello Sunny"
  - "Sunny [command]"
- [ ] Whisper API integration (STT)
- [ ] Fallback: Vosk or local Whisper (offline option)
- [ ] I2S audio streaming from Clock to Lenovo
- [ ] Audio buffering + wake word detection loop

### Intent Routing Tasks

- [ ] Hardcoded pattern matching for common commands
- [ ] Route to actions (hardwired vs LLM)
- [ ] Examples:
  - "What time is it?" → Direct answer (system time)
  - "What's the weather?" → API call
  - "Tell me about my day" → Briefing (no LLM)
  - "Remind me to..." → Task creation (LLM if ambiguous)

### Test Deliverables

- [ ] Say "Hey Sunny" → Clock detects, indicates listening
- [ ] Say "What time is it?" → Hear response
- [ ] Say "What's on my calendar?" → Hear today's events
- [ ] Say "Remind me to buy milk" → Task created
- [ ] Test false positives (ambient noise shouldn't trigger)

### Deliverables When Complete

```
✅ Wake word detection: Local, low false-positive rate
✅ STT: Captures user speech accurately
✅ Intent routing: Hardcoded patterns + LLM for ambiguous
✅ Response: TTS back to user
✅ Latency: <5s from wake word to response
```

**Next Step**: Phase 5 (Phone Integration)

---

## Phase 5: Telephony / Phone Calls

**Timeline**: Week 8-9  
**Dependencies**: Phase 4 complete (voice I/O working)  
**Deliverable**: Callable voice interface, live conversation, remote tasking

### Twilio Setup Tasks

- [ ] Register Twilio phone number
- [ ] Webhook setup (authenticated)
- [ ] Incoming call handler (answer automatically or wait for user)
- [ ] STT + intent router + action executor in real-time
- [ ] TTS response back to caller

### Security & Auth Tasks

- [ ] Caller ID allowlist (only Keaton's number by default)
- [ ] PIN backup authentication (if ID spoofed)
- [ ] Confirmation required for destructive actions (send email, etc.)

### Test Deliverables

- [ ] Call Sunny's number from phone
- [ ] Hear greeting, speak command
- [ ] "Start working on physics homework" → Task created + confirmed
- [ ] "What's my next event?" → Hear calendar
- [ ] Hang up → Task saved to Obsidian staging

### Deliverables When Complete

```
✅ Twilio number: Active, receives calls
✅ Authentication: Caller ID + PIN
✅ Live conversation: STT → LLM → TTS (real-time)
✅ Task creation: From phone commands
✅ Confirmation: Important actions require user okay
✅ Cost: <$1/month expected
```

**Next Step**: Phase 6 (Optional) + Phases 7-Ongoing

---

## Phase 6: Remote Power Control (DEPRIORITIZED)

**Timeline**: Later (lower priority)  
**Dependencies**: Phase 5 complete  
**Deliverable**: Remote wake/shutdown of desktop PC

### Tasks

- [ ] Smart plug integration (Tasmota/MQTT) OR Wake-on-LAN
- [ ] Voice command handler ("Turn on the desktop")
- [ ] Safety: Confirmation required
- [ ] Example: Phone call → "Start working" → Desktop wakes up

---

## Phase 7: Custom Hardware Finalization (MUCH LATER)

**Timeline**: After Phase 5 proven  
**Deliverable**: Move from breadboards to custom PCB

### Tasks

- [ ] Design custom PCB (power, audio, signal integrity)
- [ ] Manufacturing (PCBway, similar)
- [ ] Testing & refinement
- [ ] Optional: Smaller/cleaner enclosure

---

## Backlog

Deferred items not yet slotted into a phase — see [[BACKLOG.md]] (currently: service orchestration — systemd unit, single-command startup for all services, per-service runtime toggle, autostart-per-service config).

---

## Ongoing / Cross-Cutting (All Phases)

Work on these in parallel, integrate incrementally:

### Discord Activity Log

**Scoped ahead of this**: a single-channel bot is already built — see [[architecture/discord-bot.md]], [[TASK_SYSTEM.md]], [[architecture/lists.md]], and [[architecture/alarms-reminders.md]]. It handles Tasks, Lists, and Alarms/Reminders (including a 30-second due-item check that pings the channel), all in one `#tasks`-style channel; it doesn't touch the multi-channel activity log below.

- [ ] Set up Discord server + channels:
  - `#briefings` — Briefing output
  - `#calendar-actions` — Calendar updates
  - `#email-actions` — Email processing
  - `#task-updates` — Task changes
  - `#state-changes` — Sleep/wake mode
  - `#warnings` — API errors, credential expiry
  - `#direct-chat` — Live chat alternative
  - `#notion-sync` — What got pushed to Notion
- [ ] Bot integration: Log all actions
- [ ] Permanent searchable audit trail

### Priority Scheduler
- [ ] Queue system for concurrent requests
- [ ] Foreground (user interaction) preempts background
- [ ] Example: Phone call stops briefing playback
- [ ] Dashboard: Show active tasks + queue depth

### Token Circuit Breaker
- [ ] Track LLM usage in real-time
- [ ] Alert if burning tokens too fast
- [ ] Pause execution, ask user to continue/halt
- [ ] Hard cap at provider level (Anthropic: $20/mo)

### Spending Caps
- [ ] Set hard limits on Anthropic account ($20/mo)
- [ ] Set hard limits on Twilio account ($10/mo)
- [ ] Monitor daily spend on dashboard
- [ ] Alert in Discord if approaching limits

### TrueNAS Integration
- [ ] Media update logging to Discord
- [ ] Storage warning in briefing ("Disk 85% full")
- [ ] Future: GPU hosting for local LLM

### Tagged FileZilla Pipeline
- [ ] Watch external server for tagged files
- [ ] Auto-pull to Lenovo
- [ ] Auto-push to TrueNAS

### Proactive Systems (If Time)
- [ ] Proactive call engine (sleep-aware)
  - "Call me if package fails"
  - "Call me if professor emails"
- [ ] Location-aware departure nudges
  - Track location, suggest when to leave
  - Integrate with Discord notifications
- [ ] Nightly wind-down briefing (evening recap)
- [ ] Auto-draft email replies (review before send)
- [ ] Proactive calendar updates (detect changes, update automatically)

---

## Milestones & Dates

| Milestone | Target | Status |
|-----------|--------|--------|
| Phase 0: Foundations | This week | 🔄 Mostly complete — systemd autostart remaining |
| Phase 1: Networking | Week 2 | 🔄 Mostly complete — phone verification + ACLs remaining |
| Phase 2: Briefing | Week 3-4 | 🔄 Templates/Q&A + Calendar/Gmail code-complete (needs Google sign-in) — weather/commute/health/news remaining |
| Phase 3: Clock Hardware | Week 5-6 | ⏳ Upcoming |
| Phase 4: Wake Word | Week 7-8 | ⏳ Upcoming |
| Phase 5: Phone | Week 8-9 | ⏳ Upcoming |
| **MVP**: All 0-5 complete | End Sept 2026 | 🚀 Target |
| Phase 6: Power Control | Q4 2026 | ⏳ Optional |
| Phase 7: Custom PCB | Q4 2026+ | ⏳ Nice-to-have |

---

## Dependencies & Blockers

```
Phase 0
  ├─→ Phase 1 (Networking)
  │   ├─→ Phase 2 (Briefing)
  │   │   ├─→ Phase 3 (Clock Hardware)
  │   │   │   ├─→ Phase 4 (Wake Word)
  │   │   │   │   ├─→ Phase 5 (Phone)
  │   │   │   │   └─→ Phase 6 (Power Control)
  │   │   │   └─→ Phase 7 (Custom PCB)
  │   │   └─→ Ongoing (Discord, Costs, etc.)
  │   └─→ Ongoing (Priority Queue, Circuit Breaker, etc.)
  └─→ Ongoing (Obsidian Vault, Logging, etc.)
```

**Critical Path**: Phase 0 → 1 → 2 → 3 → 4 → 5 = MVP

**Non-blocking**: Phase 6, 7, and all "Ongoing" tasks can start earlier

---

## How to Use This Document

- **Current Status**: Look at "Phase 0" and update checkbox as you progress
- **What's Next**: Check which tasks are blocking (dependencies)
- **Deliverables**: Know what "done" looks like for each phase
- **Timeline**: Adjust dates based on actual progress
- **Cross-cutting**: Pick up "Ongoing" tasks when you have time (no dependencies)

---

## Notes

- **Iterative**: Don't wait for Phase X to be "perfect" before starting Phase X+1
- **Fail gracefully**: Each phase should work standalone (e.g., Phase 2 briefing works without Phase 3 voice)
- **Test often**: End-to-end tests at each phase milestone
- **Document as you go**: Update Obsidian vault with learnings
- **Adjust timeline**: If something takes longer, move other phases accordingly
