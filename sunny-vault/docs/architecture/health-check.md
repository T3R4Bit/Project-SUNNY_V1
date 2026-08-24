---
id: sunny-health-check
type: feature
status: active
created: 2026-08-20
tags: [llm, claude, discord, maintenance, scheduling]
---

# Weekly System Health Check

A once-a-week, LLM-written report on how Sunny's been doing: recurring errors, requests that keep getting refused or forced to an LLM instead of a hardcoded handler, API keys about to expire, and (when there's something real to say) a suggestion for cutting usage further. Fires every Sunday at 4am on its own — no manual trigger needed. Straight from BACKLOG.md's own wording: tell the user to check it, not what it is, in the morning briefing.

## Status

✅ Built — `sunny_code/components/health_check.py`, scheduled from `sunny_code/main.py`, posted via Discord when configured, surfaced in the morning briefing and through the "health check" chat phrase.

## How It Works

1. **Trigger** — a standalone `discord.ext.tasks.loop(time=datetime.time(hour=4, tzinfo=ZoneInfo(LOCAL_TIMEZONE)))` in `main.py`, started unconditionally from the FastAPI lifespan hook (same place and same reason as [[vault-storage|the vault mirror wiring]] — this has to run whether or not Discord is configured). `time=` fires **daily**; there's no native day-of-week filter, so the callback checks `datetime.now(tz).weekday() == 6` (Sunday) and no-ops the other six mornings.
2. **Gather** — `_build_summary()` assembles a compact, pre-counted text block, deliberately not raw log dumps (this is where the token-minimization goal actually bites):
   - `ERROR` line count from the current `logs/sunny.log`.
   - Unfulfilled-request counts by category, from `sunny-vault/log/requests.md`, last 7 days.
   - LLM call counts by purpose/status, from `sunny-vault/log/llm-usage.md` (see [[llm-integration]]'s call catalog), last 7 days — this is the "gets forced to an LLM" signal BACKLOG.md asked for.
   - Keys expiring within 7 days, via `key_status.expiring_within(7)`.
3. **Write it up** — `ask_claude(purpose="weekly_health_check", model="haiku", prompt=<summary>)`. The system prompt auto-loads from `sunny-vault/instructions/weekly-health-check.md` (see [[llm-instructions]]) — Haiku, matching this project's default tier and "keep usage low."
4. **Record** — the report (or, if Claude's unreachable, the raw summary with a note saying so) gets appended to `sunny-vault/log/health-checks.md`, and `sunny-vault/state/health-check.md` flips to `status: unacknowledged`.
5. **Notify** — posted to its own Discord channel (`DISCORD_HEALTH_CHANNEL_ID`, falling back to the chat channel if unset) if the bot is configured and connected (`client.post_to_health`, no-ops otherwise); always logged locally regardless. The next "morning"/"evening" briefing gets one extra line (`health_check.pending_notice()`) — a nudge only, never the report content itself, matching the "tells me to check it, not what it is" requirement.
6. **Acknowledge** — saying "health check" or "health report" (web console, terminal, or Discord) returns `health_check.latest_report()` and flips the marker back to acknowledged, so the briefing nudge stops appearing.

The marker persists across days on purpose, not a same-day-only check: morning briefings in this app are manual-trigger-only, so if "morning" doesn't get said on the Sunday the check ran, a same-day check would silently lose the reminder forever.

## Known Limitations

- **Error window isn't precise.** `_count_log_errors()` scans the current, unrotated `sunny.log` only — not a strict 7-day window. Fine at this log's volume (10MB × 10 backups, rotates rarely); revisit with real timestamp filtering if that stops being true.
- **Timezone is bound at startup.** `ZoneInfo(LOCAL_TIMEZONE)` is read once when `main.py` builds the loop — changing `LOCAL_TIMEZONE` needs a restart, unlike most settings in this app.
- **The Sunday-4am firing itself can't be meaningfully unit-tested.** Verified in isolation (summary building, the Claude call, the log/marker/acknowledge cycle — see Verification below) and via a full lifespan start/stop smoke test, but the actual weekly trigger needs a supervised manual check on the real box: temporarily point `time=` a few minutes ahead, confirm one fire, confirm the weekday guard no-ops on non-Sundays.
- **Requires `tzdata` on Windows.** `zoneinfo.ZoneInfo` has no IANA database on Windows by default (`ZoneInfoNotFoundError`) — a no-op on the Ubuntu production box, but `tzdata>=2024.1` is in `requirements.txt` so local dev on Windows doesn't crash either.

## Files

- `sunny_code/components/health_check.py` — summary building, the Claude call, log/marker read-write, `pending_notice()`/`latest_report()`
- `sunny_code/main.py` — `_create_health_check_loop()`, started/cancelled from the FastAPI lifespan hook, guarded by `self._health_check_started`
- `sunny_code/components/discord_bot.py` — `client.post_to_health`, exposed as an attribute so `main.py` doesn't need to know Discord internals
- `sunny_code/components/briefing.py` — the morning-briefing nudge line
- `sunny_code/components/assistant.py` — the "health check"/"health report" chat phrase
- `sunny_code/components/key_status.py` — `expiring_within(days)`, backed by four optional `*_EXPIRES` settings
- `sunny-vault/instructions/weekly-health-check.md` — the system prompt
- `sunny-vault/log/health-checks.md` — append-only report log
- `sunny-vault/state/health-check.md` — acknowledged/unacknowledged marker

## Dependencies

- [[llm-integration]] — uses `ask_claude()`, and this is the first real consumer of the call catalog it logs
- [[llm-instructions]] — the system prompt this purpose loads
- [[discord-bot]] — optional posting destination
- [[vault-storage]] — `vault_io` helpers for the marker file

## Implementation Checklist

- [x] `key_status.expiring_within(days)` + four optional `*_EXPIRES` settings
- [x] `health_check.py` — summary, Claude call, log append, marker write/read
- [x] Standalone Sunday-4am loop in `main.py`, independent of Discord's lifecycle
- [x] `discord_bot.py` — `post_to_health`, its own `DISCORD_HEALTH_CHANNEL_ID`, ready-guarded
- [x] Morning briefing nudge (`pending_notice()`)
- [x] "health check" chat phrase (`latest_report()`, flips the marker)
- [ ] Supervised manual smoke test on the real box (temporarily move `time=` a few minutes ahead) before trusting the unattended Sunday schedule
