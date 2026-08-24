---
id: sunny-service-orchestration
type: component
status: active
created: 2026-08-24
tags: [orchestration, services, discord, component]
---

# Service Orchestration

Per-service on/off and autostart-on-boot control for Sunny's background loops, plus a global vacation mode. See [[../BACKLOG.md]]'s "Service Orchestration" section for the backlog this closes out.

## Status

| Piece | Status |
|-------|--------|
| Per-service enable/disable while running | Built — `sunny_code/components/service_registry.py` |
| Per-service autostart-on-boot config | Built — same file |
| Vacation mode | Built — same file, `assistant.py` routing |
| `/service`, `/services`, `/vacation` Discord commands | Built — `discord_bot.py` |

## The Six Services

`dashboard_refresh`, `scheduled_check` (alarms/reminders due-check), `usage_refresh`, `health_check`, `morning_prep`, `voice_join`. Fixed, not user-extensible — each name corresponds to a real loop or command gate wired by hand, not an open-ended concept like task categories.

## Storage

`service_registry.json` at the project root — same shape as `category_store.py`: a flat JSON file, `vault_io.atomic_write_text`, live-takes-effect (no restart needed for `enabled`; `autostart` takes effect on the next restart, since there's no manual-start path for a loop that was never started). Two independent booleans per service:

```json
{
  "services": {
    "dashboard_refresh": {"enabled": true, "autostart": true},
    ...
  },
  "vacation_mode": false
}
```

## How Toggling Actually Takes Effect

- **`enabled`**: every loop checks `service_registry.is_enabled(name)` at the very top of its tick body and returns early if off — so a live toggle takes effect within one tick (30s-1hr depending on the loop), not just at the next boot. `discord_bot.py`'s `join_command` checks `is_enabled("voice_join")` directly before starting a session, so `/join` itself is refused immediately when off, not just the background loops.
- **`autostart`**: checked once, at startup, before a loop's `.start()` call. `scheduled_check_loop` is the one exception — it's always started regardless of either `scheduled_check` or `morning_prep`'s autostart flag, since both services share that one loop and gating the whole loop on either flag alone would silently kill the other. The per-tick `enabled` checks inside the loop are what actually control behavior in that case.

## Vacation Mode

A single global flag, not per-service — it doesn't map to one loop. While on: `scheduled_check_loop` skips the morning-prep lookahead block entirely (no `prewarm_morning_briefing()`, no proactive alarm-triggered nudging). It does **not** suppress an explicit "good morning"/"good night" request — those still work normally; vacation mode only stops the *proactive* daily-cycle waiting, matching the original ask ("so my local clock is not waiting every day for goodnight/morning").

Toggle from any interface: "vacation mode on"/"off" (natural language, routed through `assistant.py`, works on console/Discord text/voice/Pi companion alike) or `/vacation on|off` in Discord.

## Discord Commands

- `/services` — one line per service (`name: on/off (autostart/manual)`) plus vacation mode's state.
- `/service <name> enable|disable|autostart_on|autostart_off` — `name` is a fixed dropdown (the six services above), not free text.
- `/vacation on|off` — same as the natural-language phrase.

All three are channel-restricted to the configured chat channel, same as every other slash command in this bot.

## Files

- `sunny_code/components/service_registry.py` — storage, `is_enabled`/`is_autostart`/`set_enabled`/`set_autostart`/`is_vacation_mode`/`set_vacation_mode`/`status_lines`
- `sunny_code/main.py` — health-check loop's `enabled`/`autostart` gating
- `sunny_code/components/discord_bot.py` — the other five loops' gating, `/service`/`/services`/`/vacation`, `voice_join` gating on `/join`
- `sunny_code/components/assistant.py` — vacation-mode natural-language triggers

## Dependencies

- `sunny_code/components/category_store.py` — the storage pattern this follows exactly
- [[discord-bot]] — hosts the three new commands
- [[health-check]] — one of the six gated services

## Implementation Checklist

- [x] Per-service `enabled` flag, checked at the top of every loop tick
- [x] Per-service `autostart` flag, checked once at boot
- [x] `scheduled_check_loop`'s shared-loop exception handled correctly (always starts; `enabled` gates behavior per-service inside)
- [x] Vacation mode — global flag, suppresses proactive morning-prep only, not explicit requests
- [x] `/service`, `/services`, `/vacation` Discord commands
- [x] "vacation mode on/off" natural-language phrasing, cross-interface
- [x] `voice_join` gates `/join` itself, not just a background loop
- [ ] A manual-start path for a service whose `autostart` was off at boot (today, re-enabling autostart only takes effect on the next restart)
