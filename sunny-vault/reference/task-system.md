---
id: sunny-tasks
type: reference
status: active
source: repo
created: 2026-08-18
tags: [features, tasks, discord, no-llm]
---

# Task Management System

A live Discord-based task dashboard. View, create, and update tasks from any device via Discord messaging. **No LLM calls** — all hardcoded logic.

## Tags

- **School** — Academic work, classes, assignments
- **Motorsports** — Car projects, maintenance, parts
- **General** — Personal growth, learning, setup
- **Project Ideas** — Sunny improvements, future features

## Data Model

```
Task {
  id: UUID                  # unique identifier
  title: string             # task name
  description: string       # optional details
  tag: enum                 # School | Motorsports | General | Project Ideas
  status: enum              # open | in_progress | done
  priority: 1-5             # 1=low, 5=critical
  created_at: datetime      # when created
  updated_at: datetime      # last modified
  due_date: datetime        # optional target date
}
```

## Storage

**SQLite database**: `tasks.db` on Lenovo

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
```

## Discord Bot Commands

### View Tasks

```
!tasks                      # Show all open tasks, grouped by tag
!tasks <tag>               # Show tasks for specific tag: School, Motorsports, General, "Project Ideas"
!tasks --all               # Show all tasks including completed
!tasks --done              # Show only completed tasks
!tasks --priority 4        # Show priority 4+ tasks
!tasks --overdue           # Show past-due open tasks
```

### Create Task

```
!task add <title> --tag <tag> [--priority 1-5] [--due YYYY-MM-DD] [--describe <description>]

Examples:
!task add "Finish physics homework" --tag School --priority 4 --due 2026-08-20
!task add "Engine rebuild plan" --tag Motorsports --priority 3
!task add "Learn Rust" --tag General --priority 2 --describe "Functional programming concepts"
!task add "Voice-activated lights" --tag "Project Ideas" --priority 1
```

### Update Task

```
!task <id> status <open|in_progress|done>
!task <id> priority <1-5>
!task <id> tag <tag>
!task <id> title <new title>
!task <id> describe <description>
!task <id> due <YYYY-MM-DD>
!task <id> undo                    # revert to previous state

Examples:
!task abc123 status done
!task abc123 priority 5
!task abc123 tag School
!task def456 due 2026-08-25
```

### Delete Task

```
!task <id> delete
```

## Live Dashboard Display

Pinned message in dedicated `#tasks` Discord channel showing:

```
📋 OPEN TASKS — Updated every 5 min

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
└─ [P2] Voice-activated lights

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ DONE (7)  |  ⏳ IN PROGRESS (2)  |  📌 DUE THIS WEEK (3)

React with 🔄 to refresh instantly
```

**Refresh**: Every 5 minutes automatically, or on-demand via 🔄 emoji reaction

## Command Parsing (Hardcoded, No LLM)

All parsing via regex pattern matching:

```python
# Add task
PATTERN: !task add "([^"]+)"(.*flags)
EXTRACT: title, priority, tag, due_date, description

# Update task  
PATTERN: !task (\w+) (\w+) (.+)
EXTRACT: id, field (status|priority|tag|title|describe|due), value

# View tasks
PATTERN: !tasks [--filter] [<tag>]
EXTRACT: filter type, tag name
```

No semantic understanding needed — just pattern matching and validation.

## Response Format

### Success
```
✅ Task created: abc123def
   Title: Finish physics homework
   Tag: School
   Priority: 4
   Due: 2026-08-20
```

### Error
```
❌ Invalid priority (must be 1-5)
```

## Integration Points

### With Briefing Engine
- Morning briefing includes: "You have 5 open tasks, 3 due this week"
- Mentions highest-priority tasks from past week still open
- No recommendation logic — just statement of fact

### With Obsidian Staging
- New tasks logged to `staging/task-<date>.md` with frontmatter
- Not synced to Notion yet (live Discord-only for now)

### With Discord Activity Log
- All task changes posted to `#task-updates` channel
- Auto-archive completed tasks to Discord thread

## Cost Impact

- **Zero LLM tokens** — all hardcoded parsing
- **Minimal API calls** — Discord bot messages + SQLite queries
- **Storage**: ~1KB per task in SQLite

## Implementation Checklist

Phase (TBD, likely Phase 2 alongside briefing):

- [ ] SQLite schema creation
- [ ] Discord bot setup (token in env var)
- [ ] Regex-based command parser
- [ ] Task CRUD operations (create, read, update, delete)
- [ ] Dashboard embed builder
- [ ] 5-minute auto-refresh loop
- [ ] Error handling + validation
- [ ] Obsidian staging integration
- [ ] Discord channel setup (#tasks, #task-updates)
- [ ] Pin dashboard message to #tasks
- [ ] Test all commands

## Future Enhancements

- Recurring tasks ("every Monday")
- Task dependencies ("blocked by task X")
- Time tracking ("2 hours on this task")
- Export to Notion (on-demand)
- Mobile app integration
- Calendar integration (auto-add to Notion calendar)
- Habit tracking variant (daily/weekly recurring)
