---
id: sunny-architecture
type: reference
status: active
source: notion
created: 2026-08-18
tags: [architecture, networking, system-design]
---

# System Architecture

## Network Topology

**Inside Tailscale mesh:**
- Lenovo mini PC (always-on brain)
- ESP32 Clock (mic/speaker/OLED, battery-backed)
- TrueNAS Scale server (media, future GPUs)
- Phone (location, calls)

**Outside mesh, reached on demand:**
- Desktop PC (Wake-on-LAN or smart plug)
- External file server (FileZilla source)

## Request Flow

1. **Input surfaces**: Clock wake word, Twilio phone call, Discord bot chat, scheduled timer jobs
2. **Sunny core**: Priority queue, then intent router
3. **Splits to either**:
   - Direct API calls (no tokens spent) — calendar, weather, traffic
   - Claude API (judgment only) — email triage, task interpretation, conversation
4. **Action executed**, logged, then answered via output surface
5. **Funnels through Obsidian staging layer** before finalized items pushed to Notion

## Compute Architecture

### Lenovo Mini PC (Brain)
- **OS**: Ubuntu Server 20.04, headless
- **BIOS**: Restore power state on AC loss enabled (critical)
- **Systemd**: Sunny runs as `Restart=always` unit
- **Startup**: No unattended-upgrades auto-reboot
- **Python**: Single process in venv under systemd (no Docker, no Proxmox)

### ESP32-S3 Clock (Bedside Device)
- **Brain**: ESP32-S3, low power, handles wake word + hardwired commands
- **Display**: Small OLED, self-lit, low power
- **Power**: LiFePO4 (LFP) 26650 cell, ~3000mAh
  - Charger: TP5000 (LFP-compatible, NOT TP4056)
  - Boost converter for stable 5V
  - Battery backup target: 12 hours
- **Voice I/O**: Thin client for mic/speaker; heavy compute (LLM, TTS) on Lenovo or API
- **Wake word**: openWakeWord or Porcupine variants — "Hey Sunny", "Hello Sunny", "Sunny [command]"

### LLM Hosting Strategy
- **Short term**: Hosted Claude API (Haiku/Sonnet/Opus as needed)
- **Long term**: Local inference on TrueNAS GPUs when affordable

## Networking

All devices join the same Tailscale network:
- ESP32 uses MicroLink (Tailscale-compatible client with WireGuard, DERP, STUN)
- Secure remote access via Tailscale even when away from home
- No port forwarding, no separate auth layer

## Storage & Logging Pipeline

### Obsidian Vault (Local)
```
sunny-vault/
├── inbox/        raw capture, unparsed
├── staging/      structured items awaiting Notion push
├── archive/      already pushed, kept locally
├── reference/    permanent docs (architecture, design, tasks, hardware)
├── log/          2026/08/2026-08-17.md — Discord mirror (append-only)
└── state/        sleep mode, token counters, sync cursor
```

**Design**: One file per item, never shared append target. Atomic writes (write `.tmp`, then `os.rename()`).

### Discord Activity Log
Channels by action type:
- `#calendar-actions` — calendar updates
- `#email-actions` — email processing
- `#reminders` — task updates, briefings
- `#state-changes` — sleep mode, wake mode
- `#warnings` — API expirations, blocked tasks
- `#direct-chat` — live Sunny chat alternative to voice
- `#notion-sync` — what got pushed to Notion

### Notion (Cloud)
- Final, canonical storage for:
  - Calendar events (synced bidirectionally)
  - Tasks and projects
  - Email inbox
  - Logs and activity
- Updated via Obsidian staging layer

## Priority & Concurrency

Multiple input surfaces can be active at once (Clock wake word + Discord chat + scheduled job). Sunny uses a priority queue:

**High priority** (real-time interaction):
- Phone call (Twilio)
- Wake word on Clock
- Direct Discord mention

**Medium priority**:
- Discord messages
- Manual commands

**Low priority**:
- Scheduled briefings
- Background checks (battery, API status)
- Logging

Foreground requests preempt background tasks so interaction never feels slow.

## Local Dashboard

**Bound to Tailscale interface only** (never `0.0.0.0`). Reachable from phone via Tailnet.

**Panels**:
- **Spend**: tokens today, month-to-date, projected cost, breakdown by surface
- **Health**: process uptime, last-success timestamps for Claude, Sonic, Twilio, Discord, Clock
- **Host resources**: CPU, load, temp, RAM, disk (psutil)
- **Clock battery**: charge state (mains vs battery), voltage, runtime remaining
- **Needs attention**: credential expiry, staging items stuck, TrueNAS space, Clock on-battery alerts
- **Recent activity**: last 50 actions from log

**Storage**: SQLite `sunny.db` for metrics, sampled every 30 seconds. Historical data retained for trend analysis.

## Service Inventory

| Service | Purpose | Cost |
|---------|---------|------|
| Claude API | LLM reasoning | ~$1.50-$8/mo |
| Sonic API | Fast TTS | Included |
| Piper TTS | Fallback voice | Free |
| Whisper STT | Speech-to-text | Free (local) or API |
| Twilio | Phone calls | ~$0.01-0.15/min |
| Discord Bot | Messaging & logging | Free |
| Tailscale | Secure networking | Free (personal) |
| Calendar API | Event sync | Free |
| Weather API | Forecasts | Free tier |
| Traffic API | Commute times | ~$3-4/mo |
| Notion | Cloud storage | Free tier |
| Obsidian | Local vault | Free |
| TrueNAS | Media/storage | Self-hosted |

**Total monthly**: ~$5-$8 with hard caps at provider level.
