---
id: sunny-project-system
type: component
status: active
created: 2026-08-24
updated: 2026-09-23
tags: [projects, containers, critique, research, claude, component]
---

# Project System

A project is a **folder Sunny reads as one body of context** — closer to
how Claude's own projects work than to a document generator. Scope a
conversation to one and it already knows what the project is, what the
plan says, what the critique found, and whatever notes are sitting in the
folder.

`sunny_code/components/project_store.py` (the container) and
`project_work.py` (planning, critique, research).

## What this replaced

Until 2026-09-23 this was a one-shot scaffolder: three wizard questions,
one LLM call, one overview file, done. Nothing referred to a project
again — no status, no phase, no context, no way to ask "what am I working
on". It generated a document and called that a project system.

`project_engine.py` still exists for the old scaffold path. The container
model is what everything new uses.

## Layout

```
sunny-vault/data/projects/<slug>/
  project.md       frontmatter (status, phase, dates) + description
  instructions.md  human-owned — how Sunny behaves on THIS project
  plan.md          milestones and timeline
  critique.md      the red-team pass over the plan
  research/*.md    dated comparisons and findings
  <anything else>  dropped in by hand, still read as context

sunny-vault/data/projects/archive/<slug>/
  finished and parked projects, same shape
```

`context()` reads **every** readable file in the folder into the prompt.
A note filed by hand in Obsidian is available to Sunny on the next
message with no import step. The vault is the database.

Capped at `CONTEXT_BUDGET_CHARS` (12,000). Files that don't fit are
**named in the output** rather than silently dropped — "Sunny didn't know
about the research note" is otherwise a bug report with no explanation.

## Status: three values, one field

| Status | Means |
| --- | --- |
| `active` | on it now |
| `long-term` | ongoing, no end date |
| `someday` | later, not started |

Chosen over a two-dimensional horizon × state model. Two fields describe
reality more precisely — an ongoing project can also be the one you are
on today — but every item then needs two decisions to file and two to
find, and the filing gets skipped. One occasionally-imprecise field beats
two that go stale.

A long-term project you're working on today is `active`; it returns to
`long-term` when you step off it.

## Phase: how far along the thinking is

```
idea → planning → critique → refined → building → done / parked
```

**Status and phase are independent.** Status is "do I care right now";
phase is "how far along is the thinking". A `someday` project can sit at
`refined` with a finished plan waiting for time. Collapsing them would
mean starting work on something forced it to look planned.

## The critique phase

The distinctive part, and the reason the phase list is ordered rather
than free text.

Most planning goes idea → plan → do. The failure mode is that the first
plan is the one you execute, and the first plan gets written while you
are still enthusiastic about the idea. `critique` sits between `planning`
and `refined` so the plan is attacked once, deliberately, while changing
it is still cheap.

`critique()` is adversarial **on purpose**:

- Every risk needs a concrete failure mode — what breaks, under what
  conditions, when it would first be noticed. "This might not scale" is
  rejected by the prompt.
- Every risk needs a **specific fix**. "Be careful" and "monitor closely"
  are not fixes; a fix changes the plan. A critique that only lists
  problems moves work onto the reader and gets ignored after the second
  time.
- Severity is ranked honestly. Inventing high-severity problems to seem
  thorough is the failure mode of the exercise.

Structured output (typed JSON), because severity has to be sortable —
it decides what gets addressed before building starts. Rendered into
`critique.md` so it is editable in Obsidian rather than scrolling away in
chat.

**Live example** (personal website, 2026-09-23):

> **Auth boundary verified once, not enforced continuously** — HIGH
> Milestone 7 says "confirm portal is unreachable without auth from a
> clean browser" — a manual, single-point-in-time check.
> **Fix:** automated test hitting every `/portal` route without a session
> cookie, asserting 401/redirect.

## Research

`research()` runs with **web search on** and returns **prose, not
fields**. A comparison's value is the reasoning, and forcing it into a
schema would flatten exactly the part worth reading. Web search also
pairs badly with a constrained output format.

Filed under `research/<date>-<slug>.md`, one file per question rather
than one rolling file — the reasoning behind a choice is most useful
exactly when you are reconsidering it.

## Archiving

A shipped project sitting at phase `done` is still in the list, so the
list keeps growing and stops answering "what am I working on".

`archive()` **moves the folder** to `archive/` and records `archived` as
the status — the same convention `tasks_db` uses, which keeps the
projects directory readable when browsing the vault.

**`archived` is deliberately not in `STATUSES`.** It is not a fourth kind
of live project competing with the other three; it is "not in the list at
all". In `STATUSES` it would appear in every filter and summary, which is
the opposite of the point. `update()` still rejects it — that function
takes user input — and `archive()` writes it through a private setter.

**Archived is hidden, not unreachable.** `get()`, `context()` and
`resolve()` all fall back to the archive, so asking about finished work
still answers. The phase records *why* it left: `done` for shipped,
`parked` for abandoned. A year later that is the distinction worth
having.

## Scoped conversations

`set_focus(session_id, slug)` binds a chat session to a project.
`focus_context()` then returns the folder plus its `instructions.md`,
injected in `briefing.py` between memory and the doc search — project
files are more specific than a general doc search and should win where
they disagree.

Focus is **in memory, not on disk**. It is a property of a conversation,
not of the project, and coming back hours later to find yourself silently
still "inside" a project is worse than having to say which one again.

## Safety properties

- `write_file()` takes filenames from an LLM, so it refuses anything that
  resolves outside the project folder.
- A new project cannot take an archived project's slug, or unarchiving
  would later collide with a live folder of the same name.
- `resolve()` refuses to guess between two matches. Filing work under the
  wrong project is worse than being asked which one. Live projects win a
  tie against archived ones.
- The vault is the source of truth — a folder deleted by hand in Obsidian
  disappears from listings immediately rather than lingering in an index.

## Tests

`test_project_store.py` — 77 assertions. The ones that matter are where
this would go quietly wrong rather than loudly: a context file silently
missing, a path escaping the folder, a resolve guessing between two
projects, an archived project becoming unreachable.

## Current projects

Imported from the Notion Projects database on 2026-09-23. Rows tagged
`ARCHIVE` there were skipped — that tag is the existing junk marker, and
the database's own default view filters on it.

Notion's `Status` field was **not** trusted on its own: 5 of the 7 rows
marked *In progress* were also tagged `ARCHIVE`, so the field had rotted
and the tag was the newer signal.

## See also

- [[../COMMANDS.md]] — what to type
- [[../ROADMAP-2026-09.md]] — what is still open
- [[memory.md]] — the other long-lived context source
