---
id: sunny-llm-instructions
type: component
status: active
created: 2026-08-20
tags: [llm, claude, instructions, prompts, vault]
---

# LLM Instructions — Vault-Loaded System Prompts

Each `ask_claude()` "purpose" gets its system prompt from `sunny-vault/docs/instructions/{purpose}.md` instead of a Python f-string. Hand-edit the file, no redeploy, no restart — the change takes effect on the very next call. Built alongside the LLM call catalog (see [[llm-integration]] and [[llm-readiness]]) specifically to serve the "squeeze out the least tokens possible" goal: instructions live as small, purpose-specific files, so a given call only ever pays for the one prompt it actually needs.

## Status

✅ Built — `sunny_code/components/instructions.py`, `sunny_code/components/vault_io.read_body()`, wired into `llm_client.ask_claude()`.

## How It Works

- `ask_claude(prompt, purpose="weekly_health_check", ...)` — if `system` isn't passed explicitly, `instructions.load_instructions(purpose)` runs first, converting `purpose` to a filename (`_` → `-`, `.md` appended) and reading `sunny-vault/docs/instructions/{filename}`'s body via `vault_io.read_body()` (frontmatter stripped, just the prompt text).
- No file for that purpose → `None`, same as not passing a system prompt at all. No error, no crash — matches this app's honest "not configured" pattern everywhere else.
- **Not cached.** Every call re-reads the file, matching `get_settings()`'s deliberate uncached-by-design choice — the tradeoff (a little disk I/O per call) buys hand-edits that take effect immediately, with zero cache-invalidation logic to get wrong.
- A caller that passes `system=` explicitly always wins — the vault lookup only fills in when nothing else was given.

## Why Not a Retrieval/Search System

An earlier proposal for this looked like RAG: keyword search across many instruction files, a hand-maintained `keyword → file` index, tag-based filtering, maybe vector embeddings. Rejected as disproportionate for what this actually needs — every `ask_claude()` caller already knows exactly which task it's performing (it's choosing the `purpose` string itself), so there's no ambiguity to resolve at retrieval time. A hand-maintained index is also a second source of truth that drifts from the actual files; exact-match-by-filename has none of that risk.

If a genuine need for multi-file assembly per call ever shows up, revisit then — nothing here blocks it, but it isn't worth building ahead of an actual need.

## File Format

```markdown
---
id: weekly-health-check-instructions
type: instruction
status: active
tags: [llm, health-check]
---

You write Project SUNNY's weekly health report...
```

Frontmatter matches the shape used across `docs/` (`id`, `type`, `status`, `tags`) rather than `state/`'s shape (`updated_at` instead of `tags`) — deliberate, since instruction files are hand-authored reference content like `docs/`, not machine-rewritten mirrors like `state/`. `type: instruction` distinguishes them.

## Token Budget

Whatever's in one of these files is paid for on **every** call for that purpose — this is the single highest-leverage place to cut spend, more than trimming the per-call user-supplied prompt. Keep instruction files terse and imperative. Prompt caching (`cache_control` on the system block) is a real future lever if any one purpose starts getting called frequently, but isn't built here — it would need `system` to become a content-block list instead of a plain string in `llm_client._call_claude_sync()`, real complexity for a benefit that doesn't exist yet since nothing calls `ask_claude()` on a regular cadence today.

## Security Note

Instruction files are hand-editable markdown, loaded verbatim as system prompt text. Prompt injection defenses are explicitly out of scope by the user's own decision (2026-08-20) — single-user, no untrusted party ever writes into this vault. See [[llm-integration]]'s Prompt Engineering section for the full reasoning and what would change that call.

## Files

- `sunny_code/components/instructions.py` — `load_instructions(purpose)`
- `sunny_code/components/vault_io.py` — `read_body(path)`, the generic frontmatter-stripping helper this is built on
- `sunny_code/components/llm_client.py` — the one call site (`ask_claude()`)
- `sunny-vault/docs/instructions/` — the files themselves

## Dependencies

- [[llm-integration]] — the parent design this implements a piece of
- [[llm-readiness]] — built-vs-not tracking
- [[vault-storage]] — shares `vault_io.py`'s atomic-write/frontmatter helpers, though instructions are read-only from Sunny's side (never machine-rewritten), unlike Tasks/Lists

## Implementation Checklist

- [x] `vault_io.read_body()` — generic frontmatter-stripping read helper
- [x] `instructions.load_instructions(purpose)` — exact-match-by-filename lookup, uncached
- [x] Wired into `ask_claude()` — auto-loads when `system` isn't passed explicitly
- [x] `sunny-vault/docs/instructions/` created as a fourth vault lifecycle category, documented in [[../DESIGN|DESIGN.md]]
- [x] `weekly-health-check.md` — first real instruction file, see [[health-check]]
- [x] `general-chat.md`, `project-scaffold.md`, `storm-mode.md`, `exam-prep-review.md`, `syllabus-parse.md` — added as each of those features shipped (2026-08-21 through 2026-08-25), see [[llm-integration]]
- [ ] More instruction files as more LLM features get built (email triage, task interpretation still not built — see [[llm-readiness]])
