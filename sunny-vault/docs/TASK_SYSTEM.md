# Task Management System

Task management with hardcoded logic (no LLM required). **Discord is the intended primary interface** — a live bot dashboard you view and command from a `#tasks` channel — but it hasn't been built yet. Until it exists, the same command syntax is available through the web chatbot, which is fully working today and will remain the fallback for whenever the Discord bot is down.

## Status

| Piece | Status |
|-------|--------|
| SQLite storage + CRUD | ✅ Built (`sunny/components/tasks_db.py`) |
| Command parser (`!task`/`!tasks` syntax) | ✅ Built (`sunny/components/tasks_parser.py`) |
| Task engine (command execution, dashboard formatting) | ✅ Built (`sunny/components/tasks_engine.py`) |
| REST API | ✅ Built (`sunny/components/tasks_api.py`) |
| Web chatbot interface (`/chatbot`) | ✅ Built — current primary way to use the task system |
| **Discord bot dashboard** | ⏳ **Not built** — planned as the primary interface, see [[../phases.md]] "Discord Activity Log" |
| Obsidian staging integration | ⏳ Not built — nothing writes to `staging/` yet |

Current focus: fleshing out the task system itself (the table above) before starting the Discord bot.

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

Open `/chatbot` (or `/`, which redirects there) and type the same `!task`/`!tasks` commands described below. The chatbot's JS sends them to the REST API under the hood:

- Plain commands (`!tasks`, `!task <id> ...`) → `POST /api/tasks/command?cmd=<command>`
- Everything else not starting with `!` is treated as a briefing question, not a task command

## REST API

```
POST /api/tasks/command?cmd=...   Execute any !task/!tasks command
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

Same syntax whether it's typed into the web chatbot today or the Discord bot once that exists.

### View Tasks
```
!tasks                      # Show all open tasks, grouped by tag
!tasks --tag <tag>          # Show tasks for specific tag
!tasks --all                # Show all tasks including completed
!tasks --done               # Show only completed tasks
!tasks --open               # Show only open tasks
!tasks --in-progress        # Show only in-progress tasks
!tasks --priority 4         # Show priority 4+ tasks
!tasks --due-soon           # Show tasks due within 7 days
```

### Create Task
```
!task add "<title>" --tag <tag> --priority <1-5> --due <date> --describe "<text>"

Examples:
!task add "Finish physics homework" --tag School --priority 4 --due 2026-08-20
!task add "Engine rebuild plan" --tag Motorsports --priority 3
!task add "Learn Rust" --tag General
```
Tag defaults to `General` and priority defaults to `3` if omitted.

### Update Task
```
!task <id> status <open|in_progress|done>
!task <id> priority <1-5>
!task <id> tag <tag>
!task <id> title <new title>
!task <id> describe <description>
!task <id> due <date>

Examples:
!task a1b2c3d4 status done
!task a1b2c3d4 priority 5
!task a1b2c3d4 tag "Project Ideas"
```

### Delete Task
```
!task <id> delete
```

## Planned: Discord Dashboard (Not Yet Built)

Once the Discord bot exists, the plan is a pinned message in a dedicated `#tasks` channel showing the same data the `/api/tasks/dashboard` endpoint already formats today:

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

**Planned update behavior**: dashboard refreshes every 5 minutes, plus an on-demand 🔄 reaction to update instantly. This is a design target — see [[../phases.md]] "Discord Activity Log" for the actual build checklist.

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

All command parsing is hardcoded regex/string matching, in `tasks_parser.py`:

```python
TASK_ADD_PATTERN = r'!task\s+add\s+"([^"]+)"(.*)'       # title in quotes, flags follow
TASK_UPDATE_PATTERN = r'!task\s+(\w+)\s+(\w+)\s+(.*)'    # id, field, value
TASK_DELETE_PATTERN = r'!task\s+(\w+)\s+delete'
TASK_LIST_PATTERN = r'!tasks?(?:\s+(.*))?'
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
Plan: new tasks get logged to `staging/task-<date>.md` per the vault's staging convention (see [[../../sunny-vault/staging]]). Nothing writes there yet — today, tasks only exist in `tasks.db`.

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
- [ ] Discord bot setup + token env var
- [ ] Discord embed dashboard builder
- [ ] 5-minute refresh loop
- [ ] 🔄 reaction for on-demand refresh
- [ ] Pin dashboard message to `#tasks` channel
- [ ] Logging to Obsidian staging
- [ ] Test all commands via Discord
