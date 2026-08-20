---
id: sunny-llm-readiness
type: architecture
status: active
created: 2026-08-20
tags: [llm, claude, readiness, prerequisites, architecture]
---

# LLM Readiness — What's Needed Before Turning On Any LLM Feature

Project SUNNY's design philosophy is "no LLM, plain pattern matching" everywhere except a small set of judgment tasks where an LLM is the explicit, deliberate escalation path (see [[llm-integration]]). This doc is the concrete checklist for what has to exist *before* any of those tasks go live — split into what's safety-rail infrastructure (buildable and built ahead of time), what's an external/manual step only the account owner can do, and what's an actual LLM-powered *feature* (deliberately not built yet — building one is a separate decision from building the rails it needs).

## Built (infrastructure — tested, nothing user-facing calls it yet)

| Piece | File | What it does |
|---|---|---|
| Spend tracking + circuit breaker | `sunny_code/components/token_tracker.py` | Records every call's tokens/cost into `sunny.db`'s `token_usage` table (per-model breakdown); `check_budget()` refuses further calls once `daily_spend_cap`/`monthly_spend_cap` (`.env`, config.py) is hit |
| Safety-gated Claude client | `sunny_code/components/llm_client.py` | `ask_claude(prompt, model, ...)` — the one function any future feature must call through. Honest "not configured" handling, budget-gated, auth-failure latch (stops all calls until restart on an invalid key), never raises |
| Vault usage logging | `llm_client.log_llm_call()` | Appends a timestamped prompt/response record to `sunny-vault/log/llm-usage.md` on every real call — the mechanism BACKLOG.md asked for ("all chats forced to an llm... get a copy... logged with a time stamp into the obsidian vault"). Not called by anything yet since no feature makes real calls yet |
| Live spend visibility | `dashboard.py`: `GET /api/dashboard/spend/today`, `/spend/month` | Previously hardcoded to `$0.00` — now reads real numbers from `token_tracker` |
| Setup guide + status tracking | `setup_guides.py` ("setup claude"/"setup llm"), `key_status.py` | Same "setup \<name\>" pattern as every other integration; `CLAUDE_API_KEY` was already tracked in `key_status.py`'s startup summary before this pass |
| Concurrency guard | `llm_client.py`: `asyncio.Semaphore(1)` | Lightweight stand-in for the "Priority Scheduler" backlog item — caps in-flight LLM calls at 1. Good enough for a single-user assistant with no concurrent LLM-triggering surface today; revisit if phone-call-interrupts-briefing (or similar) becomes real |

All of the above has real, automated tests (scratch-DB circuit-breaker behavior, mocked SDK auth/rate-limit failures, vault log format, live HTTP endpoint checks) — see the test run in this change's session, not committed as a permanent test file since it exercises infrastructure with no live feature attached yet.

## Still needed before flipping on any specific feature

- **An actual Claude API key** — `console.anthropic.com`, external, user action. Nothing above requires one to exist; everything degrades to an honest "not configured" without it.
- **A second, account-level hard spend cap** — set at `console.anthropic.com`, external, user action. The in-app cap (`token_tracker.check_budget()`) is self-tracked from a local price table, not authoritative Anthropic billing — the account-level cap is the real backstop if the two ever diverge.
- **Real system prompts** for whichever task ships first (Email Triage, Task Interpretation, Freeform Phone Conversation, or Email Reply Drafting — see [[llm-integration]] for each one's draft prompt). None are finalized/tested against a live model yet.
- **Actually wiring `ask_claude()` into a feature's command path** — building the client is not the same as a feature using it. This is a deliberate, separate decision per task.
- **Discord `#warnings` alerting** on the error paths in `llm_client.py` — today those only go to the app log, not Discord, unlike the rest of the app's alerting.
- A real Priority Scheduler, **only if** a genuine concurrent-LLM-caller scenario shows up (e.g. [[phone]] hardware interrupting a briefing mid-playback) — not needed today, the semaphore stand-in covers the current single-caller reality.

## Explicitly deferred — these ARE "adding an LLM," not prerequisites for it

Pulled from [[llm-integration]] and BACKLOG.md. Each of these needs the infrastructure above to exist (now true) but is itself a feature decision, not infrastructure — out of scope for this pass by the very framing of "what's needed *before* adding an LLM":

- **Email Triage**, **Task Interpretation**, **Freeform Phone Conversation**, **Email Reply Drafting** — the four tasks in [[llm-integration]]
- **Storm mode** (BACKLOG.md) — "Only on request weather is no longer being pulled by the API, it switches to an LLM"
- **Project system's Y/N handoff** (BACKLOG.md) — "YES = all hard coded is done and chat switches to LLM"
- **Weekly system health function** (BACKLOG.md) — "runs once a week at sunday 4am (this is a llm)" — log compaction, error review, Discord report

## Not related to LLM readiness (separate backlog items)

A few BACKLOG.md items sit near the LLM ones but don't depend on this infra at all — noted here only so they aren't confused for blocked-on-LLM: Location optimization (GPS pinging), Vacation mode (hardware-gated, no clock device exists), Morning prep (briefing pre-compute timing), Service Orchestration's per-service toggle/autostart, and "any API with usage gets a chart" (a Discord visualization — could reuse `token_tracker`'s data shape once built, but isn't LLM-specific).

## Dependencies

- [[llm-integration]] — the full task-by-task design this checklist supports
- [[../BACKLOG.md]] — source of the deferred items above
- [[discord-bot]] — where Discord alerting would land once wired
