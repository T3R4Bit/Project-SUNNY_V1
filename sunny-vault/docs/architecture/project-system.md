---
id: sunny-project-system
type: component
status: active
created: 2026-08-24
tags: [projects, wizard, llm, component]
---

# Project Wizard

Say "new project" (or a close variant — see Trigger below) from any interface (console, Discord text, Discord voice), and Sunny walks a short, fully hardcoded wizard through name → description → sections → a real yes/no confirm, then hands off to exactly one LLM call that drafts a real multi-file project folder under `sunny-vault/projects/<slug>/`. See [[../TASK_SYSTEM.md]] — this sits alongside Tasks/Lists/Alarms-Reminders as another feature routed through the same `assistant.handle_message()`, not part of the task system itself.

## Status

| Piece | Status |
|-------|--------|
| Wizard conversation state (name/description/sections/confirm) | Built — `assistant.py`'s pending-follow-up mechanism, same TTL/cancel pattern as the task-title/task-category prompts |
| Trigger phrases | Built — `_PROJECT_TRIGGERS` in `assistant.py` |
| Scaffold generation (one LLM call → real files) | Built — `sunny_code/components/project_engine.py` |
| System prompt | Built — `sunny-vault/instructions/project-scaffold.md` |
| Discord dashboard integration | Built — the task dashboard's Projects field lists real folder names from `sunny-vault/projects/` (`discord_bot.py`'s `build_dashboard_embed()`) |

## How It Works

1. **Trigger** — an exact-phrase match in `_PROJECT_TRIGGERS` (e.g. "new project", "start a new project"), checked in `assistant.py`'s routing before task/list/calendar/etc. parsing.
2. **Name** → **Description** → **Sections** — three plain questions, each stored via `_set_pending(session_id, "project_name"|"project_description"|"project_sections", ...)`. Sections is optional — saying "you decide" (or similar) skips straight to Claude picking a sensible split based on the description.
3. **Confirm** — a recap of what was collected, then a real yes/no. Multiple phrasings per question (not one fixed line) to avoid feeling robotic on repeat use. A firm "no" ends the wizard immediately — **the LLM is never called** for a declined project. Only "yes" proceeds.
4. **Scaffold** — `ProjectEngine.scaffold(name, description, sections)`, the module's one entry point (the class is otherwise stateless — `assistant.py` owns all conversation state). One `ask_claude(purpose="project_scaffold", model="sonnet", max_tokens=8192)` call — Sonnet and a larger token budget deliberately, since this is real content authoring, not the quick Haiku judgment calls used elsewhere (see [[llm-integration]]).

## Output Format

Claude is asked for a single bare JSON object, no markdown fence: `{"files": [{"filename": "...", "content": "..."}, ...]}`. `_parse_file_plan()` strips a code fence defensively anyway, since instructions not to add one aren't always followed. Every filename is forced to end in `.md`, and `Path(filename).name` strips any path component before writing — a defensive guard against a filename like `"../x.md"` escaping the project directory, even though Claude is only ever asked for bare filenames.

Per `project-scaffold.md`'s system prompt: always exactly one top-level overview file, plus at least two more focused topic files (never a single-file stub) — what those topic files are is inferred from the project description rather than a fixed template.

## Storage

`sunny-vault/projects/<slug>/*.md` — `slug` from `vault_io.slugify(name)`, with the same `-2`/`-3`... collision-avoidance scheme as `tasks_db.py`/`lists_db.py`, extended from a single file to a whole directory. Written via `vault_io.atomic_write_text`, one call per file — a disk error partway through a multi-file write is reported honestly ("Started writing X but hit a disk error partway through"), not silently swallowed.

## Failure Modes

Every failure path returns `(False, message)`, never raises — same contract as `TaskEngine`'s execute methods:
- Claude unreachable (not configured, budget exceeded, API error) → "Couldn't reach Claude to draft the project — try again in a moment."
- Malformed JSON, missing `files` key, or a file entry missing `filename`/`content` → "Claude's project plan came back malformed — try again."
- A disk error partway through writing → reports how far it got, doesn't retry automatically.

## Dependencies

- [[../TASK_SYSTEM.md]] — sibling feature, same routing entry point (`assistant.handle_message`)
- [[llm-integration]] — `ask_claude(purpose="project_scaffold")`, model/token-budget choice
- [[llm-instructions]] — `sunny-vault/instructions/project-scaffold.md`
- [[discord-bot]] — the dashboard's Projects field reads real folder names from `sunny-vault/projects/`

## Implementation Checklist

- [x] Wizard trigger phrases
- [x] Name/description/sections collection via the shared pending-follow-up mechanism
- [x] Optional sections ("you decide" lets Claude choose the split)
- [x] Recap + real yes/no confirm before any LLM call
- [x] One-shot JSON-structured scaffold generation
- [x] Defensive filename sanitization (no path escape)
- [x] Multi-file enforcement (overview + 2 more minimum) — enforced by the system prompt, not code
- [x] Discord dashboard Projects field
- [ ] Editing/updating an existing project through the wizard (today only creates new ones)
- [ ] Obsidian staging integration (matches Tasks' same not-yet-built gap)
