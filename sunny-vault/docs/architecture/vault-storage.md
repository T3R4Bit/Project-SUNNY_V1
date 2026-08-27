---
id: sunny-vault-storage
type: feature
status: active
created: 2026-08-20
tags: [feature, tasks, lists, vault, storage]
---

# Vault Storage (Tasks & Lists)

Tasks and Lists live as markdown files in the Obsidian vault (`sunny-vault/data/state/tasks/`, `sunny-vault/data/state/lists/`) — not SQLite. This is a deliberate, scoped migration: Alarms/Reminders/Scheduled items are **unaffected** and stay SQLite (see [[alarms-reminders]]) — they get a read-only markdown mirror instead, not a storage change.

## Status

Built — `sunny_code/components/tasks_db.py`, `sunny_code/components/lists_db.py`, `sunny_code/components/vault_io.py` (shared atomic-write/frontmatter helpers), `migrate_to_vault.py` (one-time migration from the old `tasks.db`/`lists.db`). Every public method on `TaskDB`/`ListDB` kept its exact name/signature/return shape from the SQLite version, so `tasks_engine.py`, `lists_engine.py`, `tasks_api.py`, `discord_bot.py`, and every interface built on top needed zero changes — only the five places that *construct* a `TaskDB`/`ListDB` (`main.py`, `chat.py`, `briefing.py`, plus two test files) needed their path argument updated from a `.db` file to a vault directory.

## Why

The previous design (SQLite) worked fine but was invisible — task/list data only ever existed inside opaque `.db` files, nothing you could open in Obsidian and browse. This migration makes that data a first-class part of the vault instead.

## Sunny-Only Writer (Not Two-Way Sync)

This is the single decision that makes the whole migration tractable: **Sunny reads and writes these files; you can view them in Obsidian, but they're not meant to be hand-edited.** No file-watching, no conflict resolution between a human edit and a concurrent Sunny write — that entire class of problem doesn't exist because it was scoped out up front, not solved.

If you do hand-edit a file anyway: every write does a read-modify-write (loads the current file, changes only the intended field, rewrites), so a stray edit *may* survive incidentally as an emergent property of that — but it's not a supported guarantee, and there's no mechanism watching for or validating hand-edits.

## Layout & Format

**Tasks** — one file per task, `sunny-vault/data/state/tasks/<slug>.md`, filename from the task's title (slugified) at creation time. Doesn't rename if the title changes later (avoids breaking any Obsidian backlink/graph position you've built to it) — the frontmatter `id` is the real stable identifier, the filename is just for browsing.

```yaml
---
id: a1b2c3d4
tag: School
status: open
due_date: 2026-08-20
source: web
created_at: 2026-08-19T14:30:00.482113
updated_at: 2026-08-19T14:30:00.482113
---
# Finish physics homework

Complete problems 1-20 from chapter 5.
```

No `priority` field — removed 2026-08-24 (a plain 1-5 int with no real behavior tied to it beyond dashboard sort order). A task file written before the removal that still has a `priority:` line just has it ignored on read/write; nothing rewrites old files to strip it.

Frontmatter field names deliberately match the dict keys `TaskDB` already returns (`created_at`, not `created`) — no translation layer between "what's on disk" and "what `get_task()` returns," since callers like `briefing.py` depend on those exact keys. A field with no value (`due_date`, `source`, `description`) is omitted from frontmatter entirely rather than written as `null` — cleaner for Dataview, and every read guarantees the key is still present in the returned dict with a `None` default (matching what SQLite always did with a NULL column) so callers using bracket access don't get a `KeyError`.

**Lists** — one file per list, `sunny-vault/data/state/lists/<slug>.md`, using Obsidian's native checkbox syntax for items:

```yaml
---
id: c3d4e5f6
name: Groceries
source: discord
created_at: 2026-08-19T09:12:03.114552
---
# Groceries

- [ ] milk
- [x] bread
- [ ] eggs
```

List-name slugs have zero collision risk (names are already enforced case-insensitive-unique — see `get_or_create_list`), unlike task-title slugs, which get a `-2`/`-3` suffix on a genuine duplicate title. Item identity/order is derived from file line position at read time, not stored — safe because the only place an item id is ever used is `find_item()` immediately followed by `remove_item()`/`check_item()` within the same call, never persisted across separate requests. Per-item `source`/`created_at` (tracked in the old SQLite schema) were dropped — nothing has ever read either field.

## Concurrency

No explicit locking. Two layers of protection instead:

1. **Within one process** (the web server + Discord bot run in the same asyncio event loop via `asyncio.gather()`): every `TaskDB`/`ListDB` method is a plain sync function with no `await` inside it, so Python's cooperative single-threaded scheduling guarantees one call can never be interrupted mid-write by another coroutine. This relies on every route handler touching these classes staying `async def` — if one ever became a plain `def` (Starlette would dispatch it to a worker thread) or real multithreading got introduced, this guarantee would break.
2. **Across processes** (`chat.py` running as a separate OS process at the same time as the main server — the only realistic cross-process scenario): every write is atomic (`vault_io.atomic_write_text` — temp file + `os.replace()`, not `os.rename()`, which is not an atomic overwrite on Windows). A genuine simultaneous write means "last writer wins for that file," never corruption or a torn read.

Verified directly: ran `chat.py` and the web server simultaneously firing rapid, overlapping task-create commands from both processes at once — every resulting file parsed cleanly, zero corruption, collision-suffix logic handled the overlapping titles correctly.

## Migration

`migrate_to_vault.py` (repo root, kept in version control) reads the old `tasks.db`/`lists.db` directly via raw `sqlite3` and calls `TaskDB.import_task()` / `ListDB.import_list()` — migration-only methods that write a dict verbatim, preserving the original `id`/`status`/timestamps exactly, unlike `create_task()` which always mints fresh ones. Idempotent by `id` (re-running overwrites the same file rather than duplicating — this needed an explicit fix during implementation, since the naive version asked `_unique_slug()` for a fresh slug every time and got a `-2` suffix on the second run). Never touches or deletes the original `.db` files. Supports `--dry-run`.

## What's Not Tracked in Git

`sunny-vault/data/state/tasks/` and `sunny-vault/data/state/lists/` are gitignored — same privacy posture `*.db` already had, personal task/list content has never left your machines and that doesn't change just because the file format did.

## Dependencies

- `PyYAML` — frontmatter parsing/serialization (`sunny_code/components/vault_io.py`)
- [[../TASK_SYSTEM.md]], [[lists]] — the two subsystems this covers
- [[alarms-reminders]] — explicitly *not* covered; has its own read-only mirror instead
- [[../DESIGN.md]] — the vault's broader file-lifecycle conventions this follows (atomic writes, one-file-per-item)
