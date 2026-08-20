---
id: sunny-lists
type: component
status: active
created: 2026-08-19
tags: [lists, todo, component]
---

# Lists (To-Do Lists, Groceries, Anything Checkable)

A separate subsystem from [[../TASK_SYSTEM.md|Tasks]] — same "no LLM, plain pattern matching" philosophy, own database, own parser, own engine. Tasks are priority/due-date/category work items; Lists are simple named collections of checkable items (groceries, packing lists, whatever). Don't conflate the two — a task is never added "to a list" and a list item never gets a priority.

## Status

| Piece | Status |
|-------|--------|
| Vault storage (`sunny-vault/state/lists/`) | Built (`sunny_code/components/lists_db.py`) — markdown, not SQLite, see [[vault-storage]] |
| Command parser | Built (`sunny_code/components/lists_parser.py`) |
| List engine | Built (`sunny_code/components/lists_engine.py`) |
| Routed into web chatbot + Discord bot | Built (both go through `assistant.handle_message`) |
| Dedicated REST API | Not built — only reachable through chat/Discord today |
| Obsidian staging integration | Not built |

## How It Works

- **Storage**: Markdown in the vault (`sunny-vault/state/lists/<slug>.md`), one file per list — frontmatter for the list (id, name, source, created_at), items as native Obsidian checkboxes (`- [ ] milk` / `- [x] bread`) in the body. Deleting a list's file deletes its items with it (cascade-by-construction — no separate FK step needed, since items live in the same file). Full design: [[vault-storage]].
- **Default list**: If you don't name one, items go to a list called "To-Do" (`DEFAULT_LIST_NAME`), created automatically on first use.
- **Any name works**: "add milk to my grocery list" creates a "grocery" list on the spot — no setup step, same free-form philosophy as task categories.
- **Checking items**: marking an item done doesn't delete it — it's a checkbox (`checked` column). "Remove"/"delete" is what actually deletes a row.
- **Not async**: `ListEngine.try_execute()` is a plain sync method (local file I/O is fast enough not to need it, same reasoning that applied to SQLite before this moved to vault storage) — unlike `TaskEngine.execute_command()` and `ScheduledEngine.try_execute()`, which are both async.

## Command Syntax

```
add <item> to my list → default "To-Do" list
add <item> to my <name> list → named list, created if new
add <item1>, <item2>, and <item3> to my <name> list → multiple items at once

what's on my list / show my list → default list
what's on my <name> list → named list
my lists → show all lists you have

remove <item> from my list
remove <item> from my <name> list
```

### Routing note

`assistant.py` checks the Lists parser **before** the Tasks parser (see [[../TASK_SYSTEM.md]] "Routing order"). Lists commands require the literal word "list" somewhere in the phrase, so they can't be confused with task commands — but without this ordering, Tasks' broad `remove <x>`/`delete <x>` patterns would swallow "remove milk from my list" before the Lists parser ever saw it.

### A regex pitfall worth remembering

Bare patterns (no list name, e.g. "add X to my list") are checked **before** named patterns (e.g. "add X to my `<name>` list") in `lists_parser.py`. Checking named first caused a real bug: the optional `(?:my\s+)?` in a named pattern could backtrack so that the non-greedy list-name capture group swallowed the word "my" itself, turning "add walk the dog to my list" into "create a list called 'my' and add 'walk the dog'" instead of adding to the default To-Do list. Always try the strict/unambiguous pattern first.

## Data Model

```python
List {
  id: str
  name: str # unique, case-insensitive — enforced by lookup-before-create,
                      # not a DB constraint now that storage is markdown
  source: str # web | discord | api — see Device Tracking below
  created_at: datetime
}

ListItem {
  id: str # synthesized from file line position at read time, not
                       # stored — see vault-storage.md for why that's safe
  text: str
  checked: bool
  source: None # tracked in the old SQLite schema, dropped — nothing
                        # ever read it; see vault-storage.md
  created_at: None # same — file order already encodes creation order
}
```

## Response Format

No IDs shown, same as Tasks — items and lists are referenced by name/text only.

```
Added "milk" to grocery
```
```
grocery
milk
eggs
bread
```
```
Removed "milk" from grocery
```

## Dependencies

- [[../TASK_SYSTEM.md]] — sibling subsystem, same routing entry point (`assistant.handle_message`)
- [[discord-bot.md]] — same bot, same channel, no separate Lists dashboard (unlike Tasks, Lists don't get a pinned live-updating message today)
- [[vault-storage]] — the markdown storage design shared with Tasks
- `sunny_code/components/device.py` — `device_from_session()`, shared with Tasks/Alarms/Reminders

## Implementation Checklist

- [x] Vault markdown storage (`sunny-vault/state/lists/`), cascade-by-construction (list + items in one file)
- [x] Natural-language parser (create/add/query/remove, multi-item splitting)
- [x] Free-form list names, default "To-Do" list
- [x] Routed into web chatbot and Discord bot via shared `handle_message()`
- [x] Device/source tracking on lists and items
- [x] No IDs in chat/Discord responses
- [ ] Dedicated REST API (`/api/lists/...`) — not built, chat/Discord only for now
- [ ] Pinned Discord dashboard for lists (Tasks has one, Lists doesn't yet)
- [ ] Obsidian staging integration
