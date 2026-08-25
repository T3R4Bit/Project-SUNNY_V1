---
id: sunny-log-index
type: reference
status: active
created: 2026-08-18
tags: [logging, activity, audit]
---

# Activity Log

Permanent, append-only mirror of Discord activity and all Sunny actions.

## Structure

```
log/
├── 2026/
│   └── 08/
│       ├── 2026-08-17.md
│       ├── 2026-08-18.md
│       └── ...
└── README.md  (this file)
```

**Why nested folders?** Obsidian's indexer degrades past ~10,000 files in a single folder. Nesting by year/month keeps the vault performant even after years of logging.

## File Format

One file per day, named `YYYY-MM-DD.md`. Append-only.

Each entry is a single line or short block with timestamp:

```
**2026-08-18T14:30:15Z** [BRIEFING] Morning briefing delivered (weather, calendar, tasks)
**2026-08-18T14:35:42Z** [TASK] Task abc123 marked done: "Finish physics homework"
**2026-08-18T14:45:00Z** [EMAIL] Email triage: 12 new, 2 urgent, 1 action item
**2026-08-18T15:00:00Z** [PHONE] Incoming call from +1-555-0123, ID in allowlist, connected
**2026-08-18T15:05:30Z** [PHONE] "Remind me to call Sarah tomorrow" → task created
**2026-08-18T15:06:00Z** [PHONE] Call disconnected, 5m 30s duration
**2026-08-18T16:30:00Z** [STATE] Sleep mode activated ("good night")
```

## Content Sources

This log mirrors exactly what's being posted to Discord channels:

- `#briefings` → `[BRIEFING]` entries
- `#task-updates` → `[TASK]` entries
- `#email-actions` → `[EMAIL]` entries
- `#phone-log` → `[PHONE]` entries
- `#state-changes` → `[STATE]` entries
- `#warnings` → `[WARNING]` entries
- etc.

## Atomic Writes

```python
# Write pattern
import os
with open("2026-08-18.md.tmp", "a") as f:
    f.write(new_entry + "\n")
os.rename("2026-08-18.md.tmp", "2026-08-18.md")  # atomic on Linux/Windows
```

Writing to `.tmp` first, then atomic `rename()`, prevents corruption if Sunny crashes mid-write. The file either doesn't exist or is complete.

## Querying

Use Obsidian's search:
- `[PHONE]` to find all phone logs
- `[WARNING]` to find all warnings from past month
- `urgent` to find entries marked urgent
- Date range searches to find activity in a specific week

## Retention

Logs are kept indefinitely. No pruning. This is your permanent audit trail.

**Storage estimate**: ~10-50KB per day depending on activity. At 1GB for 20 years of storage, not a significant constraint.

## Other Log Files

Flat, single-file logs also live directly in `log/` — simpler append-only files, not the nested per-day design above (that design is for the Discord activity mirror, not yet built as described; these predate/sit alongside it):

- `requests.md` — requests Sunny couldn't fulfill with real data (`request_log.py`)
- `rules-engine.md` — one line per fired Layer 2 rule (hardcoded, deterministic automation — vault note changed, calendar event changed), appended by `rules_engine.py`'s scheduled `evaluate()` loop.
- `llm-usage.md` — a record of **every** `ask_claude()` attempt, not just successes — status, prompt, and (on success) response — see `llm_client.log_llm_call()` and [[../docs/architecture/llm-readiness]].
- `health-checks.md` — the weekly Sunday-4am system health report, appended by `health_check.py` — see [[../docs/architecture/health-check]].

## Discord Bot Sync

The Sunny Discord bot posts every action, which is then mirrored here for local backup. This is not a source of truth — Discord is the live channel, this vault is the backup.

If Discord ever deletes the channel, this log survives. If you're without internet and Sunny is still running locally, this log still grows (Discord posts are queued/buffered).
