---
id: sunny-alarms-reminders
type: component
status: active
created: 2026-08-19
tags: [alarms, reminders, scheduling, component]
---

# Alarms & Reminders

A separate subsystem from [[../TASK_SYSTEM.md|Tasks]] and [[lists.md|Lists]] — time-triggered items instead of static ones. Same "no LLM, plain pattern matching" philosophy, own database, own parser, own engine. Deterministic time parsing only — no external date library, just bounded regex + stdlib `datetime`.

## Status

| Piece | Status |
|-------|--------|
| SQLite storage (`scheduled.db`) | ✅ Built (`sunny_code/components/scheduled_db.py`) — **unaffected** by the Tasks/Lists move to vault storage, see [[vault-storage]] |
| Read-only vault mirror | ✅ Built (`sunny_code/components/scheduled_vault_mirror.py`) — see below |
| Time/recurrence parsing (no library) | ✅ Built (`sunny_code/components/time_parse.py`) |
| Command parser | ✅ Built (`sunny_code/components/scheduled_parser.py`) |
| Scheduled-item engine | ✅ Built (`sunny_code/components/scheduled_engine.py`) |
| Routed into web chatbot + Discord bot | ✅ Built (both go through `assistant.handle_message`) |
| **Delivery when due** | ✅ Built, but **only fires if the Discord bot is connected** — see Delivery below |
| Real "sounding" (speaker/hardware) | ⏳ Not built — no clock/speaker device exists yet (Phase 3) |

## Important: what "alarm" actually means today

There's no bedside clock hardware yet ([[clock]] is Phase 3, unbuilt). Nothing plays a sound or vibrates anything. What's built:

1. Say "set an alarm for 7am" → a row goes into `scheduled.db` with a `trigger_at` timestamp.
2. Every 30 seconds, if the Discord bot is running, it checks for anything due and **posts a message in the chat channel** (not the read-only dashboard channel — these are conversational pings you might reply to) (`⏰ Alarm: <label>` or `🔔 Reminder: <label>`).
3. If the Discord bot isn't connected (no token configured), alarms and reminders still get created and stored correctly — they just never announce themselves anywhere. Querying them ("what alarms are set") always works regardless of Discord.

This is stated explicitly in the chatbot's `help` text so it's never a surprise. Don't remove that caveat when editing `assistant.py`'s `HELP_TEXT`.

## How It Works

- **Storage**: SQLite (`scheduled.db`), one table `scheduled_items` — `kind` (`alarm`|`reminder`), `label`, `trigger_at`, `recurrence`, `active`, `source`, `created_at`.
- **Time parsing** (`time_parse.py`, fully deterministic):
  - Clock times: `7am`, `7:00 AM`, `6:30pm`, `19:00`
  - Explicit day: `<time> tomorrow`, `<time> today`
  - Explicit date: `on 2026-08-25 at 3pm`
  - Relative: `in 30 minutes`, `in 2 hours`
  - If no explicit date is given and the time has already passed today, it auto-rolls to tomorrow (so "set an alarm for 7am" at 8pm means tomorrow morning, not 11 hours in the past).
- **Recurrence** (`parse_recurrence`): `daily`, `weekdays`, or a specific weekday name (`every Monday`). `next_occurrence()` computes the next `trigger_at` after a recurring item fires.
- **Delivery loop** (`discord_bot.py`, `scheduled_check_loop`, every 30s): queries `scheduled_engine.db.get_due_items(now)`, posts one message per due item, then either reschedules it (if recurring) or deactivates it (one-off). This is the only "on_change"-style engine that doesn't use the `on_change` callback pattern for its main job — the callback exists (`ScheduledEngine.on_change`, mirrors `TaskEngine.on_change`) and now has a real use (see below), but it fires only on create/cancel, not on "due now" (that's a poll loop, not an event).

## Read-Only Vault Mirror

Unlike Tasks and Lists, storage here didn't change — `scheduled.db` stays SQLite, on purpose: the 30-second due-check above needs reliable, automatic background writes (reschedule/deactivate) that don't belong in a hand-browsable vault file. Instead, `sunny_code/components/scheduled_vault_mirror.py` writes a **read-only snapshot** to `sunny-vault/state/alarms-reminders.md` so current alarms/reminders are still visible in Obsidian — this file is never read back in by anything; hand-editing it has zero effect.

Wired as `ScheduledEngine.on_change` in `sunny_code/main.py` (not `discord_bot.py` — this must work whether or not Discord is configured), and also called once directly at startup so the file reflects reality from process start, not just after the first future change.

```markdown
---
id: alarms-reminders-mirror
type: mirror
status: active
updated_at: 2026-08-20T10:00:00
---
# Alarms & Reminders

Read-only snapshot — the real data lives in SQLite (scheduled.db), not here.

## Alarms

- ⏰ Thu Aug 20, 7:00 AM — Alarm (daily)

## Reminders

- 🔔 Tue Aug 25, 3:00 PM — call Mom
```

## Command Syntax

### Creating Alarms
```
set an alarm for 7:00 AM
set an alarm for 8 AM called "Take Medicine"
set a recurring alarm for 7 AM every weekday
set an alarm for 6:30pm tomorrow
```

### Managing Alarms
```
what alarms are set / show my alarms
cancel my 7am alarm                  → matches by time if no custom label
cancel all alarms
```

### Reminders (time-based only — see Known Limitations)
```
remind me to call Mom at 5 PM
remind me to call Mom on 2026-08-25 at 3pm
remind me to call Mom in 30 minutes
what are my reminders
delete my reminder to call Mom
clear all reminders
```

### Not supported (explicit, honest rejection — not silently ignored)
```
remind me to grab an umbrella when I get home     → no location tracking exists;
remind me to call Sarah when I get to the office     the parser detects this phrasing
                                                       and says so instead of pretending
stop / snooze                                       → doesn't map to a "post once to
                                                       Discord" delivery model; not built
```

## Data Model

```python
ScheduledItem {
  id: str
  kind: str            # 'alarm' | 'reminder'
  label: str            # defaults to "Alarm" for unlabeled alarms; the task text for reminders
  trigger_at: datetime
  recurrence: str       # None | 'daily' | 'weekdays' | a weekday name
  active: bool           # False once fired-and-not-recurring, or cancelled
  source: str            # web | discord | api — see Device Tracking below
  created_at: datetime
}
```

## Response Format

No IDs — alarms/reminders are referenced by label or, for the common "unlabeled alarm" case, by the time itself (see Cancelling below).

```
⏰ Alarm "Alarm" set for Wednesday, August 19 at 7:00 AM
```
```
🔔 I'll remind you to call Mom on Tuesday, August 25 at 3:00 PM
```
```
✅ Cancelled alarm "Alarm"
✅ Cancelled 1 alarm(s)
✅ Deleted reminder "call Mom"
```

### Cancelling an unlabeled alarm by time

Most alarms never get a custom `called X` label, so they're all internally named "Alarm" — matching "cancel my 7am alarm" by label text alone would find nothing. `ScheduledEngine._cancel_alarm()` falls back to parsing the identifier as a time expression and matching against each active alarm's `trigger_at` time-of-day when label matching comes up empty.

## Routing Note

`assistant.py` checks the Scheduled parser **before** the Tasks parser, for the same reason as Lists (see [[../TASK_SYSTEM.md]] "Routing order") — otherwise Tasks' broad `delete <x>` pattern would swallow "delete my reminder to call Mom".

## Dependencies

- [[../TASK_SYSTEM.md]] — sibling subsystem, same routing entry point (`assistant.handle_message`)
- [[discord-bot.md]] — the only real delivery mechanism today; the `scheduled_check_loop` lives there, not here
- [[vault-storage]] — the read-only mirror shares its atomic-write helper (`vault_io.py`) with Tasks/Lists, even though `scheduled.db` itself stays SQLite
- `sunny_code/components/device.py` — `device_from_session()`, shared with Tasks/Lists
- [[clock]] — future hardware that would eventually replace "post a Discord message" with an actual sound; not built, Phase 3

## Implementation Checklist

- [x] SQLite schema (`scheduled.db`) — unaffected by the Tasks/Lists vault-storage migration
- [x] Read-only vault mirror (`sunny-vault/state/alarms-reminders.md`), updates on change + once at startup
- [x] Deterministic time-expression parser (clock times, relative, explicit dates, tomorrow/today)
- [x] Recurrence parsing + next-occurrence calculation (daily/weekdays/specific weekday)
- [x] Natural-language command parser (create/query/cancel for both alarms and reminders)
- [x] Honest rejection of location-based reminder phrasing (no location tracking exists)
- [x] Routed into web chatbot and Discord bot via shared `handle_message()`
- [x] Discord 30-second due-item check loop — posts + reschedules/deactivates
- [x] Cancel-by-time fallback for unlabeled alarms
- [x] Device/source tracking
- [x] No IDs in chat/Discord responses
- [ ] Alarm "stop"/"snooze" — doesn't fit the current delivery model, not built
- [ ] Real hardware sounding (Phase 3 clock device)
- [ ] Dedicated REST API — chat/Discord only for now
- [ ] Obsidian staging integration
