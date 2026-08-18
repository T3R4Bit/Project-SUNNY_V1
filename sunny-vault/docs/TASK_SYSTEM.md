Im# Task Management System

A live Discord-based task dashboard with hardcoded logic (no LLM required). View, create, and update tasks from any device via Discord messaging.

## Overview

- **Tags**: School, Motorsports, General, Project Ideas
- **Storage**: SQLite database (`tasks.db`)
- **Interface**: Discord bot + live dashboard embed
- **Logic**: Deterministic, no LLM calls

## Data Model

```python
Task {
  id: str                    # UUID
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

## Discord Bot Commands

### View Tasks
```
!tasks                      # Show all open tasks, grouped by tag
!tasks <tag>               # Show tasks for specific tag
!tasks --all               # Show all tasks including completed
!tasks --done              # Show only completed tasks
!tasks --priority 4        # Show priority 4+ tasks
```

### Create Task
```
!task add <title> --tag <tag> --priority <1-5> --due <date>

Examples:
!task add "Finish physics homework" --tag School --priority 4 --due 2026-08-20
!task add "Engine rebuild plan" --tag Motorsports --priority 3
!task add "Learn Rust" --tag General
```

### Update Task
```
!task <id> status <open|in_progress|done>
!task <id> priority <1-5>
!task <id> tag <tag>
!task <id> title <new title>
!task <id> describe <description>
!task <id> due <date>

Examples:
!task abc123def status done
!task abc123def priority 5
!task abc123def tag "Project Ideas"
```

### Delete Task
```
!task <id> delete
```

## Discord Dashboard

### Live Embed Display

Post a pinned message in a dedicated `#tasks` channel showing:

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

### Update Frequency
- Dashboard refreshes every 5 minutes
- On-demand refresh: React with 🔄 emoji to update instantly

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
```

## Bot Logic (No LLM)

All command parsing is hardcoded regex/string matching:

```python
# Command patterns
TASK_ADD_PATTERN = r'!task add "([^"]+)"(.*)'  # title in quotes, flags follow
TASK_UPDATE_PATTERN = r'!task (\w+) (\w+) (.*)'  # id, field, value
TAG_PATTERN = r'--tag\s+[""]?([^"\s]+)[""]?'
PRIORITY_PATTERN = r'--priority\s+([1-5])'
DUE_PATTERN = r'--due\s+([\d-]+)'  # YYYY-MM-DD

# Parse logic: regex → extract fields → validate → execute
# No semantic understanding needed, just pattern matching
```

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
- Highest-priority tasks from past week that are still open

### With Obsidian Staging
- New tasks logged to `staging/task-<date>.md`
- Not pushed to Notion; live only in Discord for now

### Cost Impact
- **Zero LLM tokens** — all hardcoded
- **Minimal API calls** — Discord bot messages + SQLite queries
- **Storage**: ~1KB per task in SQLite

## Future Enhancements

- Recurring tasks ("every Monday")
- Task dependencies ("blocked by X")
- Time tracking ("2 hours on this task")
- Export to Notion (on-demand)
- Mobile app integration (future)

## Implementation Checklist

- [ ] SQLite schema + creation script
- [ ] Discord bot setup + token env var
- [ ] Command parser (regex-based)
- [ ] Task CRUD operations
- [ ] Dashboard embed builder
- [ ] 5-minute refresh loop
- [ ] Error handling + validation
- [ ] Logging to Obsidian staging
- [ ] Pin dashboard message to #tasks channel
- [ ] Test all commands
