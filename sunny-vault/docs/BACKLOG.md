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
- [ ] Per-service **toggle while running** — enable/disable an individual service (e.g. voice I/O, briefing scheduler) without restarting the whole Sunny process. Likely exposed via the dashboard and/or a CLI command.
- [ ] **Config for "start on Sunny launch" per service** — a settings file (e.g. `services.yaml` or a section in the existing config) marking each service as AutoStart-on-boot vs. manual-start-only, read at launch to decide what to bring up
- [x] Location optimization. every time I ask for something and it needs my location it always pings my current location with my phone. But at a 30minute interval unless deemed immediate
      OR, find a completely free way to ping the location of my phone
      *(built 2026-08-20: [OwnTracks](https://owntracks.org/) — free, self-hosted, no third-party cloud. `POST /api/location/owntracks` receives GPS pushes on the phone's own schedule; `location_store.get_coordinates(max_age_minutes=30)` implements the "30-minute interval unless immediate" framing as a staleness window on the receiving end, falling back to the static city if there's no fresh fix. See [[architecture/location]].)*
- [x] Storm mode: Only on request weather is no longer being pulled by the API, It switches to an LLM
      on activation it asks for an "update interval" and updates me on the current weather every interval IE 10min then also any updates or changes to the weather
      also asks for how long storm mode should be active for before auto updates turn off
      *(built 2026-08-23: `storm_mode.py` — "storm mode"/"stop storm mode" in Discord, asks interval then duration, posts a real web-searched update (`ask_claude(enable_web_search=True)`, not the weather API) every interval until the duration elapses or it's stopped early. Discord-only, handled directly in `discord_bot.py`'s `on_message` — see that module's docstring for why.)*
- [ ] A vacation mode so that my local clock is not waiting every day for goodnight / morning
- [x] morning prep, preps brief before My  alarm goes off to reduce delay, but Email is pulled right before alarm (5min max) to get the latest info
      *(built 2026-08-23: `discord_bot.py`'s `scheduled_check_loop` looks ahead for the next active alarm and, within 5 minutes of it, kicks off `BriefingEngine.prewarm_morning_briefing()` in the background — a real "good morning"/"im up" shortly after returns the cached result instantly instead of waiting on live weather/calendar/email calls, while still keeping email fresh at wake-up rather than fetched hours early.)*
- [x] Project system creates a project folder in obsidian under vault/project/project-name/ and asks for a short description of what it is (ALL OF THIS IS HARD CODED) with more then one variation of responses or questions to keep it human. then askes if you would like to build not NO = end of conversation, YES = all hard coded is done and chat switches to LLM
      *(built 2026-08-23: `project_engine.py` + `assistant.py`'s wizard — name → description → sections → recap and a real yes/no confirm (a firm "no" ends it, the LLM is never called), each question picked at random from a few phrasings. "YES" hands off to one `ask_claude` call that drafts a real multi-file folder under `sunny-vault/projects/`.)*
- [x] ANY api with usage gets a chart  that is in its own discord channel with a leaderboard type screen (a persestant message that is a chart that updates) and pings me in that channel when a token will expire or usage is running within 70% of my self imposed limit of spending
      *(built 2026-08-23: `usage_chart.py` renders the chart; `discord_bot.py`'s `refresh_usage_dashboard()` keeps one pinned message in its own channel updated hourly (same pinned-message pattern as the task/health dashboards), and `check_usage_alerts()` pings that channel once a day if spend crosses 70% of the daily/monthly self-imposed cap or a key is expiring within a week. Not a literal multi-item "leaderboard" layout — one chart, one alert line — but covers the persistent-dashboard-plus-alerting intent.)*
- [x] All chats that were forced to an llm (except weather mode or project builds) get a copy of the message logged with a time stamp into the obsidian vault — the logging mechanism is built (`llm_client.log_llm_call()` → `sunny-vault/log/llm-usage.md`), tested, and fires automatically on **every** `ask_claude()` attempt, not just successes (2026-08-20: extended to log all 8 exit paths — not-configured, budget-exceeded, auth/rate/connection errors, etc. — with a `status` field, specifically so refused/failed calls are visible for spotting hardcode-able patterns). First real traffic is the weekly health check below.
- [x] A system health function that runs once a week at sunday 4am (this is a llm) - compacts logs checks for any errors anything that was not phrased in hardcode and forced to switch to an LLM gets sent to me in discord as a report and a message to my good morning on sunday tells me to check it (not what it is) also checks if any api keys will expire within the next week also looks for way to improve the system with usage (try to keep low for usage)
      *(built 2026-08-20: `health_check.py`, scheduled every Sunday 4am from `main.py` — compacts `sunny.log` error counts, `requests.md`/`llm-usage.md` 7-day category counts, and key-expiry checks into a small summary, has Haiku write the report, posts it to #warnings if Discord's connected, and always logs to `sunny-vault/log/health-checks.md` either way. The morning briefing gets a "check it" nudge with no content, exactly per this item's own wording — say "health check" to see the actual report. See [[architecture/health-check]].)*
- [x] Piper TTS — `/speak <text>` posts back a playable audio attachment, free/local, no API key
      *(built 2026-08-20: real Discord slash command via `discord.app_commands`, the bot's first — see [[architecture/tts-piper]].)*
- [x] "later I want to be able to just talk to it in a discord vc with a /join command for the bot" — live, real-time voice conversation in a Discord voice channel, not one-shot `/speak` attachments
      *(built 2026-08-20: `/join`/`/leave`, live conversation via Vosk STT (free, local) + the existing Piper TTS, routed through the same `assistant.handle_message()` every other interface uses. See [[architecture/voice-join]].)*
- [x] Genuinely open-ended questions (text or voice) that don't match any real command/data topic get a real Claude answer instead of a canned "I don't have a real answer"
      *(built 2026-08-21: `briefing.py`'s `custom_briefing()` fallback now calls `ask_claude(purpose="general_chat")` — the first real, user-facing feature to use the `llm_client.py` safety rails built earlier. System prompt: `sunny-vault/instructions/general-chat.md`, hand-editable. Model/length/creativity are `.env`-tunable (`LLM_CHAT_MODEL`/`LLM_CHAT_MAX_TOKENS`/`LLM_CHAT_TEMPERATURE`). See [[architecture/llm-integration]].)*
- [ ] Can you track Claude usage and limits with the API — real-time rate-limit/usage data straight from Anthropic's own API response headers, not just this app's self-tracked cost estimate
      *(different from the spend dashboard that already exists — `GET /api/dashboard/spend/today`/`/spend/month` reports `token_tracker.py`'s own local cost calculation, not Anthropic's authoritative usage/rate-limit numbers. Not yet built.)*
- [ ] Add A "SYSTEM OFFLINE" screen to pi os that is big  and can be seen whenever main server is offline also allow pi to send an error message through the discord bot to server saying server went offline
      *(half built, separately, on the Pi-client side: the device now detects its own dirty restart and reports it through `/api/pi/crash-report` to the #warnings channel — the big on-device "SYSTEM OFFLINE" screen itself isn't built.)*
- [x] "good morning sunny" "hey sunny im up" "im up sunny" "good night sunny" "hey sunny, im going to bed" or anything variation of them (add in a lot of variations) to trigger good morning and goodnight breifs that we build already
      *(built 2026-08-23: `assistant.py`'s `_MORNING_TRIGGERS`/`_EVENING_TRIGGERS` now cover these and a few more; voice already strips the wake phrase before this is checked, so the bare forms ("im up", "going to bed") also work there.)*
- [x] Every hour send in a new image of the current claude usage in discord and remove the old one
      *(built 2026-08-23, as one persistent edited-in-place message instead of post-new-then-delete-old — see the usage-chart item above; functionally the same "always current, no stale copies left behind" result.)*