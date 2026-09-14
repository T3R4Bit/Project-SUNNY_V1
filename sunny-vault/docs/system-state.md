---
id: sunny-state
type: state
status: active
created: 2026-08-18
tags: [state, runtime, config]
---

# System State — How Sunny Actually Tracks It

This file used to describe a planned single-file `state.json`/`state.md` mechanism (sleep/wake tracking, a Notion sync cursor, a token-threshold circuit breaker with an interactive continue/halt prompt). None of that exists in code — it was written before the real approach took shape. This is a rewrite describing what's actually there today, as a map for anyone (human or Sunny) looking for "where does X get tracked."

There is no single state file. Each kind of state lives wherever fits it best, following the same pattern every component in this codebase uses: vault-markdown for anything a human should be able to read/edit directly, SQLite for anything needing frequent automatic background writes.

## Tasks and Lists — vault-markdown, one file per item

`sunny-vault/data/state/tasks/<slug>.md`, `sunny-vault/data/state/lists/<slug>.md` — one file per task/list, frontmatter + body, written via `sunny_code/components/vault_io.py`'s `atomic_write_text` (temp file + `os.replace()`, safe against partial writes). See [[architecture/vault-storage]], `tasks_db.py`, `lists_db.py`. Finished/deleted tasks move to `sunny-vault/data/archive/finished/` or `archive/deleted/` rather than being erased — see [[TASK_SYSTEM.md]].

## Alarms/Reminders — SQLite, plus a read-only vault mirror

`sunny.db`'s `scheduled_items` table (`scheduled_db.py`) is the real source of truth — it needs reliable writes from a 30-second background due-check loop, which doesn't suit a hand-editable markdown file. `sunny-vault/data/state/alarms-reminders.md` is a generated read-only snapshot (`scheduled_vault_mirror.py`) for visibility in Obsidian — nothing reads it back in.

## Categories — a small JSON file, not the vault

`categories.json` at the project root (`category_store.py`) — the free-form task-category list (`General`/`School`/`Motorsports` by default), editable from any interface ("add category `<name>`"/"remove category `<name>`"/"my categories" in terminal chat, Discord text, or voice) as well as `/category` in Discord. Plain JSON, not frontmatter+markdown, since it's runtime config rather than vault content — same reasoning as `location_store.py`.

## Health Check — a marker file + an append-only log

`sunny-vault/data/state/health-check.md` — a small frontmatter-only marker (`id`/`type`/`status`: `"unacknowledged"`/`"acknowledged"`/`updated_at`) tracking whether the morning briefing still needs to nudge about a new report. `sunny-vault/log/health-checks.md` is the actual append-only report history, entries separated by `---`. See `health_check.py`, [[architecture/health-check]]. This marker-file shape is the template for any new small "is there something pending" state.

## Token Usage / Spend — SQLite

`sunny.db`'s `token_usage` table (`dashboard.py`'s schema, written by `token_tracker.py`) — per-day, per-model prompt/completion token counts and self-calculated cost. `check_budget()` reads this before every `ask_claude()` call; it's a real hard-cap circuit breaker (refuses further calls once the daily/monthly cap is hit, resets automatically when the day/month rolls over), **not** the interactive "continue or halt" prompt this file used to describe — no such prompt exists. See [[architecture/llm-integration]].

## LLM Call Log — append-only vault log

`sunny-vault/log/llm-usage.md` (`llm_client.log_llm_call()`) — every `ask_claude()` attempt, success or failure, with a `status` field (not-configured, budget-exceeded, auth/rate/connection error, success, etc.), specifically so refused/failed calls are visible for spotting patterns worth hardcoding. Same shape for `sunny-vault/log/requests.md` (`request_log.py`) — logs what a user asked for that Sunny couldn't fulfill with real data, e.g. weather with no API key set.

## Location — a small state file, not SQLite or the vault proper

`location_store.py` — the last GPS fix received from OwnTracks (`POST /api/location/owntracks`), with a staleness window (`get_coordinates(max_age_minutes=30)`) falling back to a configured static city if the fix is too old. See [[architecture/location]].

## What isn't tracked (confirmed, not just undocumented)

- **Sleep/wake state** (`awake`/`sleeping`/`in_bed`) — not tracked anywhere in code. The Discord activity log's planned `#state-changes` channel is blocked on this not existing (see [[BACKLOG.md]]).
- **Notion sync cursor** — no Notion integration exists at all.
- **API heartbeat timestamps** (last-successful-call-per-service) — not tracked as a standalone structure; each integration's "connected or not" is checked live at call time instead (e.g. `google_auth.is_connected()`, `key_status.missing_api_keys()`), not from a cached heartbeat.

If any of these end up genuinely needed, the marker-file pattern above (health-check.md) is the template to reuse rather than reintroducing a single monolithic state file.
