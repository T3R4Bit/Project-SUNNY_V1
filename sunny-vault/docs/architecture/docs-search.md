---
id: sunny-docs-search
type: component
status: active
created: 2026-08-25
tags: [feature, llm, briefing, docs, component]
---

# Docs Search — Grounding "How Does Sunny Work" Questions

Before this, a question like "how does class setup work" landed in the same general-chat LLM fallback as everything else genuinely open-ended (see [[llm-integration]]) — Claude answered from whatever it happened to recall about a codebase it's never actually seen, with no way to be right about specifics. `docs_search.py` closes that gap: it runs a plain keyword search over Sunny's own architecture docs ahead of every fallback question and, when one matches well, prepends its real content to the prompt so the answer is grounded in what's actually true today, not a guess.

## Status

| Piece | Status |
|-------|--------|
| Keyword search over `sunny-vault/docs/architecture/*.md` | Built — `docs_search.py`'s `search()` |
| Wired into the general-chat LLM fallback | Built — `briefing.py`'s `custom_briefing()`, unconditional on every fallback question |
| Instructed in the system prompt | Built — `sunny-vault/instructions/general-chat.md`'s "Sunny's own documentation" section |

## Why Keyword Scoring, Not a Real Tool-Use Loop

Claude already has one real tool here — web search (see [[llm-integration]]), enabled and left to Claude's own judgment about when to use it. Giving Claude a second tool to fetch a doc file on demand would need a real tool-use loop (send the tool definition, get a `tool_use` block back, run it locally, send a `tool_result`, repeat) — meaningfully more machinery for a problem a plain local search already solves. This is the same "deterministic routing, LLM only for judgment" shape as everything else in this codebase (see [[personal-assistant-vision]]): the search itself is cheap and mechanical (one directory walk, no LLM call), so it runs unconditionally on every fallback question rather than needing Claude to first decide it's needed.

## Why Not Embeddings

A personal, single-user tool with ~25 short architecture docs doesn't need a vector index to find the right one. Plain word-overlap scoring, gated by a minimum-hits threshold (`_MIN_SCORE`), is enough to tell "how does class setup work" from "tell me a joke" — the latter scores 0 against every doc and changes nothing about the prompt. Same reasoning `class_memory.py`/`exam_prep.py` already use for note storage: real, simple, and matched to the actual scale of the problem.

## Scoring, and Why the Corpus Is Narrower Than "All the Docs"

`search()` only looks at `sunny-vault/docs/architecture/*.md` — not `sunny-vault/docs/`'s broader meta docs (`BACKLOG.md`, `CHANGELOG.md`, `DESIGN.md`, `phases.md`, `ABOUT.md`, `system-state.md`) and not `Mind-Map.md`. Those are large, deliberately broad-vocabulary documents (a running history, a single-page overview of every component) that out-scored genuinely specific docs on raw word overlap during testing — a query about class setup was landing on `BACKLOG.md` instead of `class-setup.md` simply because `BACKLOG.md` is long enough to contain a few words from almost any question. Restricting to the one-doc-per-component `architecture/` folder fixed that; a match there is also structurally the right level of detail for a spoken/chat answer anyway (a focused doc, not a whole planning document).

A hit against the doc's own filename (`class-setup.md` matching "class setup" in the query) counts `_FILENAME_MATCH_WEIGHT` (5x) more than an incidental body-text mention — the strongest, cheapest relevance signal available without anything fancier. `_MIN_SCORE` (3) is the gate against noise: a question has to share at least 3 distinct meaningful words with a doc (after stripping stopwords, short words, and "sunny" itself — present in nearly every doc, so not discriminating) before that doc counts as a match at all.

## Where This Doesn't Apply

Every deterministic command/trigger in `assistant.py`'s routing chain (tasks, lists, alarms, `/version`, `setup <x>`, etc.) is answered before this fallback is ever reached — `docs_search.py` only ever sees genuinely open-ended questions, same scope as the rest of `custom_briefing()`'s final `else` branch. It also never touches live state (tasks, calendar, weather, email) — `general-chat.md`'s existing "no live access to Sunny's data" constraint is unchanged; this is static reference documentation, not an exception to it.

## Files

- `sunny_code/components/docs_search.py` — `search()`, `format_for_prompt()`
- `sunny_code/components/briefing.py` — `custom_briefing()`'s LLM fallback, where the result is prepended to the prompt alongside `conversation_memory.format_for_prompt()`
- `sunny-vault/instructions/general-chat.md` — tells Claude what the injected context is and how to use it

## Dependencies

- [[llm-integration]] — the general-chat fallback this enriches, and the existing web-search tool it sits alongside
- [[personal-assistant-vision]] — the "deterministic routing, LLM only for judgment" principle this follows

## Implementation Checklist

- [x] Keyword search over `sunny-vault/docs/architecture/*.md`, filename-weighted, minimum-score gated
- [x] Wired into `custom_briefing()`'s LLM fallback (both streaming and non-streaming paths, since both build the same `prompt` string)
- [x] `general-chat.md` updated so Claude knows what the injected context is and to say so honestly if it doesn't actually answer the question
- [ ] No automatic re-indexing needed — reads files fresh on every call, so a doc edit takes effect immediately, but this also means it never caches; fine at this doc count/traffic level, would need revisiting if either grew by an order of magnitude
