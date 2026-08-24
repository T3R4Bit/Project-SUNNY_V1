---
id: sunny-brain
type: component
status: active
created: 2026-08-18
tags: [hardware, compute, brain]
---

# Brain — Lenovo Mini PC

The always-on central compute for Project SUNNY. Runs Sunny core process, handles LLM API calls, processes voice, orchestrates all background jobs.

## Hardware

- **Model**: Lenovo ThinkCentre (existing mini PC)
- **CPU**: x86-64 (sufficient for Whisper, LLM API calls, async tasks)
- **RAM**: Typical mini PC RAM (8-16GB recommended)
- **Storage**: SSD for OS + logs
- **Power**: Mains-powered, always-on

## Operating System

- **OS**: Ubuntu Server 26.04 LTS
- **GUI**: None — runs headless
- **SSH**: Remote access available (primary way in, since there's no GUI)

## Critical BIOS Settings

- **Restore Power State on AC Loss**: ENABLED
  - Auto-boots when power is restored after outage
  - Essential for alarm reliability
- **Boot Order**: Local disk first, no USB/PXE
- **Sleep/Suspend**: Disabled (always-on)
- **Unattended-upgrades auto-reboot**: Disabled (can't miss 3am reboot)

## Systemd Configuration

Sunny runs as a systemd user service with auto-restart:

```ini
[Unit]
Description=Project SUNNY Assistant
After=network.target

[Service]
Type=simple
User=sunny
WorkingDirectory=/home/sunny/Project-SUNNY
ExecStart=/home/sunny/Project-SUNNY/run.sh server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Restart=always**: If Sunny crashes, systemd restarts it within 10 seconds.

See [[../../SETUP_LINUX.md]] for the exact `systemctl` commands to install this unit.

## Python Environment

`run.sh` owns the virtual environment end-to-end — it creates `venv/` on first run, activates it, and installs `requirements.txt`. There is no manual `python3 -m venv` / `source .../activate` step; systemd invokes `run.sh` directly, and the launcher handles the rest.

**No Docker, no Proxmox**: Single process in an auto-managed venv under systemd. Simpler to debug at 2am.

## Networking

- **Tailscale**: Joined to mesh for secure communication with [[clock]], [[networking|TrueNAS]], phone
- **Interfaces**: eth0 (local home network) + Tailscale (secure mesh)

Uses Tailscale for all inter-device communication. No devices exposed to public internet.

## Processes & Async Tasks

Sunny runs multiple concurrent async tasks:

```python
# Main background tasks
- Wake word listener (from Clock, via Tailscale)
- Twilio webhook receiver (phone calls)
- Discord bot client (messaging)
- Scheduled briefing jobs (7am, 9pm timers)
- Background health checks (battery, API status)
- Obsidian sync sweeper (push staging to Notion)

# All feeding into:
Priority Queue → Intent Router → [[llm-integration|Claude API]] or Direct APIs → Action Executor
```

## Storage

- **Logs**: `/home/keato/sunny/logs/` (structured logging)
- **Database**: `/home/keato/sunny/sunny.db` (SQLite for metrics)
- **Config**: `/home/keato/sunny/config/` (secrets via env vars, never hardcoded)
- **Obsidian vault**: Synced to `/home/keato/sunny-vault/` on Tailscale network or local

## Dependencies

**Internal**:
- [[clock]] — receives wake word audio
- [[networking]] — Tailscale mesh
- [[priority-queue]] — request orchestration
- [[llm-integration]] — Claude API calls
- [[obsidian-vault]] — staging area

**External APIs**:
- [[llm-integration|Claude API]] — LLM reasoning
- Calendar API — event sync
- Weather API — forecasts
- Email API — inbox access
- Traffic API — commute times
- [[discord-bot]] — log posting
- [[phone]] — Twilio webhook

## Monitoring

- Systemd monitors process uptime and restarts
- Dashboard tracks CPU, RAM, disk, temperature
- Syslog captures system events
- Structured logging in application logs

## Failure Modes

| Scenario | Behavior | Recovery |
|----------|----------|----------|
| Sunny process crashes | Systemd restarts within 10s | Auto-restart |
| Power cut | Lenovo boots via BIOS setting | [[clock]] runs on battery until boot |
| Network down | Queued actions retry on reconnect | Discord posts buffered |
| API rate limit | Log to #warnings, continue | Retry after cooldown |
| Disk full | Logging fails, system unstable | Manual cleanup needed |

## Performance Characteristics

- **Startup time**: ~5-10s from boot to ready
- **LLM call latency**: 1-5s (Claude API + local processing)
- **STT latency**: 0.5-3s (Whisper or hosted)
- **TTS latency**: 0.5-2s per sentence (Sonic/Piper)
- **Memory usage**: ~300-500MB baseline (Python + async loops)

## Next Steps (Phase 0)

- [x] Install Ubuntu Server 26.04 LTS
- [x] Configure BIOS
- [x] Join Tailscale network (Phase 1)
- [x] Set up basic logging
- [x] Python environment (handled automatically by `run.sh`, no manual venv step)
- [ ] Set up systemd unit
- [ ] Disable unattended-upgrades auto-reboot
