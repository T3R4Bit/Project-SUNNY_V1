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
**Current Status**: Ubuntu Server 26.04 LTS installed and running on the Lenovo (sunshine-m700) under a systemd unit (`Restart=always`, autostart on boot — see `SETUP_LINUX.md`). Core app — briefing engine, task system, [[architecture/lists.md|lists]], [[architecture/alarms-reminders.md|alarms/reminders]], the combined console (chat + system status, one page at `/console`), Discord bot (connected to a live server, split into a chat channel and a read-only dashboard channel — see [[architecture/discord-bot]]) — all built and working over Tailscale, now also over HTTPS (`TLS_CERTFILE`/`TLS_KEYFILE`, port 5443) for endpoints that need it, like the Google OAuth callback.
**Deliverable**: Sunny process running locally, basic logging, systemd autostart

### Setup Tasks

- [x] Decide on headless Linux OS (Ubuntu Server 26.04 LTS, switched from Debian)
- [x] Decide on LiFePO4 battery swap and matching charger/cell sizing
- [x] Decide on BIOS restore-on-AC-loss requirement
- [x] Install Ubuntu Server 26.04 LTS on Lenovo mini PC (headless, no GUI)
- [x] Python env setup on the Lenovo (`run.sh` creates/manages `venv/` automatically — no manual venv step)
- [x] Git repo + folder structure
- [x] Logging from the start
- [x] Set up local dashboard skeleton — now functional, not just skeleton: FastAPI app bound to `0.0.0.0:5000`, one combined console at `/console` (chat + live system/Google status — `/` and the old `/chatbot` both redirect there), sunny.db + scheduled.db via SQLite, tasks + lists stored as markdown in the vault (see [[architecture/vault-storage]])
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
Lenovo: 100.x.x.x (stable, always-on)
TrueNAS: 100.x.x.x (accessible from mesh)
Phone: Joins mesh, can ping devices
Firewall: No open ports exposed (all behind Tailscale)
Remote access: Works even away from home (DERP relays)
```

**Next Step**: Phase 2 (Briefing Engine)

---

## Phase 2: Briefing Engine (TASKS + CALENDAR + EMAIL + WEATHER LIVE, REST PENDING)

**Timeline**: Week 3-4
**Dependencies**: Phase 0-1 complete
**Deliverable**: Working morning and evening briefings

**Current status**: The engine itself is built and working — hardcoded morning and evening templates, slot-filling text generation, and a Q&A system covering weather, calendar, email, tasks, commute, health, motorsports, news, and tomorrow. Tasks are real, queried live from the vault (`sunny-vault/state/tasks/`, markdown — not a database, see [[architecture/vault-storage]]). Calendar and email are wired via Google Sign-In (OAuth) — see [[architecture/google-integration]] — client configured, HTTPS + a PKCE bug both had to be fixed before a sign-in could complete, not yet confirmed working end-to-end. Weather is code-complete via OpenWeatherMap — needs `OPENWEATHERMAP_API_KEY` **and** `WEATHER_LOCATION` in `.env` (a key alone isn't enough — see `sunny_code/components/weather.py`). Commute, health, motorsports, and news still have no real API behind them, so instead of showing mock data as if it were live, they say so explicitly (e.g. "Not connected — needs OPENWEATHERMAP_API_KEY and WEATHER_LOCATION in .env") — see [[architecture/briefing-engine.md]]. Every time that happens (or a task command fails), it's logged to [[../log/requests.md|sunny-vault/log/requests.md]], so real usage tells us which integration to build next.

### Briefing Integration Tasks

- [x] Hardcoded briefing template (morning + evening)
- [x] Text generation engine (slot-filling, no LLM)
- [x] Q&A engine for freeform questions (weather, calendar, tasks, commute, etc.)
- [x] Task summary queries — live against SQLite via [[../TASK_SYSTEM.md|task system]] (no longer mock)
- [x] Honest "not connected" messaging for every section without a real source + request logging to `sunny-vault/log/requests.md`
- [x] Google Sign-In (OAuth) — one connect flow powering both Calendar and Gmail below. OAuth client configured, HTTPS + a PKCE bug both had to be fixed before a sign-in could complete — see [[architecture/google-integration]]
- [x] Calendar API integration (Google Calendar, via Google Sign-In)
- [x] Email header parsing + urgency detection (Gmail, via Google Sign-In — unread/important counts + subject lines)
- [x] Weather API integration (OpenWeatherMap) — code complete, needs `OPENWEATHERMAP_API_KEY` in `.env` + a location set on `/console` (LOCATION card) to go live — see [[architecture/location]]
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
7am: Briefing generated automatically (manual trigger works today)
9pm: Evening briefing generated automatically (manual trigger works today)
All data from live APIs (tasks live today; calendar/email code-complete pending Google sign-in; weather code-complete pending OPENWEATHERMAP_API_KEY + a location set on /console; commute/health/news still say "not connected")
Failures logged to Discord #warnings
Obsidian staging has briefing record
Briefing templates + Q&A engine fully working end-to-end, tasks real, honest gaps elsewhere
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
- [x] Piper TTS fallback (download model) — built ahead of the hardware, 2026-08-20, as a standalone `/speak` Discord slash command (no Clock device needed for this piece) — see [[architecture/tts-piper]]. Still needed here: wiring Piper as the actual *fallback* once Sonic API + the Clock's audio streaming exist.
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
Clock device: Physical hardware working
On mains: Time displayed, charging
On battery: Continues for 12+ hours
Alarm: Fires on schedule, survives power cut
Voice output: Sonic API TTS + Piper fallback
Tailscale: Clock accessible from Lenovo via mesh
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
Wake word detection: Local, low false-positive rate
STT: Captures user speech accurately
Intent routing: Hardcoded patterns + LLM for ambiguous
Response: TTS back to user
Latency: <5s from wake word to response
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
Twilio number: Active, receives calls
Authentication: Caller ID + PIN
Live conversation: STT → LLM → TTS (real-time)
Task creation: From phone commands
Confirmation: Important actions require user okay
Cost: <$1/month expected
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

A single command-channel bot is built and connected to a live server — see [[architecture/discord-bot.md]], [[TASK_SYSTEM.md]], [[architecture/lists.md]], and [[architecture/alarms-reminders.md]]. It handles Tasks, Lists, Alarms/Reminders, and server administration (create/delete channels & roles — see below), all read from one `#chat`-style command channel (`DISCORD_CHAT_CHANNEL_ID`). The pinned task dashboard now lives in its own separate, read-only channel (`DISCORD_TASKS_CHANNEL_ID`, optional, falls back to chat if unset) — added 2026-08-20 so a busy chat doesn't bury the dashboard. Three of the eight originally-planned output channels are now built as optional destinations the bot *posts* to (still only reads commands from the chat channel):

- [x] `#task-updates` — Task changes (create/update/delete), from any interface
- [x] `#warnings` (named `#errors` on the live server) — API errors, missing credentials; live and configured, posts here instead of the chat channel
- [x] `#chat` — this **is** the existing command channel (`DISCORD_CHAT_CHANNEL_ID`), name it whatever you like
- [x] `#briefings` — Briefing output, cross-posted whenever "morning"/"evening" is typed in the command channel
- [ ] `#calendar-actions` — Calendar updates — **blocked**: Calendar is read-only Q&A today (see [[architecture/google-integration]]), nothing ever *takes an action* on it to log
- [ ] `#email-actions` — Email processing — **blocked**: same reason, Gmail is read-only Q&A today
- [ ] `#state-changes` — Sleep/wake mode — **blocked**: this concept isn't tracked anywhere in the codebase yet
- [ ] `#notion-sync` — What got pushed to Notion — **blocked**: no Notion integration exists at all
- [x] Bot integration: Log all actions — done for the four channels above that have something to log
- [ ] Permanent searchable audit trail — the channels themselves *are* a searchable log today (Discord's own search); a separate persisted audit trail beyond that isn't built

**Also built, not in the original plan**: server administration — `create/delete channel <name>`, `create/delete role <name>`, `give/remove <@user>` a role, `list channels`/`list roles`. See [[architecture/discord-bot.md]] for the full command list and the two safety guardrails.

### Priority Scheduler
- [ ] Queue system for concurrent requests — `llm_client.py` has a lightweight `asyncio.Semaphore(1)` stand-in (caps in-flight LLM calls at 1), not a real priority queue
- [ ] Foreground (user interaction) preempts background
- [ ] Example: Phone call stops briefing playback
- [ ] Dashboard: Show active tasks + queue depth

Still fully unbuilt as a real scheduler — no concrete concurrent-caller scenario exists yet (would need [[phone]]/[[clock]] hardware). See [[architecture/llm-readiness]].

### Token Circuit Breaker
- [x] Track LLM usage in real-time — `token_tracker.py`, tested (`record_usage`/`get_today_usage`, per-model breakdown, live in `sunny.db`)
- [ ] Alert if burning tokens too fast — only a cumulative cap exists, not a burn-rate/velocity alert
- [x] Pause execution — `llm_client.ask_claude()` refuses (returns `None`) once `check_budget()` fails, automatically, every call. **Not built**: interactively asking the user to continue/halt — it just pauses silently until the cap window rolls over
- [ ] Hard cap at provider level (Anthropic: $20/mo) — external, user action at console.anthropic.com; the in-app cap above is self-tracked, not authoritative billing

Full breakdown: [[architecture/llm-readiness]].

### Spending Caps
- [ ] Set hard limits on Anthropic account ($20/mo) — external, user action
- [ ] Set hard limits on Twilio account ($10/mo) — no Twilio integration exists yet, unrelated to this pass
- [x] Monitor daily spend on dashboard — `GET /api/dashboard/spend/today` and `/spend/month`, tested
- [ ] Alert in Discord if approaching limits — not built, logs only today

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
  - Natural extension of [[architecture/location|the location store]] — swap its
    single static value for a per-session/per-device one instead of adding a
    separate system
- [ ] Nightly wind-down briefing (evening recap)
- [ ] Auto-draft email replies (review before send)
- [ ] Proactive calendar updates (detect changes, update automatically)

---

## Milestones & Dates

| Milestone | Target | Status |
|-----------|--------|--------|
| Phase 0: Foundations | This week | Mostly complete — systemd autostart remaining |
| Phase 1: Networking | Week 2 | Mostly complete — phone verification + ACLs remaining |
| Phase 2: Briefing | Week 3-4 | Templates/Q&A + Calendar/Gmail/Weather code-complete (needs sign-in/keys) — commute/health/news remaining |
| Phase 3: Clock Hardware | Week 5-6 | Upcoming |
| Phase 4: Wake Word | Week 7-8 | Upcoming |
| Phase 5: Phone | Week 8-9 | Upcoming |
| **MVP**: All 0-5 complete | End Sept 2026 | Target |
| Phase 6: Power Control | Q4 2026 | Optional |
| Phase 7: Custom PCB | Q4 2026+ | Nice-to-have |

---

## Dependencies & Blockers

```
Phase 0
  ├─→ Phase 1 (Networking)
  │ ├─→ Phase 2 (Briefing)
  │ │ ├─→ Phase 3 (Clock Hardware)
  │ │ │ ├─→ Phase 4 (Wake Word)
  │ │ │ │ ├─→ Phase 5 (Phone)
  │ │ │ │ └─→ Phase 6 (Power Control)
  │ │ │ └─→ Phase 7 (Custom PCB)
  │ │ └─→ Ongoing (Discord, Costs, etc.)
  │ └─→ Ongoing (Priority Queue, Circuit Breaker, etc.)
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
