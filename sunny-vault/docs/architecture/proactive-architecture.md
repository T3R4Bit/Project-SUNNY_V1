---
id: sunny-proactive-architecture
type: component
status: active
created: 2026-08-24
tags: [proactive, sensors, rules-engine, context-engine, permissions, component]
---

# Proactive-Architecture Foundation (Layers 1/2/3/5)

The five-layer model from [[personal-assistant-vision]] section 10 describes Sunny's long-term shape: cheap sensors feeding a rules engine, a compact context engine for when an LLM call is actually warranted, and a permission-checked executor — instead of sending everything to an expensive LLM. Before this pass, none of it existed in code (the vision doc's own inline note said so explicitly). This is the first real, working slice: Layers 1, 2, 3, and the permission-check half of Layer 5, wired together end to end with one real (if modest) consumer already running. Layer 4 (an LLM planner deciding what's worth surfacing) and the rest of Layer 5 (a structured-action executor) are still not built — see What's Still Missing below.

## Status

| Piece | Layer | Status |
|-------|-------|--------|
| Sensors (calendar changes, vault file changes) | 1 | Built — `sunny_code/components/sensors.py` |
| Rules engine | 2 | Built — `sunny_code/components/rules_engine.py`, 2 seed rules |
| Context engine | 3 | Built — `sunny_code/components/context_engine.py` |
| Vault write permission levels | 5 (partial) | Built — `sunny_code/components/vault_permissions.py` |
| Suggestion-outcome tracking | — (learning, §12) | Built — `sunny_code/components/suggestion_tracker.py` |
| Scheduled evaluation loop | — | Built — `main.py`'s `rules_engine_loop`, 30 min, gated by `service_registry` |
| Structured-action executor | 5 (rest) | Not built — no real feature calls `vault_permissions.request_vault_write()` yet |
| LLM planner deciding what's worth surfacing | 4 | Not built |

## Sensors (Layer 1)

`sensors.py` — cheap, deterministic, no LLM calls. Two functions today, each owning its own small persisted "what have I seen before" cursor (a JSON file under `sunny-vault/data/state/`, same self-contained-state pattern as `category_store.py`/`location_store.py`):

- `calendar_changes(days_ahead=14) -> List[Dict]` — diffs against `google_calendar.get_events_range()` by event `id`+`updated` timestamp. Returns `[]` if Calendar isn't connected (fail-quiet, same contract as `google_calendar.py` itself). Doesn't detect deletions — Google's `events().list()` just omits a deleted event, indistinguishable from "outside the window"; real deletion tracking needs `syncToken` support, out of scope for this pass.
- `vault_file_changes() -> List[Path]` — mtime scan over `sunny-vault/`, excluding Sunny's own bookkeeping folders (`.obsidian`, `archive`, `log`, `state`, `instructions`) so it reports real content changes (a new note under a future `Classes/` or `Projects/` folder) rather than every internal task/list file rewrite this app already makes constantly on its own. A plain mtime comparison, not a content hash — cheap, and doesn't distinguish a no-op save from a real edit, which isn't worth the extra I/O to fix.

## Rules Engine (Layer 2)

`rules_engine.py` — deliberately a plain ordered list of `(name, condition, action)` tuples, not a DSL or plugin/registration system, matching this project's stated anti-overengineering stance. `evaluate()` runs every sensor once, builds a small shared context dict, and checks each rule's condition against it. Two seed rules today — the only two actually implementable against real sensor data with no new external integration:

- `vault_note_changed` — logs which vault note(s) changed
- `calendar_event_changed` — logs which calendar event(s) changed

Both actions just log (to `sunny-vault/log/rules-engine.md`, append-only, same shape as `health_check.py`'s report log) — nothing acts on Sunny's own initiative yet. The vision doc's other example rules (exam-date study prep, workout-window suggestions) need data sources that don't exist yet (a `Classes/` vault convention, Garmin) — see [[../BACKLOG.md]].

**Scheduled**: `main.py`'s `rules_engine_loop`, every 30 minutes, Discord-independent (same standalone `tasks.loop` pattern as the weekly health check — must run and log regardless of whether Discord is configured), gated by `service_registry.is_enabled("rules_engine")`/`is_autostart("rules_engine")`. Wrapped in `asyncio.to_thread()` since `calendar_changes()` makes a blocking network call.

## Context Engine (Layer 3)

`context_engine.py` — a pure read-time aggregator, no new storage of its own. `build_context(tasks_engine, list_engine)` assembles open tasks (title/tag only, not full descriptions — deliberately small, and there's no priority field to include since tasks dropped priority entirely), every list's name and item count, today's calendar events (title/time only), and real project folder names, from data sources that already exist. `format_context()` renders it as compact plain text sized for dropping straight into an LLM prompt — the actual "instead of sending full history" payoff the vision doc describes. No real caller yet; the next feature that needs cheap "what's going on right now" context calls this instead of re-querying each source itself.

## Vault Write Permissions (Layer 5, partial)

`vault_permissions.py` — the permission-check half of a future executor. Four levels per the vision doc's own definitions (0 read-only, 1 safe edits, 2 controlled organization, 3 destructive), a fixed `operation -> level` table (an unrecognized operation defaults to level 3 — ask, never guess something unfamiliar is safe). Confidence thresholds, also the vision doc's own numbers: >95% auto, 80-95% suggest, <80% ask — applied to levels 1-2 only; level 3 always returns `"ask"` regardless of confidence, a hard rule from the vision doc's own Level 3 definition, not a confidence-band consequence.

`request_vault_write(operation, confidence, description) -> "auto"|"suggest"|"ask"` is the one entry point — it classifies **and logs** every call (not just autos, matching `llm_client.log_llm_call()`'s "log every attempt" reasoning), to `sunny-vault/log/vault-edits.md`. It only decides; the caller is responsible for actually performing the write. No real caller exists yet — the knowledge health check (when it moves past reporting into suggesting/performing cleanup) is the natural first one.

## Suggestion-Outcome Tracking

`suggestion_tracker.py` — not a layer in the diagram, but the "Learning From Behavior" piece from vision doc §12. `record_suggestion(kind, content) -> id`, `record_outcome(id, outcome)` where outcome is `accepted`/`rejected`/`ignored`/`snoozed`, and `acceptance_rate(kind, days=30)` for a future feature to check before deciding how aggressively to keep suggesting something. Append-only vault log (`sunny-vault/log/suggestions.md`), same pattern as the rules-engine log. First real caller: `briefing_api.py`'s `/morning`/`/evening` routes call `record_suggestion("morning_brief"|"evening_brief", briefing)` and return the id in the response; `POST /api/briefing/feedback` maps a dashboard's helpful/not_helpful vote to `record_outcome(id, "accepted"|"rejected")`.

## What's Still Missing

- **Layer 4 (LLM planner)** — nothing here decides "is this worth interrupting Keaton about" using an LLM; the rules engine's actions are hardcoded logging, not judgment calls.
- **The rest of Layer 5 (structured-action executor)** — `vault_permissions.py` decides, nothing executes. The vision doc's `LLM -> Structured Action -> Permission Check -> Executor -> Result -> Memory/Log` pipeline only has the "Permission Check" and "Memory/Log" pieces built.
- **More sensors** — GitHub webhooks, file-change watchers beyond the vault itself, Garmin — all still unbuilt, most gated on external accounts (see [[../BACKLOG.md]]).
- **More rules** — anything needing exam dates, workout windows, or opportunity sources waits on those data sources existing first.

## Files

- `sunny_code/components/sensors.py`, `rules_engine.py`, `context_engine.py`, `vault_permissions.py`, `suggestion_tracker.py`
- `sunny_code/main.py` — `rules_engine_loop`
- `sunny_code/components/service_registry.py` — `rules_engine` added as a togglable service

## Dependencies

- [[personal-assistant-vision]] — the design this implements a first slice of
- [[google-integration]] — `calendar_changes()`'s only real external dependency
- [[service-orchestration]] — the loop's enable/autostart gating
- [[health-check]] — the append-only log pattern both `rules_engine.py` and `vault_permissions.py`/`suggestion_tracker.py` follow

## Implementation Checklist

- [x] `sensors.py` — calendar + vault file change detection, self-contained cursors
- [x] `rules_engine.py` — plain rule-list evaluator, 2 seed rules, append-only activity log
- [x] `context_engine.py` — read-time aggregator + compact text formatter
- [x] `vault_permissions.py` — 4 levels, confidence thresholds, level-3 hard override, full logging
- [x] `suggestion_tracker.py` — record/outcome/acceptance-rate
- [x] Scheduled 30-minute evaluation loop, service-registry gated
- [ ] A real caller for `vault_permissions.request_vault_write()` (the knowledge health check is the natural first one — see [[../BACKLOG.md]])
- [x] A real caller for `suggestion_tracker.record_suggestion()` — `briefing_api.py`'s `/morning`/`/evening` routes plus `POST /api/briefing/feedback`
- [ ] Layer 4 (LLM planner) and the rest of Layer 5 (executor)
