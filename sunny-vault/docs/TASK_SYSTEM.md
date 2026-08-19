# Task Management System

Task management with hardcoded logic (no LLM required). **Discord is the intended primary interface** — a live bot dashboard you view and command from a `#tasks` channel. The code is built (see [[architecture/discord-bot.md]]) but not yet connected to a real Discord server — that last step needs a bot token and channel ID only you can create. The web chatbot is fully working today and remains the fallback for whenever the Discord bot is down.

## Status

| Piece | Status |
|-------|--------|
| SQLite storage + CRUD | ✅ Built (`sunny_code/components/tasks_db.py`) |
| Command parser (natural phrasing, no LLM) | ✅ Built (`sunny_code/components/tasks_parser.py`) |
| Task engine (command execution, dashboard formatting) | ✅ Built (`sunny_code/components/tasks_engine.py`) |
| REST API | ✅ Built (`sunny_code/components/tasks_api.py`) |
| Web chatbot interface (`/chatbot`) | ✅ Built — working fallback interface |
| **Discord bot** | ✅ Built (`sunny_code/components/discord_bot.py`), ⏳ **not yet connected** — see [[architecture/discord-bot.md]] Setup |
| Obsidian staging integration | ⏳ Not built — nothing writes to `staging/` yet |

Current focus: connect the Discord bot to a real server (bot token + channel ID in `.env`) — see [[architecture/discord-bot.md]].

## Overview

- **Tags**: School, Motorsports, General, Project Ideas
- **Storage**: SQLite database (`tasks.db`)
- **Interface today**: Web chatbot at `/chatbot`, sending commands to a REST API
- **Interface planned**: Discord bot + live dashboard embed (primary, once built)
- **Logic**: Deterministic, no LLM calls

## Data Model

```python
Task {
  id: str                    # short UUID, first 8 hex chars (e.g. "a1b2c3d4")
  title: str
  description: str           # optional
  tag: str                   # School | Motorsports | General | Project Ideas
  status: str                # open | in_progress | done
  priority: int              # 1-5 (1=low, 5=critical)
  created_at: datetime
  updated_at: datetime
  due_date: datetime         # optional
}
```

## How It Works Today (Web Chatbot)

Open `/chatbot` (or `/`, which redirects there) and just talk to it naturally — "add buy milk to my tasks", "show my tasks", "mark a1b2c3d4 as done". No command prefix required. Type **"help"** (or "commands"/"info", or just hit enter with nothing typed) any time for a capability summary. The chatbot sends every message to one endpoint, which checks for "help" first, then tries to parse it as a task command, then falls back to the briefing Q&A engine if it isn't either:

```
POST /api/assistant/message?text=<message>
```

## REST API

```
POST /api/tasks/command?cmd=...   Execute a task command directly (natural phrasing or legacy !task syntax)
GET  /api/tasks/list              List tasks (filter by status/tag/priority query params)
GET  /api/tasks/open              All open tasks
GET  /api/tasks/done              All completed tasks
GET  /api/tasks/in-progress       All in-progress tasks
GET  /api/tasks/due-soon?days=7   Tasks due within N days
GET  /api/tasks/high-priority?min_priority=4
GET  /api/tasks/stats             Counts by status + open tasks by tag
GET  /api/tasks/dashboard         Full formatted dashboard (same text the Discord embed will eventually show)
GET  /api/tasks/{task_id}         Single task by ID
```

## Command Syntax

Natural phrasing is the primary, documented way to talk to the task system — no `!` prefix needed. Same phrasing works whether it's typed into the web chatbot today or the Discord bot once that exists.

### View Tasks
```
show my tasks               # Show all open tasks, grouped by tag
my tasks
tasks
what are my tasks
list tasks --tag School     # Trailing filters still work: --tag, --status, --priority,
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
add <title> to my tasks --tag <tag> --priority <1-5> --due <date> --describe "<text>"

Examples:
add finish physics homework to my tasks --tag School --priority 4 --due 2026-08-20
add engine rebuild plan to my tasks --tag Motorsports --priority 3
remind me to learn Rust
```
Tag defaults to `General` and priority defaults to `3` if omitted.

### Update Task
"Done" has a natural shortcut that takes an ID **or a title**:
```
mark <id-or-title> as done
complete <id-or-title>
finish <id-or-title>

Examples:
mark ff055559 as done
mark make pizza as done
complete make pizza
```
Other field updates (priority, tag, title, description, due date) still use the terser `!task <id> <field> <value>` form:
```
!task <id> priority <1-5>
!task <id> tag <tag>
!task <id> title <new title>
!task <id> describe <description>
!task <id> due <date>

Examples:
!task a1b2c3d4 priority 5
!task a1b2c3d4 tag "Project Ideas"
```

### Delete Task
Takes an ID **or a title**:
```
delete <id-or-title>
remove <id-or-title>
remove <id-or-title> from my tasks

Examples:
delete ff055559
delete make pizza
```

### Referencing a Task by Title

`mark`/`complete`/`finish`/`delete`/`remove` all accept a title instead of the ID shown at creation — including filler phrasing like "finish task make pizza" (the leading "task"/"the task" gets stripped before lookup). Resolution order in `TaskEngine._resolve_task_id()`:
1. Exact ID match (what legacy `!task` commands and the ID shown at creation always are)
2. Exact title match (case-insensitive)
3. Substring title match, only if exactly one task matches
4. If nothing matched and the identifier starts with "task"/"the task"/"my task", strip that prefix and retry steps 2-3 once

If a title matches more than one task at the same step, it returns an error listing the matching IDs instead of guessing:
```
❌ Multiple tasks titled "clean the garage" (`7a4941c4`, `3cc214d3`) — use the task ID instead
```
No fuzzy matching or LLM involved — just case-insensitive string comparison against whatever's in `tasks.db`.

### Legacy `!task` / `!tasks` Syntax
The old Discord-style syntax (`!task add "Title" --tag School`, `!tasks --tag School`, `!task <id> delete`) still works — the parser tries it first — but it's no longer required or shown in the UI. Existing scripts/tests that use it keep working unchanged.

## Discord Dashboard (Built, Not Yet Connected)

The bot posts a pinned message in the configured tasks channel showing the same data the `/api/tasks/dashboard` endpoint already formats today:

```
📋 OPEN TASKS

🎓 School (3)
┌─ [P5] Finish physics homework (due Aug 20)
├─ [P3] Read chapter 5
└─ [P2] Study guide review

🏍️  Motorsports (2)
┌─ [P4] Engine rebuild plan
└─ [P1] Parts supplier research

📝 General (4)
┌─ [P3] Learn Rust
├─ [P2] Setup Tailscale
├─ [P2] Morning briefing prototype
└─ [P1] Organize notes

💡 Project Ideas (1)
└─ [P2] Voice assistant improvements

━━━━━━━━━━━━━━━━━━━━━━━━
✅ DONE (7) | ⏳ IN PROGRESS (2) | 📌 DUE THIS WEEK (3)
```

Refreshes automatically every 5 minutes, plus an on-demand 🔄 reaction to update instantly — both built and working in `sunny_code/components/discord_bot.py`. See [[architecture/discord-bot.md]] for setup steps to connect it to a real server, and [[../phases.md]] "Discord Activity Log" for the broader (not yet built) multi-channel activity-log idea this is scoped out of.

When it ships, the web chatbot stays available as the fallback interface for whenever the Discord bot is down or unreachable.

## Storage Schema

### SQLite (tasks.db)

```sql
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  tag TEXT NOT NULL CHECK(tag IN ('School', 'Motorsports', 'General', 'Project Ideas')),
  status TEXT NOT NULL CHECK(status IN ('open', 'in_progress', 'done')) DEFAULT 'open',
  priority INTEGER CHECK(priority BETWEEN 1 AND 5) DEFAULT 3,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  due_date DATETIME
);

CREATE INDEX idx_tag ON tasks(tag);
CREATE INDEX idx_status ON tasks(status);
CREATE INDEX idx_priority ON tasks(priority);
CREATE INDEX idx_due_date ON tasks(due_date);
```

This is the actual schema created by `TaskDB._init_db()`.

## Command Parsing (No LLM)

All command parsing is hardcoded regex/string matching, in `tasks_parser.py` — natural phrasing is tried first, then the legacy `!task` syntax as a fallback:

```python
# Natural phrasing (primary)
NATURAL_ADD_TRIGGERS = [
    r'^add\s+(.+?)\s+to\s+(?:my\s+)?tasks?$',   # "add X to my tasks"
    r'^add\s+task[:\s]+(.+)$',                  # "add task X"
    r'^(?:create|new)\s+task[:\s]+(.+)$',       # "create task X" / "new task X"
    r'^make\s+(?:a\s+|me\s+a\s+)?task[:\s]*(.*)$',  # "make a task X" (empty title → helpful error)
    r'^remind\s+me\s+to\s+(.+)$',               # "remind me to X"
    r'^add\s+(.+)$',                            # bare "add X" catch-all, tried last
]
NATURAL_LIST_PATTERN   # "show/list/see/view (my) tasks", "my tasks", "tasks", "what are my tasks"
NATURAL_DONE_PATTERN   # "mark <id-or-title> as done", "complete <id-or-title>", "finish <id-or-title>"
NATURAL_DELETE_PATTERN # "delete <id-or-title>", "remove <id-or-title> (from my tasks)"
# TaskEngine._resolve_task_id() then strips a leading "task"/"the task" filler and
# tries title matching if the raw identifier isn't a real ID — see "Referencing a
# Task by Title" above.

# Legacy !task syntax (still works, no longer required)
TASK_ADD_PATTERN = r'!task\s+add\s+"([^"]+)"(.*)'       # title in quotes, flags follow
TASK_UPDATE_PATTERN = r'!task\s+(\w+)\s+(\w+)\s+(.*)'    # id, field, value
TASK_DELETE_PATTERN = r'!task\s+(\w+)\s+delete'
TASK_LIST_PATTERN = r'!tasks?(?:\s+(.*))?'

# Shared flag patterns (either syntax can carry --tag/--priority/--due/--describe)
TAG_PATTERN = r'--tag\s+(["\']?)([^"\'\s]+)\1'
PRIORITY_PATTERN = r'--priority\s+([1-5])'
DUE_PATTERN = r'--due\s+([\d\-]+)'                       # YYYY-MM-DD
DESCRIPTION_PATTERN = r'--describe\s+(["\']?)(.+?)\1(?:\s--|$)'

# Parse logic: regex → extract fields → validate → execute
# No semantic understanding needed, just pattern matching
```

## Response Format

### Success
```
✅ Task created: `a1b2c3d4`
Title: Finish physics homework
Tag: School
Priority: 4/5
Due: 2026-08-20
```

### Error
```
❌ Invalid priority (must be 1-5)
```

## Integration Points

### With Briefing Engine
The briefing engine already queries the task DB for its "Tasks" section (see [[briefing-engine]]) — this part is built and working, just running against whatever's actually in `tasks.db` rather than mock task data.

### With Obsidian Staging (Not Yet Built)
Plan: new tasks get logged to `staging/task-<date>.md` per the vault's staging convention (see [[../staging]]). Nothing writes there yet — today, tasks only exist in `tasks.db`.

### Cost Impact
- **Zero LLM tokens** — all hardcoded, confirmed in code (no `anthropic` calls anywhere in the task system)
- **Minimal API calls** — HTTP requests + SQLite queries only
- **Storage**: ~1KB per task in SQLite

## Future Enhancements

- Recurring tasks ("every Monday")
- Task dependencies ("blocked by X")
- Time tracking ("2 hours on this task")
- Export to Notion (on-demand)
- Mobile app integration (future)

## Implementation Checklist

- [x] SQLite schema + creation script
- [x] Command parser (regex-based)
- [x] Task CRUD operations
- [x] Dashboard formatter (`format_dashboard()`)
- [x] REST API + web chatbot interface
- [x] Title-based resolution for mark/complete/finish/delete (with filler-word handling)
- [x] `help`/`commands`/`info` response in the chatbot
- [x] Discord bot code (`sunny_code/components/discord_bot.py`) + config fields (token/channel env vars)
- [x] Discord dashboard builder (reuses `format_dashboard()`)
- [x] 5-minute refresh loop
- [x] 🔄 reaction for on-demand refresh
- [x] Pin dashboard message to the configured channel
- [x] Startup summary of missing API keys, logged + posted to Discord
- [ ] **Connect a real bot token and verify against a live server**
- [ ] Logging to Obsidian staging
- [ ] Slash command variants (optional)
