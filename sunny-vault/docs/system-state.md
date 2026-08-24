---
id: sunny-state
type: state
status: active
created: 2026-08-18
tags: [state, runtime, config]
---

# System State

Runtime state tracking for Sunny. Updated by Sunny core process during execution.

## Sleep/Wake State

```yaml
current_state: awake|sleeping|in_bed
last_updated: 2026-08-18T14:30:00Z
```

**Transitions:**
- `awake` → `in_bed` (when user says "good night")
- `in_bed` → `sleeping` (after 30 min without activity)
- `sleeping` → `awake` (when user says "good morning" or alarm fires)

**Effects:**
- When `sleeping`: Incoming calls suppressed unless marked urgent
- When `in_bed`: Only calendar alerts, suppress non-critical Discord
- When `awake`: Full notification activity

---

## Token Counters (Daily Reset at at 4am)

```yaml
tokens:
  claude:
    haiku:
      prompt: 12500
      completion: 3400
      cost: $0.27
    sonnet:
      prompt: 0
      completion: 0
      cost: $0.00
    total_cost: $0.27
  sonic:
    characters: 14200
    cost: $0.12
  total_today: $0.39
  budget_remaining: $19.61
```

**Updated by**: Token circuit breaker during/after each LLM call
**Purpose**: Dashboard display, alarm if approaching daily limit

---

## API Heartbeat Timestamps

```yaml
last_success:
  claude_api: 2026-08-18T14:29:15Z
  sonic_api: 2026-08-18T14:28:50Z
  twilio: 2026-08-18T13:45:22Z
  discord_bot: 2026-08-18T14:30:01Z
  tailscale: 2026-08-18T14:30:00Z
  calendar: 2026-08-18T06:15:33Z
  weather: 2026-08-18T06:15:10Z
  traffic: 2026-08-18T08:15:22Z
```

**Updated by**: Each service after successful call
**Purpose**: Health dashboard, identify which services are down
**Note**: Timestamps more useful than green/red dots (e.g., "weather 8 hours stale" is diagnostic)

---

## Notion Sync Cursor

```yaml
notion_sync:
  last_sync: 2026-08-18T14:25:00Z
  next_sync: 2026-08-18T14:30:00Z
  items_synced_today: 7
  items_pending: 0
  last_error: null
```

**Used by**: Sync sweeper to track progress and avoid re-syncing
**Purpose**: Prevent duplicate pushes, know when next batch will run

---

## Circuit Breaker State

```yaml
circuit_breaker:
  active: false
  last_trigger: null
  threshold_tokens: 100000
  current_rate: 2400  # tokens/hour
  estimated_overage: false
```

**Active**: `true` if current task exceeded token threshold and paused
**Purpose**: Prevent runaway token spend, ask user to continue or halt

---

## File Format

This file is updated atomically:
1. Read current state
2. Update fields
3. Write to `state.json` (machine-readable)
4. Also write to `state.md` (human-readable, this file)

**Never append** to this file. Always rewrite complete state. This prevents partial-write corruption if Sunny crashes mid-write.

---

## Obsidian Integration

Dataview plugin reads this file's YAML and renders a live dashboard:
- Token spend sparkline
- API health status
- System uptime
- Next briefing time

No Sunny code needed — pure Obsidian automation.
