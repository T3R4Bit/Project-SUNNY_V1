---
id: sunny-task-system
type: feature
status: active
created: 2026-08-18
tags: [feature, tasks, discord, vault]
---

# Task Management System

Task management with hardcoded logic (no LLM required). **Discord is the intended primary interface** — connected to a live server as of 2026-08-20 (see [[architecture/discord-bot.md]]). Commands are read from a `#chat` channel; the pinned dashboard lives in its own separate, read-only channel. The web chatbot is fully working today and remains the fallback for whenever the Discord bot is down.

Tasks are one of three sibling subsystems that share the same routing entry point, database-per-feature approach, and "no LLM, plain pattern matching" philosophy — see [[architecture/lists.md]] for named checkable lists (groceries, packing, etc.) and [[architecture/alarms-reminders.md]] for time-triggered alarms/reminders that ping Discord when due. They are **not** part of Tasks — a task is never "due at 7am" in the alarm sense. All three route through the same `sunny_code/components/assistant.py`.

Tasks have no priority field (removed 2026-08-24 — it was a plain 1-5 int with no real behavior tied to it beyond dashboard sort order). Category and due date are the two real organizing fields.

## Status

| Piece | Status |
|-------|--------|
| Vault storage + CRUD | Built (`sunny_code/components/tasks_db.py`) — markdown in `sunny-vault/data/state/tasks/`, not SQLite, see [[architecture/vault-storage]] |
| Command parser (natural phrasing, no LLM) | Built (`sunny_code/components/tasks_parser.py`) |
| Task engine (command execution, dashboard formatting) | Built (`sunny_code/components/tasks_engine.py`) |
| REST API | Built (`sunny_code/components/tasks_api.py`) |
| Console chat interface (`/console`) | Built — working fallback interface |
| **Discord bot** | Built and connected (`sunny_code/components/discord_bot.py`) — see [[architecture/discord-bot.md]] |
| Device/source tracking (which interface created a record) | Built (`sunny_code/components/device.py`) — see Device Tracking below |
| Lists (groceries, packing, etc.) | Built, separate subsystem — see [[architecture/lists.md]] |
| Alarms & Reminders | Built, separate subsystem — see [[architecture/alarms-reminders.md]] |
| Obsidian staging integration | Not built — nothing writes to `staging/` yet |

## Overview

- **Categories**: A real, editable list (`sunny_code/components/category_store.py`) — "add category `<name>`"/"remove category `<name>`" from any interface, or `/category add`/`/category remove` in Discord specifically (2026-08-24: natural language added everywhere else, previously Discord-only). General/School/Motorsports ship as defaults; `General` can never be removed (permanent fallback). If a task's category isn't stated or clearly implied by phrasing, Sunny asks which one instead of silently defaulting.
- **Storage**: Markdown in the Obsidian vault (`sunny-vault/data/state/tasks/`, one file per task) — see [[architecture/vault-storage]]. Finishing or deleting a task **archives** its file (`sunny-vault/data/archive/finished/` or `archive/deleted/`) rather than removing it — no task data is ever actually lost, and lifetime stats still count what finished.
- **Interface today**: Console chat, Discord text, and Discord voice (Sunny's persistent voice presence — see [[architecture/voice-join]]) — all identical behavior through the same `handle_message()`
- **Logic**: Deterministic, no LLM calls

## Data Model

```python
Task {
  id: str # short UUID, first 8 hex chars — internal only, never
                              # shown in chat/Discord text; reference tasks by title instead
  title: str
  description: str # optional
  tag: str # any non-empty string — free-form category, not an enum
  status: str # open | in_progress | done
  created_at: datetime
  updated_at: datetime
  due_date: datetime # optional
}
```

## How It Works Today (Console Chat)

Open `/console` (or `/`, or the old `/chatbot`, both of which redirect there) and just talk to it naturally — "add buy milk to my tasks", "show my tasks", "mark a1b2c3d4 as done". No command prefix required. Type **"help"** (or "commands"/"info", or just hit enter with nothing typed) any time for a capability summary. The chat sends every message to one shared endpoint (`sunny_code/components/assistant.py`'s `handle_message()`, also used by the Discord bot — identical behavior on both interfaces):

```
POST /api/assistant/message?text=<message>
```

**Routing order**: pending follow-up question (if any) → help trigger → [[architecture/lists.md|list command]] → [[architecture/alarms-reminders.md|alarm/reminder command]] → task command (natural phrasing or legacy `!task`) → morning/evening briefing → briefing Q&A fallback. Lists and alarms/reminders are checked *before* tasks on purpose: their trigger phrases require a specific keyword ("list"/"alarm"/"reminder"), while tasks' bare `delete <x>`/`mark <x> as done` patterns are deliberately broad and would otherwise swallow "delete my reminder to call Mom" or "remove milk from my list" before the more specific parser ever got a look.

## Device Tracking

Every record created anywhere (a task, a list item, an alarm) gets tagged with `source: web | discord | api`, derived from the `session_id` passed into `handle_message()` (`sunny_code/components/device.py`'s `device_from_session()`):

- Web chatbot sessions: `web:<random-id-persisted-in-browser-localStorage>` → `source = "web"`
- Discord messages: `discord:<channel_id>:<user_id>` → `source = "discord"`
- Anything else (direct REST API calls with no session): `source = "api"`

This exists so future features (e.g. "show me what I created from my phone today") have real data to query against — nothing currently filters or displays by `source` yet, it's just recorded on every task/list-item file and every row in `scheduled.db`.

## REST API

```
POST /api/tasks/command?cmd=... Execute a task command directly (natural phrasing or legacy !task syntax)
GET /api/tasks/list List tasks (filter by status/tag query params)
GET /api/tasks/open All open tasks
GET /api/tasks/done All completed tasks
GET /api/tasks/in-progress All in-progress tasks
GET /api/tasks/due-soon?days=7 Tasks due within N days
GET /api/tasks/stats Counts by status + open tasks by tag
GET /api/tasks/dashboard Full formatted dashboard (same text the Discord embed will eventually show)
GET /api/tasks/{task_id} Single task by ID
```

## Command Syntax

Natural phrasing is the primary, documented way to talk to the task system — no `!` prefix needed. Same phrasing works whether it's typed into the web chatbot today or the Discord bot once that exists.

### View Tasks
```
show my tasks # Show all open tasks, grouped by tag
my tasks
tasks
what are my tasks
list tasks --tag School # Trailing filters still work: --tag, --status,
                             # --due-soon, --all, --done, --open, --in-progress
```

### Create Task
```
add <title>
add <title> to my tasks
add task <title>
create task <title>
new task <title>
make a task <title>
remind me to <title>

Trailing flags still work if you want precision:
add <title> to my tasks --tag <tag> --due <date> --describe "<text>"

Examples:
add finish physics homework to my tasks --tag School --due 2026-08-20
add engine rebuild plan to my tasks --tag Motorsports
add walk the dog to my tasks --tag Pets
remind me to learn Rust
```
If a category isn't stated or clearly implied by the phrasing, Sunny asks (offering the current category list) instead of silently defaulting. Categories are still free-form storage underneath — the managed list (see Overview above) is just what gets offered/asked about, not a hard allowlist, so typing something outside it (via `--tag` or as a reply to the "which category?" prompt) still works. Inline phrasing also works without `--tag` at all: "add walk the dog to my school tasks", "put buy milk on my tasks", "check off my chores task" are all recognized (broadened 2026-08-23).

### Update Task
"Done" has a natural shortcut that takes an ID **or a title** — marking a task done archives it immediately (`archive/finished/`), the same as Delete below does for `archive/deleted/`, so it drops out of the active dashboard the instant it's finished:
```
mark <id-or-title> as done
complete <id-or-title>
finish <id-or-title>

Examples:
mark ff055559 as done
mark make pizza as done
complete make pizza
```
Other field updates (tag, title, description, due date) still use the terser `!task <id> <field> <value>` form:
```
!task <id> tag <tag>
!task <id> title <new title>
!task <id> describe <description>
!task <id> due <date>

Examples:
!task a1b2c3d4 tag "Project Ideas"
```

### Delete Task
Takes an ID **or a title**. This archives the task's file (`sunny-vault/data/archive/deleted/`) rather than erasing it — the data isn't gone, it's just out of the active list:
```
delete <id-or-title>
remove <id-or-title>
remove <id-or-title> from my tasks

Examples:
delete ff055559
delete make pizza
```
Lifetime stats still count archived tasks; only the active dashboard excludes them.

### Referencing a Task by Title

`mark`/`complete`/`finish`/`delete`/`remove` all accept a title — no ID needed, and none is ever shown in chat/Discord text (see Response Format below). Filler phrasing like "finish task make pizza" also works (the leading "task"/"the task" gets stripped before lookup). Resolution order in `TaskEngine._resolve_task_id()`:
1. Exact ID match (only reachable via the legacy `!task <id> ...` syntax, since the ID is never surfaced to type back)
2. Exact title match (case-insensitive)
3. Substring title match, only if exactly one task matches
4. If nothing matched and the identifier starts with "task"/"the task"/"my task", strip that prefix and retry steps 2-3 once

If a title matches more than one task at the same step, it says so instead of guessing — and asks you to make the titles distinct rather than falling back to an ID:
```
You have 2 tasks titled "clean the garage" — rename one so they're not identical, then try again
```
No fuzzy matching or LLM involved — just case-insensitive string comparison against whatever's in the vault (`sunny-vault/data/state/tasks/`).

### Legacy `!task` / `!tasks` Syntax
The old Discord-style syntax (`!task add "Title" --tag School`, `!tasks --tag School`, `!task <id> delete`) still works — the parser tries it first — but it's no longer required or shown in the UI. Existing scripts/tests that use it keep working unchanged.

## Discord Dashboard (Built and Live)

Since 2026-08-23, the dashboard is a real Discord **embed** (`discord_bot.py`'s `build_dashboard_embed()`), not plain text — one field per active category, plus a **Projects** field listing whatever real project folders exist under `sunny-vault/data/projects/` (see the Project Wizard below). It lives in its own dedicated, read-only channel, separate from the `#chat` channel commands are read from.

Refreshes automatically every 5 minutes, plus an on-demand reaction to update instantly. See [[architecture/discord-bot.md]] for setup, and [[../phases.md]] "Discord Activity Log" for the broader (not yet built) multi-channel activity-log idea this is scoped out of.

The console chat stays available as the fallback interface for whenever the Discord bot is down or unreachable.

## Project Wizard

Say "new project" (or a close variant) and Sunny walks through three quick questions (name, description, sections — or "you decide" to let Claude choose), recaps them, and asks a real yes/no before building anything — a firm "no" ends the conversation with zero LLM calls; "yes" hands off to one `ask_claude(purpose="project_scaffold")` call that drafts a real multi-file folder under `sunny-vault/data/projects/<name>/`, always at least an overview file plus two or more topic files, never a single-file stub. Built in `sunny_code/components/project_engine.py`, wizard state lives in `assistant.py`'s pending-follow-up mechanism (same TTL/cancel pattern as the task-title/task-category prompts). See `sunny-vault/docs/instructions/project-scaffold.md` for the system prompt.

## Storage Schema

### Vault markdown (`sunny-vault/data/state/tasks/<slug>.md`)

One file per task, filename slugified from the title at creation (doesn't rename if the title changes later). Full design, concurrency reasoning, and migration details: [[architecture/vault-storage]].

```yaml
---
id: a1b2c3d4
tag: School # free-form category, any non-empty string
status: open # open | in_progress | done
due_date: 2026-08-20 # omitted from frontmatter entirely if unset
source: web
created_at: 2026-08-19T14:30:00.482113
updated_at: 2026-08-19T14:30:00.482113
---
# Finish physics homework

Complete problems 1-20 from chapter 5.
```

Categories are unrestricted — the 4 shipped defaults are just defaults with dedicated icons (`TaskEngine._CATEGORY_ICONS`), anything else gets a generic in the dashboard. (This project previously stored tasks in SQLite with a `CHECK(tag IN (...))` constraint against a fixed 4-category list, later removed — that history no longer applies now that storage is schema-flexible markdown.)

## Command Parsing (No LLM)

All command parsing is hardcoded regex/string matching, in `tasks_parser.py` — natural phrasing is tried first, then the legacy `!task` syntax as a fallback:

```python
# Natural phrasing (primary)
NATURAL_ADD_TRIGGERS = [
    r'^add\s+(.+?)\s+to\s+(?:my\s+)?tasks?$', # "add X to my tasks"
    r'^add\s+task[:\s]+(.+)$', # "add task X"
    r'^(?:create|new)\s+task[:\s]+(.+)$', # "create task X" / "new task X"
    r'^make\s+(?:a\s+|me\s+a\s+)?task[:\s]*(.*)$', # "make a task X" (empty title → helpful error)
    r'^remind\s+me\s+to\s+(.+)$', # "remind me to X"
    r'^add\s+(.+)$', # bare "add X" catch-all, tried last
]
NATURAL_LIST_PATTERN # "show/list/see/view (my) tasks", "my tasks", "tasks", "what are my tasks"
NATURAL_DONE_PATTERN # "mark <id-or-title> as done", "complete <id-or-title>", "finish <id-or-title>"
NATURAL_DELETE_PATTERN # "delete <id-or-title>", "remove <id-or-title> (from my tasks)"
# TaskEngine._resolve_task_id() then strips a leading "task"/"the task" filler and
# tries title matching if the raw identifier isn't a real ID — see "Referencing a
# Task by Title" above.

# Legacy !task syntax (still works, no longer required)
TASK_ADD_PATTERN = r'!task\s+add\s+"([^"]+)"(.*)' # title in quotes, flags follow
TASK_UPDATE_PATTERN = r'!task\s+(\w+)\s+(\w+)\s+(.*)' # id, field, value
TASK_DELETE_PATTERN = r'!task\s+(\w+)\s+delete'
TASK_LIST_PATTERN = r'!tasks?(?:\s+(.*))?'

# Shared flag patterns (either syntax can carry --tag/--due/--describe)
TAG_PATTERN = r'--tag\s+(["\']?)([^"\'\s]+)\1'
DUE_PATTERN = r'--due\s+([\d\-]+)' # YYYY-MM-DD
DESCRIPTION_PATTERN = r'--describe\s+(["\']?)(.+?)\1(?:\s--|$)'

# Parse logic: regex → extract fields → validate → execute
# No semantic understanding needed, just pattern matching
```

## Response Format

No IDs shown anywhere — every response references tasks by title. The ID still exists (it's the DB primary key, needed internally for updates/deletes), but the chat/Discord text never surfaces it. See "Referencing a Task by Title" above for how ambiguous titles are handled without one.

### Success
```
Task created: Finish physics homework
Category: School
Due: 2026-08-20
```
```
Finished "Finish physics homework" — archived
```
```
Deleted "Finish physics homework"
```
Both archive the file rather than removing it (see Update Task / Delete Task above).

### Error
```
Category cannot be empty
```

## Integration Points

### With Briefing Engine
The briefing engine already queries the vault for its "Tasks" section (see [[briefing-engine]]) — this part is built and working, just running against whatever's actually in `sunny-vault/data/state/tasks/` rather than mock task data.

### With Obsidian Staging (Still Not Built — Different From Vault Storage Above)
Plan: new tasks get logged to `staging/task-<date>.md` per the vault's staging convention (see [[../DESIGN.md#Obsidian Vault Structure|DESIGN.md]]) as a transient, Notion-export-bound summary. Nothing writes there yet. **Don't confuse this with `sunny-vault/data/state/tasks/`** (above) — that's tasks' live, permanent storage (built, in use today); `staging/` would be a separate, temporary copy for pushing to Notion, a different concept that's still just a plan.

### Cost Impact
- **Zero LLM tokens** — all hardcoded, confirmed in code (no `anthropic` calls anywhere in the task system)
- **Minimal API calls** — HTTP requests only, no external API for storage
- **Storage**: one small markdown file per task in the vault

## Future Enhancements

- Recurring tasks ("every Monday")
- Task dependencies ("blocked by X")
- Time tracking ("2 hours on this task")
- Export to Notion (on-demand)
- Mobile app integration (future)

## Implementation Checklist

- [x] Vault markdown storage (`sunny-vault/data/state/tasks/`) — see [[architecture/vault-storage]]
- [x] Command parser (regex-based)
- [x] Task CRUD operations
- [x] Dashboard formatter (`format_dashboard()`)
- [x] REST API + web chatbot interface
- [x] Title-based resolution for mark/complete/finish/delete (with filler-word handling)
- [x] `help`/`commands`/`info` response in the chatbot
- [x] No task IDs in chat/Discord text — every response references tasks by title
- [x] Free-form categories — no fixed tag list, storage is schema-flexible markdown
- [x] Dashboard groups by whatever categories actually exist (known ones first, custom ones alphabetically after)
- [x] Conversational follow-up — "make a new task" with no title asks "what should I call it?" instead of erroring, then creates it from the next reply (per-session state in `sunny_code/components/assistant.py`, 5-minute expiry, "cancel" to back out)
- [x] Discord bot code (`sunny_code/components/discord_bot.py`) + config fields (token/channel env vars)
- [x] Discord dashboard builder (reuses `format_dashboard()`)
- [x] 5-minute refresh loop
- [x] reaction for on-demand refresh
- [x] Pin dashboard message to the configured channel
- [x] Startup summary of missing API keys, logged + posted to Discord
- [x] Device/source tracking (`web`/`discord`/`api`) on every created task — see Device Tracking above
- [x] Lists and Alarms/Reminders built as separate sibling subsystems, routed through the same `handle_message()` — see [[architecture/lists.md]] and [[architecture/alarms-reminders.md]] for their own checklists
- [x] Real Discord bot token connected, live on a real server (2026-08-20)
- [x] Migrated storage off SQLite onto vault-markdown, one file per task (2026-08-19/20) — see [[architecture/vault-storage]]
- [x] Real, editable category list — natural language ("add category X"/"remove category X") from any interface, or `/category add`/`/category remove` in Discord specifically, with a category asked for when not stated/implied instead of silently defaulting
- [x] Priority removed entirely (2026-08-24) — no field, no `--priority` flag, no dashboard `[P#]` display; existing task files with an old `priority:` frontmatter line just have it ignored, nothing rewrites them
- [x] Archive-not-delete — finishing or deleting a task moves its file to `archive/finished/`/`archive/deleted/` instead of erasing it
- [x] Discord task dashboard is a real live-updating embed with a Projects field, not plain text
- [x] Project wizard ("new project") — see Project Wizard above
- [x] Broadened natural-phrasing coverage for add/complete/delete (inline categories, "put X on my tasks", "check off my X task")
- [ ] Logging to Obsidian *staging* (transient, Notion-export-bound — distinct from the vault storage above, which is already built)
- [ ] Slash command variants (optional)
