---
id: sunny-vault-sync
type: component
status: active
created: 2026-09-23
tags: [sync, syncthing, obsidian, vault, conflicts, component]
---

# Vault sync

Syncthing, across four devices. The interesting part is not the tool — it
is **what is excluded**.

## The audit that changed the plan

The plan of record was to replace Syncthing with self-hosted
obsidian-livesync (CouchDB), on the reasoning that there is no viable
Syncthing client on iOS. Measured on the Lenovo, 2026-09-23:

| Device | Conflicts created |
| --- | --- |
| `T3R4Bit laptop` | 8 |
| `sunshine-m700` (Sunny itself) | 8 |
| `Keaton-PC` | 3 |
| `Keatons-iPad` | **0** |

The iPad is in the folder, unpaused, `sendreceive` — and has **never**
caused a conflict. There is no iPhone in the folder at all. The iOS gap
is real in general and is simply not what was breaking this vault.

**The actual cause is what was being synced:**

| | Size | Share |
| --- | --- | --- |
| `.obsidian/` | 4.6MB | 12 of 19 conflicts |
| `log/` | 4.5MB | 3 more |
| Real notes | **144KB** | **1.4% of the folder** |

Syncthing was hauling 9.8MB of churning machine and app state across four
devices to protect 144KB of notes. **Not one conflict came from a note
edited in two places** — so CouchDB would have prevented zero of them.

`health_check.py:97` and `sensors.py:28` already excluded
`{.obsidian, archive, log, state, instructions}` from what counts as
"knowledge". The classification existed; it was never wired to the sync
boundary.

**Decision: no CouchDB.** Revisit only if conflicts start appearing on
real notes.

## The conflicts themselves

All 19 were checked before deletion rather than assumed. Two findings:

- **A whole class was line endings.** `docs/architecture/discord-bot.md`
  differed by 23281 vs 23051 bytes across exactly **230 lines** — CRLF
  from Windows against LF from the server. One byte per line, zero
  disagreement.
- `data/state/alarms-reminders.md` differed only in its `updated_at`
  timestamp, and its own header says the real data lives in SQLite.

Nothing of Keaton's was lost.

## The ignore rules

Split in two, because `.stignore` is **per-device and never syncs** — so
every rule change had to be retyped on four machines, and the two that
most needed it (laptop, iPad) are the two rarely to hand. They simply
never got it.

| File | Synced? | Contents |
| --- | --- | --- |
| `.stignore-rules` | **yes** | the actual rules |
| `.stignore` | no | one line: `#include .stignore-rules` |

Edit the rules once, every device follows.

**Tradeoff accepted:** a bad edit now propagates everywhere. It is a
short file, and the alternative was four devices silently disagreeing
about what to sync — which is what produced 19 conflict files.

### What is excluded

```
.obsidian                     per-device app state
log                           append-only churn
data/state/*cursor*.json      rewritten every few minutes
data/state/health-check.md
data/state/alarms-reminders.md    SQLite mirror
state                         stale tree from a path migration
*.sync-conflict-*
```

**Kept:** notes, tasks, docs, memory, `personality.md`, KSU, projects.

## Result

| | Before | After |
| --- | --- | --- |
| Synced size | 10 MB | **0.56 MB** |
| Synced files | 146 | **61** |
| Conflicts | 19 | **0** |

## Still open

The **laptop and iPad** have no `.stignore`, so the global index stays
~9.4MB until they get one. They cannot push any of it into the two
devices that now ignore it, so the PC↔server churn is already stopped.

Neither is reachable remotely: the laptop is up on the tailnet but
22/5985/3389 are closed, Syncthing's API is bound to localhost, and 445
rejects credentials. The fix is one line in each device's Syncthing UI →
folder → Ignore Patterns:

```
#include .stignore-rules
```

## The structural rule

No sync tool can cleanly resolve two writers editing one file, so the
situation is avoided rather than resolved:

- **Machine-owned** — tasks, lists, logs, generated summaries. Sunny
  writes, you read.
- **Human-owned** — `personality.md`, `memory/profile.md`,
  `instructions/*.md`, per-project `instructions.md`. You write, **Sunny
  only ever reads.**
- Where Sunny wants to change a human-owned file, it writes to
  `log/suggestions.md` for deliberate merging. Never in place.

That rule is what keeps the personality file and the memory system from
becoming the worst conflict sources in the vault — both are files you and
Sunny would otherwise both want to write.

## See also

- [[vault-storage.md]] — how files are written safely
- [[../ROADMAP-2026-09.md]] — Stage A2
