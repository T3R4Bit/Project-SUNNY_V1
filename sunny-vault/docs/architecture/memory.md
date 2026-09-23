---
id: sunny-memory
type: component
status: active
created: 2026-09-22
tags: [memory, profile, facts, retrieval, llm, component]
---

# Long-term memory

`sunny_code/components/memory_store.py`

Three tiers, of which two are built:

| Tier | What it is | Who writes it |
| --- | --- | --- |
| **Profile** | One slow-changing doc: how you think, how you plan, your flaws, standing constraints | **You**, by hand |
| **Facts** | Small dated notes with a type and a source | Sunny, from "remember that …" |
| **Patterns** | Derived weekly over the facts plus the metrics | Not built yet |

## The vault is the source of truth

Facts are markdown files in `sunny-vault/memory/facts/` with an index in
SQLite. The **files win**: delete a note by hand in Obsidian, run
`reindex()`, and it stops being injected.

That rule matters more here than anywhere else in the system. A fact you
explicitly removed that keeps being asserted is worse than one that was
never stored — you have no way to see why Sunny still believes it.

## Profile is human-owned

`sunny-vault/memory/profile.md`. Sunny reads it and **never writes it**,
the same rule as `personality.md`. A vault file edited by both you and a
server process is exactly what file sync cannot merge cleanly, and it is
the shape of the conflicts Syncthing was already producing.

An **empty scaffold is not injected.** Headings with nothing under them
cost tokens and say nothing, so `profile_text()` drops everything before
the first `## ` and skips empty sections. A file with only the template
in it contributes zero characters to the prompt.

## Retrieval

Keyword overlap, scored — deliberately not embeddings. Embeddings would
mean torch on a shared 1GB box for a corpus that will be in the hundreds
of facts, not thousands. `score_fact()` is the seam where that gets swapped
if it ever earns its place.

**Preferences and flaws outrank plain facts** on equal keyword overlap,
because they shape *how* an answer is given rather than just adding a
detail.

`format_for_prompt()` returns `""` when there is nothing to say, so
callers concatenate unconditionally without a branch.

## Injection order

In `briefing.py`:

```
memory → project context → doc search → conversation → question
```

Standing context first so a follow-up cannot push it out of the model's
attention; project context next because a focused project is more
specific than a general doc search.

## Two bugs worth remembering

**"remember to call mom" is not a memory.** A bare `remember ` prefix
captured reminder phrasing as a fact. Guarded: text starting "to " after
the trigger is not a memory.

**The empty-profile scaffold was being injected** despite a docstring
claiming otherwise — the preamble above the first heading was kept. Fixed
by skipping everything before the first `## `.

## Not built yet

- **Patterns** (tier 3) — weekly derivation over facts plus metrics.
  Facts need to accumulate before reflecting over them means anything.
- **Automatic extraction** — a heartbeat that combs new conversations for
  memory-worthy facts and files them into the two tiers without being
  asked. This is in Keaton's own Notion notes as the original idea; the
  storage side is done, the extraction side is not.

## Tests

`test_memory_store.py` — the cases where memory would be quietly wrong:
a hand-deleted fact still being injected, an empty scaffold costing
tokens, `format_for_prompt` returning something when it should return
nothing.

## See also

- [[../COMMANDS.md]] — `remember that …`, `what do you remember`
- [[personality.md]] — how Sunny sounds, versus what it knows
