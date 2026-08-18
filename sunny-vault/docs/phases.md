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

## Phase 0: Foundations (IN PROGRESS)

**Timeline**: This week  
**Current Status**: Ubuntu Server 20.04 installed, BIOS configured  
**Deliverable**: Sunny process running locally, basic logging, systemd autostart

### Setup Tasks

- [x] Decide on headless Linux OS (Ubuntu Server 20.04)
- [x] Decide on LiFePO4 battery specs
- [x] Decide on BIOS restore-on-AC-loss
- [x] Install Ubuntu Server 20.04 on Lenovo
- [x] Configure BIOS (power restore, boot order, disable PXE)
- [ ] Set BIOS to restore power state on AC loss
- [ ] Disable unattended-upgrades auto-reboot (or pin to window)
- [ ] Set up Python virtual environment
- [ ] Create project folder structure (config, logs, scripts, etc.)
- [ ] Set up secrets handling (env vars + config file)
- [ ] Create git repo + folder structure
- [ ] Structured logging module (with levels, rotating files)
- [ ] Set up Obsidian vault structure (inbox/staging/archive/log/state)
- [ ] Set up systemd unit (Restart=always)
- [ ] Create basic dashboard skeleton (FastAPI, bound to Tailscale)
- [ ] SQLite setup (sunny.db for metrics)

### Deliverables When Complete

```
✅ Lenovo running Ubuntu Server 20.04
✅ BIOS configured for auto-boot on power restore
✅ Python venv with base dependencies
✅ Sunny process starts on boot via systemd
✅ Structured logging to logs/ folder
✅ Obsidian vault ready (empty but structured)
✅ Dashboard accessible at http://localhost:5000 (not yet functional)
```

**Next Step**: Phase 1 (Networking)

---

## Phase 1: Networking

**Timeline**: Week 2  
**Dependencies**: Phase 0 complete  
**Deliverable**: All devices securely connected via Tailscale mesh

### Networking Tasks

- [ ] Install Tailscale on Lenovo [[brain]]
- [ ] Generate stable private IP for Lenovo (100.x.x.x)
- [ ] Install Tailscale on TrueNAS server
- [ ] Verify TrueNAS connectivity to Lenovo
- [ ] Flash MicroLink firmware on future ESP32 [[clock]]
- [ ] Test ESP32-Clock WiFi + Tailscale connectivity
- [ ] Configure Tailscale ACLs (optional, all devices trust each other for now)
- [ ] Install Tailscale on phone
- [ ] Test phone dashboard access via Tailscale
- [ ] Document all device IPs and hostnames

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

## Phase 2: Briefing Engine

**Timeline**: Week 3-4  
**Dependencies**: Phase 0-1 complete  
**Deliverable**: Working morning and evening briefings

### Briefing Integration Tasks

- [ ] Calendar API integration (Google Calendar or Notion)
- [ ] Weather API integration (OpenWeatherMap or similar)
- [ ] Traffic API integration (Google Maps)
- [ ] Task summary queries (from Notion or SQLite)
- [ ] Email header parsing + urgency detection
- [ ] Hardcoded briefing template (morning + evening)
- [ ] Text generation engine (slot-filling, no LLM)
- [ ] Scheduling (7am morning, 9pm evening)
- [ ] Error handling per API (fail gracefully)
- [ ] Optional: Email triage via LLM (simple classification)
- [ ] Obsidian staging integration (log briefings)
- [ ] Dashboard: Show last briefing time, next scheduled, status

### Test Deliverables

- [ ] Manually trigger morning briefing → see formatted text
- [ ] Verify all API calls work
- [ ] Test fallback behavior (API fails → briefing continues)
- [ ] Check Obsidian logging

### Deliverables When Complete

```
✅ 7am: Briefing generated automatically
✅ 9pm: Evening briefing generated automatically
✅ All data from APIs (no LLM calls except optional email triage)
✅ Failures logged to Discord #warnings
✅ Obsidian staging has briefing record
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

## Ongoing / Cross-Cutting (All Phases)

Work on these in parallel, integrate incrementally:

### Discord Activity Log
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
| Phase 0: Foundations | This week | 🔄 In Progress |
| Phase 1: Networking | Week 2 | ⏳ Upcoming |
| Phase 2: Briefing | Week 3-4 | ⏳ Upcoming |
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
