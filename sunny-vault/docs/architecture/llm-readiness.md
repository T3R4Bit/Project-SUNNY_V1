---
id: sunny-llm-readiness
type: architecture
status: active
created: 2026-08-20
tags: [llm, claude, readiness, prerequisites, architecture]
---

# LLM Readiness — What's Needed Before Turning On Any LLM Feature

Project SUNNY's design philosophy is "no LLM, plain pattern matching" everywhere except a small set of judgment tasks where an LLM is the explicit, deliberate escalation path (see [[llm-integration]]). This doc is the concrete checklist for what has to exist *before* any of those tasks go live — split into what's safety-rail infrastructure (buildable and built ahead of time), what's an external/manual step only the account owner can do, and what's an actual LLM-powered *feature* (a separate decision from building the rails it needs — some of those decisions have since been made, see the Built table below; others, like Email Triage, are still deliberately not built).

## Built (infrastructure, now with several real feature callers)

| Piece | File | What it does |
|---|---|---|
| Spend tracking + circuit breaker | `sunny_code/components/token_tracker.py` | Records every call's tokens/cost into `sunny.db`'s `token_usage` table (per-model breakdown); `check_budget()` refuses further calls once `daily_spend_cap`/`monthly_spend_cap` (`.env`, config.py) is hit |
| Safety-gated Claude client | `sunny_code/components/llm_client.py` | `ask_claude(prompt, model, ...)` — the one function any future feature must call through. Honest "not configured" handling, budget-gated, auth-failure latch (stops all calls until restart on an invalid key), never raises |
| Vault usage logging | `llm_client.log_llm_call()` | Appends a timestamped record to `sunny-vault/log/llm-usage.md` on **every** `ask_claude()` attempt, not just successes — the mechanism BACKLOG.md asked for ("all chats forced to an llm... get a copy... logged with a time stamp into the obsidian vault"), extended 2026-08-20 to cover all 8 exit paths (not-configured, budget-exceeded, auth/rate/connection errors, etc.) so refused/failed calls are visible for spotting hardcode-able patterns |
| Vault-loaded system prompts | `sunny_code/components/instructions.py` | `ask_claude(purpose=...)` auto-loads its system prompt from `sunny-vault/instructions/{purpose}.md` — hand-editable, no redeploy, exact-match by purpose name (not a search/RAG system). See [[llm-instructions]] |
| Live spend visibility | `dashboard.py`: `GET /api/dashboard/spend/today`, `/spend/month` | Previously hardcoded to `$0.00` — now reads real numbers from `token_tracker` |
| Setup guide + status tracking | `setup_guides.py` ("setup claude"/"setup llm"), `key_status.py` | Same "setup \<name\>" pattern as every other integration; `CLAUDE_API_KEY` was already tracked in `key_status.py`'s startup summary before this pass |
| Concurrency guard | `llm_client.py`: `asyncio.Semaphore(1)` | Lightweight stand-in for the "Priority Scheduler" backlog item — caps in-flight LLM calls at 1. Good enough for a single-user assistant with no concurrent LLM-triggering surface today; revisit if phone-call-interrupts-briefing (or similar) becomes real |
| Weekly system health function | `sunny_code/components/health_check.py` | The first real caller of `ask_claude()` — see [[health-check]]. Moved here from "Explicitly deferred" below since it's now built, not just infrastructure for a future feature |
| Project wizard scaffold generation | `sunny_code/components/project_engine.py` | `purpose="project_scaffold"`, live 2026-08-23. Moved here from "Explicitly deferred" below — see [[project-system]] |
| Storm Mode web-searched weather | `sunny_code/components/storm_mode.py` | `purpose="storm_mode"`, live 2026-08-24. Moved here from "Explicitly deferred" below |
| Exam-prep study review | `sunny_code/components/exam_prep.py` | `purpose="exam_prep_review"`, live 2026-08-24 — see [[exam-prep]] |
| Class setup syllabus parsing | `sunny_code/components/syllabus_parser.py` | `purpose="syllabus_parse"`, live 2026-08-25 — see [[class-setup]] |

The core infrastructure rows (spend tracking through the concurrency guard) have real, automated tests (scratch-DB circuit-breaker behavior, mocked SDK auth/rate-limit failures, vault log format, live HTTP endpoint checks) — not committed as a permanent test file since at the time it exercised infrastructure with no live feature attached yet. That's no longer true of the infra itself — five real features (health check, project wizard, Storm Mode, exam-prep review, syllabus parsing) now call through it daily.

## Still needed before flipping on any specific feature

- ~~An actual Claude API key~~ — **done, 2026-08-21.** `CLAUDE_API_KEY` is configured; `ask_claude()` is live.
- **A second, account-level hard spend cap** — set at `console.anthropic.com`, external, user action. The in-app cap (`token_tracker.check_budget()`) is self-tracked from a local price table, not authoritative Anthropic billing — the account-level cap is the real backstop if the two ever diverge. Still outstanding.
- **Real system prompts** for whichever task ships next (Email Triage, Task Interpretation, or Email Reply Drafting — see [[llm-integration]] for each one's draft prompt). Freeform Conversation, the project wizard, Storm Mode, exam-prep review, and syllabus parsing all already have theirs, live — the three original catalog tasks above are still unwritten/untested against a live model.
- **Actually wiring `ask_claude()` into a feature's command path** — done for Freeform Conversation's Q&A slice (`briefing.py`'s `custom_briefing()` fallback, live 2026-08-21), the project wizard, Storm Mode, exam-prep review, and syllabus parsing. Still a deliberate, separate per-task decision for Email Triage, Task Interpretation, and Email Reply Drafting.
- **Discord `#warnings` alerting** on the error paths in `llm_client.py` — today those only go to the app log, not Discord, unlike the rest of the app's alerting. Still outstanding.
- A real Priority Scheduler, **only if** a genuine concurrent-LLM-caller scenario shows up (e.g. [[phone]] hardware interrupting a briefing mid-playback) — not needed today, the semaphore stand-in covers the current single-caller reality.

## Explicitly deferred — these ARE "adding an LLM," not prerequisites for it

Pulled from [[llm-integration]] and BACKLOG.md. Each of these needs the infrastructure above to exist (now true) but is itself a feature decision, not infrastructure — out of scope for this pass by the very framing of "what's needed *before* adding an LLM":

- **Email Triage**, **Task Interpretation**, **Freeform Phone Conversation (action-taking half)**, **Email Reply Drafting** — the still-unbuilt tasks in [[llm-integration]]

~~Storm mode~~ and ~~Project system's Y/N handoff~~ (both BACKLOG.md items) have since shipped — see the Built table above — and are no longer deferred.

## Not related to LLM readiness (separate backlog items)

A few BACKLOG.md items sit near the LLM ones but don't depend on this infra at all — noted here only so they aren't confused for blocked-on-LLM: Location optimization (GPS pinging — built, see [[location]], no LLM involved), Vacation mode (hardware-gated, no clock device exists), Morning prep (briefing pre-compute timing), Service Orchestration's per-service toggle/autostart, and "any API with usage gets a chart" (a Discord visualization — could reuse `token_tracker`'s data shape once built, but isn't LLM-specific).

## Dependencies

- [[llm-integration]] — the full task-by-task design this checklist supports
- [[llm-instructions]] — vault-loaded system prompts, built alongside this
- [[health-check]] — the first real feature to use this infrastructure
- [[project-system]], [[exam-prep]], [[class-setup]] — later real features built on this same infrastructure
- [[../BACKLOG.md]] — source of the deferred items above
- [[discord-bot]] — where Discord alerting would land once wired
