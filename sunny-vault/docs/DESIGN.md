---
id: sunny-design
type: architecture
status: active
created: 2026-08-18
tags: [design, architecture, principles, specifications]
---

# Project SUNNY — Design Document

## Smart Unified Network Navigating Yond

Sunny is a self-hosted voice assistant that lives on a bedside device (the Clock), wakes me up, briefs me, answers the phone, and can power on my desktop remotely. Deterministic where possible, LLM only where judgement is genuinely needed.

---

## What This Is

Sunny is an always-on personal voice assistant that lives on a bedside device (the [[clock]]), wakes you up, briefs you, answers the phone, and can power on your desktop remotely. Deterministic where possible, LLM only where judgment is genuinely needed.

---

## How It All Actually Runs

Sunny is an always-on program on a Lenovo mini PC, listening concurrently across all input surfaces rather than one at a time:
- Wake word audio from the Clock (over Tailscale)
- Incoming Twilio webhooks for phone calls
- Discord bot messages
- Scheduled jobs like the morning and nightly briefings running on timers

Each input source runs as its own background process or async task, all feeding into a shared priority system (see Compute and LLM priority system below) that decides what gets LLM attention first based on which surface you are actively using. Whatever action is decided on—a calendar update, a Discord log post, a spoken reply—gets executed and funnels through the Obsidian staging layer before anything finalized gets pushed to Notion.

---

## Design Principles

### Templates First, Tokens Last
The briefing is a fixed script with slots filled from APIs. No LLM call needed for facts.

### LLM Only for Judgment
Email triage, task interpretation, freeform phone conversation.

### No LLM for Information Lookups
Applies globally across every feature: any time Sunny is just checking or fetching information (calendar, weather, traffic, location, financial emails, API status, etc.), it must use direct API calls or deterministic logic, never routing through the LLM unless genuine judgement or interpretation is actually required.

### Sonic API for Fluent Voice
Local Piper TTS as a fallback if the API is down, and as a cost-saving option Sunny can suggest during long conversations.

### Fail Quietly
If the weather API is down, the alarm still goes off.

### Audible State Cues
Sunny plays a distinct short sound whenever it pings the LLM (so it's audibly clear when a request left the deterministic path and started costing tokens), and a different, distinct sound whenever it's actually taking an action (e.g. sending an email, updating the calendar, powering on the desktop). These two sounds must never be the same, so it's always obvious by ear alone whether Sunny is "thinking" (LLM call in flight) or "doing" (executing a real effect).

---

## The Four Capabilities

1. **Bedside clock + alarm** with battery backup so a power cut doesn't mean a missed alarm.
2. **Morning briefing** — calendar, weather, overdue tasks, email that matters, commute, yesterday's unfinished items.
3. **Callable by phone** — ring a number, tell it to start working on tasks before I get home.
4. **Remote power control** for the main computer.

---

## Hardware and Architecture

### Compute

- **Brain**: existing Lenovo mini PC, always-on. Can connect to a monitor if needed for setup and debugging.
- **Operating system**: Ubuntu Server 26.04 LTS. Chosen over Debian for newer hardware support via the HWE kernel, a larger community/troubleshooting base for a hobby build, and smoother NVIDIA/CUDA tooling if a GPU ever ends up in the Lenovo itself. 26.04 chosen over 24.04 LTS for the longer support window, with the plan to fall back to 24.04 LTS if anything on the freshest release proves flaky. *Actual install*: the installer brought in a desktop environment, and it was kept rather than stripped to headless — Sunny itself still runs as a background process regardless of GUI presence. Snap declined at install (skip Featured Server Snaps) rather than purged after.
- **BIOS**: set to restore power state on AC loss (usually under Power Management). This is critical and easy to overlook. The Clock has a battery so a power cut does not kill the alarm, but if the Lenovo does not boot back up when power returns, the Clock has nothing to talk to and the battery achieves nothing.
- **Sunny runs as a systemd unit** with Restart=always. This is the actual mechanism for surviving crashes and reboots.
- **Disable unattended-upgrades** automatic reboot, or pin it to a chosen window. A security patch rebooting the box at 3am is a missed alarm.
- **No Docker and no Proxmox**. One Python process in a venv under systemd is simpler to debug at 2am; this project's failure mode is complexity, not scale.
- Raspberry Pi may still be used later for peripheral tasks (wake word listening, display driver) but the mini PC is the primary compute for now.

### LLM Hosting Strategy

- **Short term**: hosted Claude API rather than local inference, to avoid buying GPUs right away. This is separate from the Claude Pro chat subscription, which does not cover programmatic API usage.
- **Estimated monthly cost** at expected usage:
  - Claude Haiku 4.5: ~$1.50
  - Claude Sonnet 5: ~$3.00
  - Claude Opus 5: ~$8.00
  - **Sonnet 5 is the likely sweet spot** for cost versus quality.
- **Long term**: migrate to local inference on home GPUs once affordable.

---

## The Clock (Custom Hardware Device)

### Concept

A dedicated physical device, hard-baked with local commands like the original pre-AI Alexa or Google Home Mini, rather than routing everything through an LLM.

**Budget target**: under one hundred dollars  
**Battery backup target**: twelve hours

### Hardware

- **Brain**: ESP32 board, cheap, low power, handles wake word detection and hardwired commands, hands off complex requests to the Lenovo mini PC.
- **Display**: small OLED screen, self-lit and low power, stays visible in the dark without a backlight draining the battery.
- **Power**: LiFePO4 (LFP) cell rather than LiPo or standard Li-ion, chosen for stability.
  - Nominal 3.2V, full 3.65V
  - Thermal runaway threshold around 270°C versus roughly 150°C for LiPo
  - 2000 to 5000 cycles versus 300 to 500
  - Tolerates sitting on float charge at full state of charge indefinitely, which is exactly how a mains-powered bedside device lives. LiPo degrades and swells under that condition.
- **Charger**: the TP4056 is NOT compatible and must not be used—it is a 4.2V Li-ion charger and will overcharge an LFP cell. Use a TP5000 (configurable for LFP) or a CN3058-based LFP charging module instead.
- **Cell sizing**: LFP has lower energy density, roughly 1500mAh for an 18650 LFP versus 3000+ for Li-ion. For the twelve hour target with boost converter losses, an 18650 LFP is marginal. Plan on a 26650 (around 3000mAh) or two 18650 LFP cells in parallel.
- **Boost converter board** still required for stable 5V, and benefits from LFP's flat discharge curve giving a steadier input voltage.
- **Off-the-shelf breakout boards** for now rather than a custom PCB; custom PCB is a later refinement once the design is proven.
- **Enclosure**: 3D printed, custom designed.
- **Voice output**: Sonic API handles fluent, fast voice generation, streamed down to the clock's speaker. The ESP32 is a thin client for mic, speaker, and screen; heavy compute (LLM reasoning, TTS) happens on the Lenovo mini PC or hosted API, not on the device itself.

### Planned Features

- **Adaptive volume**: measures ambient room noise (and/or the user's speaking volume) just before or while responding, and scales output volume relative to that noise floor so it's never too quiet in a loud room or too loud in a quiet room.
- **Talk-over ducking**: briefly lowers or pauses its own audio output if it detects the user talking over it.

---

## Networking

- All devices—the Lenovo mini PC, the ESP32 clock, and any future devices—join the same Tailscale network so they can talk to each other securely regardless of physical network, not just over home WiFi.
- **ESP32 side** uses the MicroLink project, a Tailscale-compatible client for ESP32 with WireGuard encryption, DERP relay, and STUN support. Recommended on ESP32-S3 variants for best results.
- **Also supports remote access** for the phone use case, since the clock and mini PC can reach each other even when you are out of the house.

---

## Phone Call Authentication

- **Caller ID allowlist** as the primary method, since you are the only expected caller.
- **PIN as a backup method** in case caller ID is unavailable or spoofed.

---

## Additional Feature Ideas

### Nightly Wind-Down Briefing
The evening counterpart to the morning briefing. Recaps what got done today, what's still open, and gently previews tomorrow's plan before sleep.

### Proactive Call Engine
A rule engine for conditions like "call me if a package delivery fails" or "call me if my professor emails", so Sunny proactively rings you instead of waiting to be asked.

Sleep-aware: only calls during hours you are actually awake. Sleep and wake state detected by saying "good night" (enters sleep mode, calls suppressed) and "good morning" (exits sleep mode, calls resume).

### Proactive Calendar Updates
When a schedule change is detected (e.g. a professor cancels class, an event time changes), Sunny proactively updates or marks the calendar event itself, rather than just mentioning the change in the briefing and leaving you to update it manually.

### Location-Aware Departure Nudges
- Track your rough location (phone location shared over Tailscale or a simple location API)
- Cross-reference against the calendar and known/live travel time (accounting for traffic or transit delays)
- Proactively nudge you on when to leave and how long the trip will take, e.g. "leave in 10 minutes to make your 2pm"
- **Notification channel**: Discord (via Discord's free Bot API, no per-message fees, unlimited messaging, only cost is hosting which is already covered by the Lenovo mini PC). Chosen over Telegram since you already use Discord and don't want to install a new app, and it handles longer freeform conversations better than Telegram. Phone calls (via Twilio, since Discord bots cannot ring a real phone number) reserved strictly for emergencies, or for non-emergency alerts if you are detected driving (driving state only checked when there's actually a notification to send, to minimize API calls).

### Discord Server as Activity Log
- A dedicated Discord server acts as a permanent, searchable audit trail / hard copy of everything Sunny does. Free, since it's just standard Discord bot messaging.
- **Channels**, sorted by action type: every action Sunny takes is posted into a channel matching its category (e.g. calendar actions, email actions, reminders, briefings, good night/good morning state changes)
- **Warnings channel**: flags things that need attention, like API keys or credentials nearing expiration, or information Sunny doesn't currently have access to but needs
- **Direct chat channel**: a channel where you can talk to Sunny live, directly through Discord, as an alternative input method to voice or phone
- **Notion sync channel**: lists exactly what has been pushed to Notion, mirroring those finalized updates
- **Obsidian mirroring**: everything happening across all Discord channels and logs is also mirrored into the Obsidian vault as a permanent local copy, in addition to living in Discord
- **Traffic/location checks**: not continuous or background; they only run when a calendar event is explicitly marked as requiring a location check (e.g. a fixed arrival time like needing to be at school by a certain time). Exact trigger criteria still to be flushed out.

### Costs

- **WhatsApp**: replies within 24 hours of you messaging in are free service conversations (unlimited, since Nov 2024). Unprompted outbound utility messages (no open window) cost roughly two and a half cents each in the US.
- **Twilio voice call**: roughly under a cent per minute inbound, about one and a half cents per minute outbound for the raw call. If it's a live AI voice call (speech-to-text plus LLM in real time, e.g. the phone tasking feature), add roughly five to twelve cents per minute for the AI pipeline. A five minute AI call could run thirty to sixty cents.
- **Estimated cost**: traffic-aware distance/travel-time API checked periodically during active commute windows (not all day) runs roughly three to four dollars a month. Combined with WhatsApp nudges, still only a few dollars a month on top of existing costs.

### Other Proactive Action Ideas (Not Yet Decided)

- Auto-draft (not send) replies to routine emails so they're ready to review
- Auto-reschedule a task to the next day if it's clearly not getting done today, instead of letting it silently go overdue
- Scan financial emails for upcoming bills and proactively create a reminder before the due date

---

## Security and Cost Safety

- **Hard spending caps** set directly on provider accounts (Anthropic, Twilio), not just in Sunny's own code, so billing stops at the provider level even if there's a bug in Sunny's logic.
- **Twilio webhook properly authenticated** so random callers can't reach it and start issuing commands.
- **API keys and secrets** rotated periodically, never hardcoded
- **Phone authentication** (caller ID allowlist plus PIN): caller ID alone can be spoofed, so the PIN is a genuine second factor, not just a formality.
- **Confirmation step required** before any action with real financial or irreversible consequences (e.g. sending an email on your behalf, making a payment), rather than fully autonomous execution.
- **Tailscale network** keeps the Clock and mini PC off the open internet, reducing exposed attack surface.

---

## Compute and LLM Priority System

Since Sunny can be interacted with from multiple surfaces (the Clock, phone calls, Discord direct chat, etc.), whichever surface you are actively engaging with in the moment gets top priority for compute and LLM access. Background or lower-priority work (proactive checks, logging, non-urgent briefing prep, etc.) is deprioritized or paused so active, real-time interaction never feels slow or laggy.

Needs a queue or priority scheduler design so active foreground requests always preempt background tasks.

---

## TrueNAS Integration

- Home media server runs TrueNAS Scale, connected via Tailscale. Will eventually host the local GPUs once affordable (see LLM hosting strategy).
- **Media update logging**: whenever media is added or updated on the server, Sunny logs it to a dedicated Discord channel.
- **Storage monitoring**: Sunny checks storage levels and includes a low-storage warning in the daily briefing if space is running low.

### Tagged File Pull Pipeline (FileZilla Workflow)

- You upload files to a separate external server via FileZilla, into a specific subfolder
- Sunny watches that subfolder for files with specific tags
- Tagged files are automatically pulled through the Lenovo mini PC and pushed onward into the personal TrueNAS server, replacing manual transfer

---

## Obsidian Vault Structure

Two distinct things live in the vault with different lifecycles, and they should not share a tree:

- **Staging**: transient. Pushed to Notion, then moves out.
- **Log mirror**: permanent, append-only, never syncs anywhere.

```
sunny-vault/
├── inbox/        raw capture, unparsed
├── staging/      structured items awaiting Notion push
├── archive/      already pushed, kept locally
├── log/          2026/08/2026-08-17.md — Discord mirror
└── state/        sleep mode, token counters, sync cursor
```

- **One file per item**, never a shared append target. The core process runs concurrent async tasks across four input surfaces. If they all append to a single daily file, that invents a locking problem for no reason. One file per item means zero write contention.
- **Every staging file carries frontmatter**: `id`, `type`, `status`, `source`, `created`, `notion_id`.
- **The sync sweeper** scans for `status: pending`, batches them into a single Notion call, writes back `synced` plus the returned `notion_id`, then moves the file to `archive/`. The `id` field is what makes retries safe: a half-failed push can be re-run against the same IDs without creating duplicates.
- **Atomic writes**: write to a `.tmp` file, then `os.rename()`. A sweeper reading a file mid-write parses garbage. Rename is atomic on Linux, so the file either does not exist or is complete. This is the failure that otherwise appears at 3am.
- **The `log/YYYY/MM/` nesting** is functional, not cosmetic. Obsidian's indexer degrades badly past roughly ten thousand files in a single folder; the nesting is what keeps the vault openable in a year.
- The Dataview plugin renders a live pending-sync dashboard off that frontmatter for free, with no work required from Sunny.

---

## Architecture Summary

### Network Topology

- **Inside the Tailscale mesh**: Lenovo mini PC (always-on brain), the Clock (ESP32-S3, mic/speaker/OLED), TrueNAS Scale server (media, future GPUs), phone (location, calls)
- **Outside the mesh**, reached on demand: Desktop PC (Wake-on-LAN or smart plug), external file server (FileZilla source)

### Request Flow

1. **Input surfaces**: Clock wake word, Twilio phone call, Discord bot chat, scheduled timer jobs
2. **Sunny core process**: priority queue, then intent router
3. **Splits** either to direct API calls (no tokens spent) or to the Claude API (judgement only). Most requests never reach the LLM.
4. **Action executed**, logged, then answered
5. **Out to output surfaces** (voice, Discord, call) and into the Obsidian vault as markdown staging
6. **Finalized items only** pushed onward to Notion

### Service Inventory

- **Voice pipeline**: Sonic API, Piper TTS, Whisper STT, wake word (openWakeWord or Porcupine)
- **Data lookups**: Calendar, Weather, Email, Traffic
- **Comms and network**: Twilio, Discord bot, Tailscale, MicroLink
- **Brain and storage**: Claude API, Notion, Obsidian, TrueNAS

Of the sixteen services, only Claude, Sonic, and Twilio cost money per use. The rest are free tiers or self-hosted, which is why the whole system lands around five dollars a month.

---

## Token Usage Circuit Breaker

- Sunny tracks token usage in real time during any task or conversation
- If usage crosses a defined threshold (total tokens for the task, or an unusually high burn rate), Sunny pauses execution immediately rather than continuing to spend
- Sends a Discord message explaining what it was doing when it paused, and asks whether to continue or halt and save the current state for later

---

## See Also

- [[phases]] — Build timeline with dependencies and deliverables
- [[dashboard]] — Local web UI for monitoring
- [[brain]] — Lenovo mini PC compute details
- [[clock]] — ESP32 hardware specifications
- [[networking]] — Tailscale mesh configuration
