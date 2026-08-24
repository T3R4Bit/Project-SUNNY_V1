---
id: sunny-backlog
type: planning
status: active
created: 2026-08-18
tags: [backlog, later, deferred, planning]
---

# Later / Backlog

Items worth doing but not blocking the current phase. Pull items into [[phases.md]] when their dependencies are actually in front of you.

---

## Service Orchestration

**Problem**: Right now there's no single entry point that brings up every Sunny service together, and no way to manage them individually once running.

- [x] Package Sunny as a **systemd unit** (`Restart=always`) so it survives crashes and starts on boot — built, see `SETUP_LINUX.md`, deployed on the Lenovo with a scoped (non-root) sudoers rule for restart/status
- [x] Single command/entry point that starts **all** services together (briefing engine, dashboard, task system, voice I/O, etc.) — `run.sh server` does this today; still no fine-grained per-service control (see the two items below, still open)
- [x] Per-service **toggle while running** — enable/disable an individual service (e.g. voice I/O, briefing scheduler) without restarting the whole Sunny process. Likely exposed via the dashboard and/or a CLI command.
      *(built: `service_registry.py` — a flat JSON file (`service_registry.json`), same shape as `category_store.py`. Six togglable services: `dashboard_refresh`, `scheduled_check`, `usage_refresh`, `health_check`, `morning_prep`, `voice_join`. `/service <name> enable|disable` in Discord flips it live — every loop checks `is_enabled()` at the top of each tick, so it takes effect within one tick, not just at boot. `/services` shows the full status. See [[architecture/service-orchestration]].)*
- [x] **Config for "start on Sunny launch" per service** — a settings file (e.g. `services.yaml` or a section in the existing config) marking each service as AutoStart-on-boot vs. manual-start-only, read at launch to decide what to bring up
      *(built: same `service_registry.json`, a second `autostart` flag per service alongside `enabled`. `/service <name> autostart_on|autostart_off`. Checked once at boot (`main.py`'s health-check loop, `discord_bot.py`'s `on_ready`) to decide whether to `.start()` a given `tasks.loop` at all — flipping it later takes effect on the next restart, no manual-start path exists yet for a loop that was never started.)*
- [x] Location optimization. every time I ask for something and it needs my location it always pings my current location with my phone. But at a 30minute interval unless deemed immediate
      OR, find a completely free way to ping the location of my phone
      *(built 2026-08-20: [OwnTracks](https://owntracks.org/) — free, self-hosted, no third-party cloud. `POST /api/location/owntracks` receives GPS pushes on the phone's own schedule; `location_store.get_coordinates(max_age_minutes=30)` implements the "30-minute interval unless immediate" framing as a staleness window on the receiving end, falling back to the static city if there's no fresh fix. See [[architecture/location]].)*
- [x] Storm mode: Only on request weather is no longer being pulled by the API, It switches to an LLM
      on activation it asks for an "update interval" and updates me on the current weather every interval IE 10min then also any updates or changes to the weather
      also asks for how long storm mode should be active for before auto updates turn off
      *(built 2026-08-23: `storm_mode.py` — "storm mode"/"stop storm mode" in Discord, asks interval then duration, posts a real web-searched update (`ask_claude(enable_web_search=True)`, not the weather API) every interval until the duration elapses or it's stopped early. Discord-only, handled directly in `discord_bot.py`'s `on_message` — see that module's docstring for why.)*
- [x] A vacation mode so that my local clock is not waiting every day for goodnight / morning
      *(built: "vacation mode on"/"off" from any interface (or `/vacation` in Discord), stored in `service_registry.json`. While on, `discord_bot.py`'s `scheduled_check_loop` skips the morning-prep lookahead entirely — no pre-warming, no proactive nudging. Saying "good morning"/"good night" directly still works as normal; this only suppresses the proactive daily-cycle waiting, not an explicit request.)*
- [x] morning prep, preps brief before My  alarm goes off to reduce delay, but Email is pulled right before alarm (5min max) to get the latest info
      *(built 2026-08-23: `discord_bot.py`'s `scheduled_check_loop` looks ahead for the next active alarm and, within 5 minutes of it, kicks off `BriefingEngine.prewarm_morning_briefing()` in the background — a real "good morning"/"im up" shortly after returns the cached result instantly instead of waiting on live weather/calendar/email calls, while still keeping email fresh at wake-up rather than fetched hours early.)*
- [x] Project system creates a project folder in obsidian under vault/project/project-name/ and asks for a short description of what it is (ALL OF THIS IS HARD CODED) with more then one variation of responses or questions to keep it human. then askes if you would like to build not NO = end of conversation, YES = all hard coded is done and chat switches to LLM
      *(built 2026-08-23: `project_engine.py` + `assistant.py`'s wizard — name → description → sections → recap and a real yes/no confirm (a firm "no" ends it, the LLM is never called), each question picked at random from a few phrasings. "YES" hands off to one `ask_claude` call that drafts a real multi-file folder under `sunny-vault/projects/`.)*
- [x] ANY api with usage gets a chart  that is in its own discord channel with a leaderboard type screen (a persestant message that is a chart that updates) and pings me in that channel when a token will expire or usage is running within 70% of my self imposed limit of spending
      *(built 2026-08-23: `usage_chart.py` renders the chart; `discord_bot.py`'s `refresh_usage_dashboard()` keeps one pinned message updated hourly, and `check_usage_alerts()` pings once a day if spend crosses 70% of the daily/monthly self-imposed cap or a key is expiring within a week. Not a literal multi-item "leaderboard" layout — one chart, one alert line — but covers the persistent-dashboard-plus-alerting intent. Originally its own dedicated channel; moved into #health the same day, same embed style as the weekly health report (bold key figures, chart image composited via `set_image`) and delete-and-resend instead of edit-in-place, since Discord's embed image cache can hold a stale thumbnail through an attachment-replacing edit. `DISCORD_USAGE_CHANNEL_ID` no longer exists — both now live under `DISCORD_HEALTH_CHANNEL_ID`.)*
- [x] All chats that were forced to an llm (except weather mode or project builds) get a copy of the message logged with a time stamp into the obsidian vault — the logging mechanism is built (`llm_client.log_llm_call()` → `sunny-vault/log/llm-usage.md`), tested, and fires automatically on **every** `ask_claude()` attempt, not just successes (2026-08-20: extended to log all 8 exit paths — not-configured, budget-exceeded, auth/rate/connection errors, etc. — with a `status` field, specifically so refused/failed calls are visible for spotting hardcode-able patterns). First real traffic is the weekly health check below.
- [x] A system health function that runs once a week at sunday 4am (this is a llm) - compacts logs checks for any errors anything that was not phrased in hardcode and forced to switch to an LLM gets sent to me in discord as a report and a message to my good morning on sunday tells me to check it (not what it is) also checks if any api keys will expire within the next week also looks for way to improve the system with usage (try to keep low for usage)
      *(built 2026-08-20: `health_check.py`, scheduled every Sunday 4am from `main.py` — compacts `sunny.log` error counts, `requests.md`/`llm-usage.md` 7-day category counts, and key-expiry checks into a small summary, has Haiku write the report, posts it to #warnings if Discord's connected, and always logs to `sunny-vault/log/health-checks.md` either way. The morning briefing gets a "check it" nudge with no content, exactly per this item's own wording — say "health check" to see the actual report. See [[architecture/health-check]].)*
- [x] Piper TTS — `/speak <text>` posts back a playable audio attachment, free/local, no API key
      *(built 2026-08-20: real Discord slash command via `discord.app_commands`, the bot's first — see [[architecture/tts-piper]].)*
- [x] "later I want to be able to just talk to it in a discord vc with a /join command for the bot" — live, real-time voice conversation in a Discord voice channel, not one-shot `/speak` attachments
      *(built 2026-08-20: `/join`/`/leave`, live conversation via Vosk STT (free, local) + the existing Piper TTS, routed through the same `assistant.handle_message()` every other interface uses. See [[architecture/voice-join]].)*
- [x] Genuinely open-ended questions (text or voice) that don't match any real command/data topic get a real Claude answer instead of a canned "I don't have a real answer"
      *(built 2026-08-21: `briefing.py`'s `custom_briefing()` fallback now calls `ask_claude(purpose="general_chat")` — the first real, user-facing feature to use the `llm_client.py` safety rails built earlier. System prompt: `sunny-vault/instructions/general-chat.md`, hand-editable. Model/length/creativity are `.env`-tunable (`LLM_CHAT_MODEL`/`LLM_CHAT_MAX_TOKENS`/`LLM_CHAT_TEMPERATURE`). See [[architecture/llm-integration]].)*
- [x] Can you track Claude usage and limits with the API — real-time rate-limit/usage data straight from Anthropic's own API response headers, not just this app's self-tracked cost estimate
      *(built: both `llm_client.py` call paths (`with_raw_response.create()` for the non-streaming path, `stream.response.headers` for the streaming one) capture `anthropic-ratelimit-*` headers into `token_tracker.get_latest_rate_limits()` — an in-memory, current-window-only snapshot, not persisted history. Surfaced via `GET /api/dashboard/usage/live`, Discord's `/usage` command (alongside the existing self-tracked chart), and a new "what's my usage" voice/text intent in `assistant.py` that works from any interface, console/Discord/Pi companion alike — see [[architecture/usage-tracking]]. Distinct from `sunny-companion/BUILD_PLAN.md`'s still-open Admin-API dashboard item, which is a different, richer feature (org-level cost_report via a separate Admin API key, rendered as a visual payload on the Pi's screen, not a spoken/text answer).)*
- [ ] Add A "SYSTEM OFFLINE" screen to pi os that is big  and can be seen whenever main server is offline also allow pi to send an error message through the discord bot to server saying server went offline
      *(half built, separately, on the Pi-client side: the device now detects its own dirty restart and reports it through `/api/pi/crash-report` to the #warnings channel — the big on-device "SYSTEM OFFLINE" screen itself isn't built.)*
- [x] "good morning sunny" "hey sunny im up" "im up sunny" "good night sunny" "hey sunny, im going to bed" or anything variation of them (add in a lot of variations) to trigger good morning and goodnight breifs that we build already
      *(built 2026-08-23: `assistant.py`'s `_MORNING_TRIGGERS`/`_EVENING_TRIGGERS` now cover these and a few more; voice already strips the wake phrase before this is checked, so the bare forms ("im up", "going to bed") also work there.)*
- [x] Every hour send in a new image of the current claude usage in discord and remove the old one
      *(built 2026-08-23, as one persistent edited-in-place message instead of post-new-then-delete-old — see the usage-chart item above; functionally the same "always current, no stale copies left behind" result.)*
- [x] move api dashboard to #health channel
      *(this was a leftover duplicate — the two items above (usage chart, hourly image) already document this move happening 2026-08-23. Confirmed directly in code: `DISCORD_USAGE_CHANNEL_ID` no longer exists in `config.py`, and `discord_bot.py`'s `refresh_usage_dashboard()`/`check_usage_alerts()` both post to `discord_health_channel_id`.)*
---

## College / Fitness / Knowledge / Proactivity

Full architecture and rationale in [[architecture/personal-assistant-vision]] — these are the extractable action items, organized by area. Nothing here is scoped or sequenced yet; pull into [[phases.md]] when actually starting one.

**College / opportunity monitoring** ([[architecture/personal-assistant-vision#2-college-ksu-assistant]], [[architecture/personal-assistant-vision#18-opportunity-engine]])

- [ ] Monitor KSU/local sources (events, competitions, scholarships, career fairs) and score opportunities (relevance/timing/deadline/interest) before surfacing anything
      *(blocked: needs the actual sources named — specific RSS feeds, event-calendar URLs, or pages to watch. "KSU/local sources" isn't one API, it's a set of specific things to point a watcher at.)*

**Exam prep** ([[architecture/personal-assistant-vision#3-proactive-test-exam-preparation]])

- [ ] Track exam dates and Obsidian note coverage per class; generate a study plan ~1 week out and a short high-value review the night before
- [ ] Spaced-review pipeline over old material (new → review → weak → retest → mastered)

**Fitness / Garmin** ([[architecture/personal-assistant-vision#4-fitness-physical-life-assistant]], [[architecture/personal-assistant-vision#5-garmin-integration]])

- [ ] Schedule-aware workout window suggestions (free time minus travel/commitments)
- [ ] Garmin sleep/training-load data as context for workout-intensity suggestions (not a medical authority)
      *(blocked: needs an approved Garmin Connect developer API account — that's an application/approval process on Garmin's side, not just an env var. Schedule-aware workout window suggestions just above this don't strictly need Garmin and could be built without it.)*

**Recipes / meals** ([[architecture/personal-assistant-vision#6-recipe-food-system]])

- [ ] Personal recipe preference tracking (liked/disliked, ingredients on hand, cuisine, cost/time)
- [ ] Online recipe discovery filtered by schedule/ingredients/preferences; weekly meal planning around class schedule + configurable campus-meal-plan days
      *(blocked: needs a recipe API key — pick a provider (e.g. Spoonacular, Edamam) and sign up. The preference-tracking item above doesn't need this and could start first.)*

**Obsidian knowledge base** ([[architecture/personal-assistant-vision#7-obsidian-as-sunnys-knowledge-base]], [[architecture/personal-assistant-vision#8-weekly-knowledge-health-check]])

- [x] Permission-leveled vault write access (0 read-only / 1 safe edits / 2 rename-move / 3 destructive-requires-approval) with a confidence threshold (>95% auto, 80-95% suggest, <80% ask) and a log of automatic edits
      *(built: `vault_permissions.py` — `request_vault_write(operation, confidence, description)` classifies and logs every call (not just autos) to `sunny-vault/log/vault-edits.md`. Level 3 always returns "ask" regardless of confidence, per the vision doc's own hard rule. No real caller yet — it only decides, nothing calls it to actually touch the vault on its own initiative today. See [[architecture/proactive-architecture]].)*
- [ ] Extend the weekly health check into a knowledge health check (broken links, orphaned/duplicate/untagged/stale notes)

**Proactivity / hybrid architecture** ([[architecture/personal-assistant-vision#10-hybrid-ai-architecture]], [[architecture/personal-assistant-vision#11-confidence-based-autonomy]], [[architecture/personal-assistant-vision#12-learning-from-behavior]])

- [x] Real Layer-1 sensors (calendar/file-change/GitHub watchers) feeding a Layer-2 rules engine, so proactive suggestions don't require an LLM call per check
      *(built: `sensors.py` (calendar + vault-file change detection, GitHub watchers still not built) + `rules_engine.py` (2 seed rules — vault note changed, calendar event changed — both log-only, no action taken yet). Evaluated on a new 30-minute `main.py` loop. See [[architecture/proactive-architecture]].)*
- [x] A compact structured context-engine state (vs. full history) for when an LLM call is actually needed
      *(built: `context_engine.py`'s `build_context()`/`format_context()` — pure read-time aggregator over tasks/lists/today's calendar/project folders, no new storage. No real caller yet.)*
- [x] Track suggestion outcomes (accepted/rejected/ignored/snoozed) and adjust future suggestion timing/confidence per pattern
      *(built: `suggestion_tracker.py` — `record_suggestion`/`record_outcome`/`acceptance_rate`, append-only vault log. No real caller yet — waits on the first feature that actually emits a proactive suggestion.)*

**Travel intelligence** ([[architecture/personal-assistant-vision#17-travel-commute-intelligence]]) — same gap as the existing commute/traffic item elsewhere in this backlog; not built

- [ ] Calendar-event destination → travel time → leave-time notification, checked near-departure rather than polled continuously
      *(blocked: needs a routing/traffic API key, e.g. Google Maps Platform — separate from Google Sign-In, billed and authenticated per-project via a plain API key, not per-user OAuth. See [[architecture/google-integration]]'s "What This Does NOT Cover" table.)*

**Daily/weekly rollups** ([[architecture/personal-assistant-vision#19-daily-personal-operations]], [[architecture/personal-assistant-vision#20-weekly-review]])

- [ ] Extend the morning briefing with college/fitness/food/opportunity sections
- [ ] A weekly review rollup (school/business/projects/fitness/food) alongside the existing weekly system health check

**Voice pipeline follow-ups** (mostly superseded by what's actually built — see the notes inline in [[architecture/personal-assistant-vision#13-voice-pipeline-revisit-vs-whats-actually-built]] and [[architecture/personal-assistant-vision#15-low-latency-voice-goal]])

- [ ] Streaming/partial-hypothesis STT (the one real latency gap left — LLM/TTS streaming is already built)
- [ ] A delivery/prosody layer that varies tone/pace by message type (reminder vs. opportunity vs. warning), beyond the text-register rewrite already done in `general-chat.md`
- [ ] Revisit Kokoro once real GPU hardware exists (measured RTF 2.40 CPU-only this session vs. Piper's 0.06 — not viable today)

---

## Sunny Companion hardware

Tracked directly in `sunny-companion/BUILD_PLAN.md` (a real phase-by-phase checklist, not backlog material) — see Phase 4 for the face renderer/audio-visualizer work specifically. Not duplicated here to avoid the two drifting apart.
