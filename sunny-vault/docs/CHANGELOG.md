---
id: sunny-changelog
type: changelog
status: active
created: 2026-08-23
tags: [changelog, history]
---

# Changelog

Running log of real changes, most recent first. Not every commit — the milestones worth remembering later. See [[BACKLOG.md]] for what's next, [[phases.md]] for the build plan this rolled up from.

---

## 2026-08-25

**Usage dashboard gets its own optional Discord channel back**
- New `DISCORD_USAGE_CHANNEL_ID` setting (`config.py`) — the persistent hourly usage dashboard and daily spend-cap alerts (`refresh_usage_dashboard()`/`check_usage_alerts()` in `discord_bot.py`) now post there if set, falling back to `#health` (`DISCORD_HEALTH_CHANNEL_ID`) then the chat channel if not, so an existing setup that never touches the new variable keeps behaving exactly as it did after the 2026-08-23 consolidation into `#health`.
- This setting existed once before and was deliberately removed during that consolidation — re-added by request, but as a fallback *ahead of* `#health` rather than a hard replacement, so both usages (shared or split) work depending on whether it's set.
- `run.sh`'s `.env` template, `discord-bot.md`'s channel reference table, and `usage-tracking.md` all updated to match.

**Full documentation audit — every doc checked against real current code**
- All ~47 real doc files (root README/QUICKSTART/SETUP_LINUX, every `sunny-vault/docs/` meta doc, all 27 `architecture/` docs, all `instructions/` system prompts, `sunny-companion`'s two docs) checked claim-by-claim against the actual source, not each other's assumptions. Found and fixed genuine drift in the large majority of them — stale "not built"/"built" status flips (`clock.md`'s Phase 3 checklist was marked all-`[x]` while no hardware has even been ordered; `dashboard.md` still said spend was "hardcoded to $0" months after real spend tracking shipped; the Pi companion's TTS demo and pygame renderer prototype were both marked "not built" despite existing and working), removed `--priority`/task-priority references left over from its 2026-08-24 removal, fixed several broken cross-doc links pointing at renamed/nonexistent docs, and rewrote `sunny-vault/docs/README.md` (self-contradicting in several places — claimed mock briefing data and $0 spend while also describing a live Discord bot).
- Turned up one real **code** bug along the way, not just doc drift: `/service`'s Discord dropdown (`discord_bot.py`) was missing `class_reminders` from its `Literal` — the service has been fully wired (registry, autostart, its own loop) since 2026-08-24 but was never actually selectable through the command. Fixed.
- `sunny-vault/instructions/exam-prep-review.md` (a live system prompt, not just reference docs) was missing a real schema change: `exam_prep.py` now prepends a `## Class info` section from Class Setup's `class-info.md` when one exists, but Claude was never told to expect it — could plausibly have led it to treat syllabus/schedule context as a review topic instead of background. Fixed.

**Sunny can read its own docs**
- New `sunny_code/components/docs_search.py`: a plain keyword search over `sunny-vault/docs/architecture/*.md`, filename-weighted, gated behind a minimum-score threshold. Runs unconditionally ahead of every general-chat LLM fallback question (`briefing.py`'s `custom_briefing()`) — cheap, no LLM call — and prepends the best-matching doc(s) to the prompt when a question is genuinely about how Sunny itself works. A genuinely unrelated question (small talk, math, anything else) scores 0 everywhere and the prompt is unchanged.
- Deliberately excludes `sunny-vault/docs/`'s broader meta docs (`BACKLOG.md`, `CHANGELOG.md`, `DESIGN.md`, `phases.md`, `ABOUT.md`, `system-state.md`) and `Mind-Map.md` from the search corpus — during testing those large, deliberately broad-vocabulary docs out-scored genuinely specific ones (a "how does class setup work" question was landing on `BACKLOG.md` instead of `class-setup.md`) purely on raw word overlap, not actual relevance.
- `general-chat.md` updated with a new section telling Claude what the injected context is and to answer honestly if it's present but doesn't actually cover the question, rather than padding the gap with a guess.
- See [[architecture/docs-search]].

**`/version` + a spoken "what version are you running"**
- New `sunny_code/components/build_info.py`: `get_build_version()` shells out to `git log -1 --format=%h (%as)` in the project root and returns the short commit hash + date (e.g. `d56151e (2026-08-25)`), or `"unknown"` if git isn't available — read fresh each call rather than a hand-maintained version string, since `sunny_code/__init__.py`'s `__version__` isn't bumped per change and can't answer "what build is this."
- `/version` Discord slash command (ephemeral, chat-channel-gated, same shape as `/services`).
- Routed into `assistant.py`'s trigger chain too, so "what version are you running" works identically over voice, the web console, and plain Discord text — not Discord-command-only.
- **Same day, follow-up**: the timestamp shown is now `mm/dd HH:MM` (e.g. `08/25 11:12`) instead of a bare date — `git log`'s `--date=format:%m/%d %H:%M` combined with `--format=%h (%ad)`, replacing the `%as` (date-only) format string.

**Class setup: syllabus → calendar + memory + proactive reminders**
- "set up my classes" walks through a multi-step wizard (semester name → start/end dates → per-class paste-syllabus/confirm, looped until "done") and, on confirm, creates real Google Calendar events and a Sunny-managed memory file for that class.
- `google_calendar.py` gained its first recurring-event support — `create_recurring_event()` (real RRULE, weekly, bounded by the semester end date) and `create_all_day_event()` (due dates/exams). Confirmed with the user directly that a semester of class meetings should be one real recurring event, not ~45 individual one-offs.
- `syllabus_parser.py`: one `ask_claude(purpose="syllabus_parse", model="sonnet")` call per class, strict JSON (meeting times, due dates, exams, a grading/contact summary), dates resolved against the given semester so a syllabus date without a year still lands correctly.
- **Same day, follow-up**: class name is now auto-extracted from the syllabus text itself instead of a separate "what's this class called" question — `class_name` added to the parsed JSON schema. A confirm-step reply that isn't yes/no is treated as a name correction (covers both "the extraction was wrong" and "the syllabus never stated one at all"), re-showing the recap via a new shared `class_setup_engine.recap()`. The syllabus-paste and confirm steps are both excluded from `assistant.py`'s general command-detection gate, since free-form pasted text could otherwise coincidentally match some other command's trigger phrase.
- **Same day, second follow-up**: `/classsetup` Discord slash command — just calls `handle_message("set up my classes", ...)` with the same `session_id` convention `on_message` uses, so it starts the identical wizard and every reply after it is ordinary plain-text; public, not ephemeral, since the whole conversation needs to stay visible. `setup_guides.py`'s bare `"setup"` overview and `"setup classes"` gained an entry too, with a live status (how many classes are actually tracked).
- `class_memory.py` (`sunny-vault/state/classes/`) holds the syllabus summary and key-dates list per class — deliberately separate from exam-prep's `sunny-vault/KSU/` convention, which stays the user's own hand-written notes.
- `class_deadlines.py` (`sunny-vault/state/class-deadlines/`) tracks each due date/exam with idempotent T-2/T-0 reminder flags. A new `class_reminders_loop` in `discord_bot.py` (checks every 3 hours, gated on a new `class_reminders` service toggle) posts to a new `#reminders` channel (`DISCORD_REMINDERS_CHANNEL_ID`) 2 days before and the day of each deadline — the first genuinely proactive, unprompted message anywhere in this codebase. Built as its own dedicated loop rather than routed through the rules_engine.py proactive-architecture pieces, which still have no real caller.
- Exam events created here compose automatically with the existing exam-prep feature (`find_exam_date()` searches Calendar for class name + exam keyword, independently of who created the event).
- See [[architecture/class-setup]].
- **Same day, third follow-up**: the wizard no longer asks for the semester's start/end dates — just the semester label ("Fall 2026"). `syllabus_parser.py`'s schema gained `semester_start`/`semester_end`, pulled from each syllabus's own text (an explicit date range, or the earliest/latest date in an included schedule) instead of a user-typed range applied uniformly to every class; the semester label is now only a year/season hint for resolving bare dates in the source text, not a source of the range itself. `class_setup_engine.recap()` surfaces the derived range before the user confirms, so a bad extraction is visible up front. If a syllabus genuinely doesn't state its dates anywhere, `commit()` skips creating recurring meeting events for that class (due dates/exams still get created — they're self-contained dates) and says so in the result message, rather than guessing a range.
- **Same day, fourth follow-up**: `commit()` now also drops two files into the class's own `sunny-vault/KSU/<semester>/<class>/` folder — `syllabus.md` (the pasted text, verbatim) and `class-info.md` (the summary/schedule/key-dates content, same as `class_memory.py`'s internal copy, rendered as plain markdown) — new `class_memory.save_to_class_folder()`. Previously the only record of a set-up class lived in `sunny-vault/state/classes/`, a gitignored Sunny-only store the user never sees and `exam_prep.py` never reads; this puts it where the user's own hand-written topic notes already live, visible in Obsidian. `exam_prep.py`'s `list_classes()` excludes both filenames from the spaced-review topic list (a syllabus isn't something to track "mastered" on), but `generate_study_review()` now reads `class-info.md` in as extra context ahead of the actual topics when it exists.
- **Same day, fifth follow-up — a real bug from real use**: a user actually tried this by attaching syllabus PDFs as Discord files instead of pasting text, and it silently did nothing (confirmed against the Lenovo's logs and an empty vault before writing the fix, not guessed). Root cause: `discord_bot.py`'s `on_message` only ever read `message.content`, which is empty for a file-only message, so the wizard just kept re-prompting for a syllabus it was never going to see. Fixed with new `pdf_text.py` (`pypdf`, text-layer extraction only, no OCR) and `discord_bot.py`'s `_resolve_message_text()`, called ahead of every message: a single PDF attachment gets its extracted text folded into the effective message text; more than one PDF in one message gets an honest "one at a time" reply instead of a guess at how to split them across classes.

## 2026-08-24

**Task priority removed, category management everywhere, chat memory idle expiry**
- Priority is gone from tasks entirely — no field, no `--priority` flag, no `!task <id> priority` update, no `[P#]` in the dashboard/embed, no `/api/tasks/high-priority` endpoint. It never had real behavior tied to it beyond dashboard sort order. Existing task files with an old `priority:` frontmatter line just have it silently ignored on the next read/write — nothing rewrites old files. `get_all_tasks()`/`get_tasks_due_soon()` now sort by creation date / due date only.
- Category add/remove is no longer Discord-only — "add category `<name>`"/"remove category `<name>`"/"my categories" now work from any interface (console, Discord text, voice, Pi companion), routed in `assistant.py` ahead of task parsing so it can't collide with tasks' broad bare "add X". `/category` in Discord still works too, same underlying `category_store.py`.
- `conversation_memory.py` gained a 2-hour idle expiry (`IDLE_EXPIRY_SECONDS`) on top of its existing 6-turn cap — without it, a quiet conversation from days ago would silently resurface as "recent conversation" context on whatever gets said next. Turn cap still bounds an *active* conversation's prompt size; the idle expiry bounds how long a *quiet* one sticks around at all.
- Confirmed (no code change needed): the Claude-usage-chart move to `#health` was already done in the Service Orchestration pass above — `DISCORD_USAGE_CHANNEL_ID` doesn't exist in `config.py`, `refresh_usage_dashboard()`/`check_usage_alerts()` post to `discord_health_channel_id`.

**Persistent voice presence + conversation memory**
- `/join`/`/leave` are gone — Sunny now stays connected to `DISCORD_VOICE_CHANNEL_ID` persistently, via a new `voice_presence_loop` that reconciles actual connection state against the existing `voice_join` service toggle every 30s (`/service voice_join enable|disable` is the only control surface now). Reconnects automatically after a drop or a worker crash, no manual re-join needed. `voice_session.start()` refactored to take a `discord.VoiceChannel` directly instead of a Discord interaction, since nothing triggers it from a slash command anymore.
- "Hey Sunny" is still required before every request — kept deliberately; an always-listening open mic reacting to any speech in the channel wasn't part of the ask and has real false-trigger/privacy implications.
- New `conversation_memory.py`: session-scoped memory (last 3 exchanges) for the general-chat LLM fallback specifically — not command routing, which stays stateless. In-memory only, resets on restart, never written to the vault. Voice and text share memory naturally since both already used the same `session_id`.

**Service orchestration** (closes out the backlog section of the same name)
- Per-service runtime toggle: `service_registry.py`, a flat JSON file (`service_registry.json`) tracking six services (`dashboard_refresh`, `scheduled_check`, `usage_refresh`, `health_check`, `morning_prep`, `voice_join`). `/service <name> enable|disable` in Discord flips one live — every loop checks `is_enabled()` at the top of its tick, so it takes effect within one tick, not just at next boot. `/services` shows overall status.
- Autostart-per-service: a second `autostart` flag alongside `enabled` in the same registry, checked once at boot to decide whether to start a given loop at all.
- Vacation mode: "vacation mode on"/"off" (or `/vacation` in Discord) suppresses the proactive morning-prep lookahead entirely — no pre-warming, no nudging — while still leaving a direct "good morning"/"good night" working normally.
- Real Claude rate-limit data: both `llm_client.py` call paths now capture Anthropic's own `anthropic-ratelimit-*` response headers into an in-memory current-window snapshot, surfaced via the dashboard API, `/usage`, and a new "what's my usage" intent — distinct from the self-tracked spend chart, which is this app's own cost estimate, not Anthropic's authoritative numbers.

**Proactive-architecture foundation** (personal-assistant-vision.md's hybrid-AI-layers section, first working slice)
- `sensors.py` + `rules_engine.py`: calendar and vault-file-change detection feeding two seed rules (both log-only, no action taken yet), evaluated on a new 30-minute loop. GitHub watchers not built yet.
- `context_engine.py`: a pure read-time aggregator over tasks/lists/today's calendar/project folders — no new storage, no real caller yet.
- `vault_permissions.py`: `request_vault_write()` classifies and logs every vault-write request by confidence (>95% auto, 80-95% suggest, <80% ask, Level 3/destructive always asks regardless of confidence) — decides, doesn't yet get called by anything that actually touches the vault on its own initiative.
- `suggestion_tracker.py`: records suggestion outcomes (accepted/rejected/ignored/snoozed) to an append-only vault log — no real caller yet either, waiting on the first feature that actually emits a proactive suggestion.
- All four are real, tested infrastructure without a live feature wired to them yet — the "no caller yet" pattern is deliberate groundwork, not unfinished work.

**Milestone 3: knowledge health check, TTS delivery, exam-prep**
- Weekly health check gained `knowledge_health_summary()` — broken wikilinks, orphaned/untagged/stale (180+ day) notes — folded into the same Sunday report, plus a one-line mention in the spoken summary. Duplicate-content detection is explicitly out of scope (would need semantic comparison, not just filename matching).
- `tts_delivery.py`: deterministic pace (`length_scale`) multipliers per message type, composing with the user's own `PIPER_LENGTH_SCALE` tuning. First real caller: `/speak text delivery:warning|reminder|casual`. Also threaded through `voice_worker.py`'s speak functions but left unused there — nothing in the live voice-conversation pipeline classifies a reply's type yet.
- `exam_prep.py`: built against a real, user-confirmed vault convention (`sunny-vault/KSU/<semester>/<class>/*.md`, one file per topic), not guessed. Exam dates come from Google Calendar, matching class name and an exam keyword independently (a strict substring match is too fragile against real event titles like "BUS 2100 Midterm Exam"). The vision doc's 5-stage spaced-review pipeline simplified to 3 real persisted states (new/weak/mastered) — modeling all 5 added complexity with no behavioral difference for a single-user tool. "study review for `<class>`" is the one real LLM-backed feature (Sonnet, reads actual note content); the ~1-week-out study plan stage isn't built, only the night-before review.

**Google Calendar write access**
- Sunny can now create and delete real calendar events by natural language — "add dentist appointment to my calendar at 3pm tomorrow", "cancel dentist appointment from my calendar" — from any interface (Discord, console, voice, Pi companion), same routing pattern as tasks/lists/alarms.
- Required widening the OAuth scope from `calendar.readonly` to the full `calendar` scope (`google_auth.py`) — anyone already connected has to reconnect via `/console`, since Google doesn't retroactively expand an existing token's scope.
- New `calendar_parser.py` (regex, matches the "calendar"/"event" keyword requirement so it can't collide with tasks' much broader bare "delete X") + `calendar_engine.py` (stateless — Google Calendar itself is the only store) + `google_calendar.create_event`/`find_event_by_title`/`delete_event`. Delete resolves a title to an event via case-insensitive substring match across every calendar (soonest upcoming match wins on ambiguity) — no confirmation step before deleting, a real risk worth knowing about.
- Deliberately narrow scope of what got built: create + delete only, no reschedule/move, no recurring events, no invites. See [[architecture/google-integration]] for the full breakdown.

## 2026-08-23

**Task system rework**
- Task categories are now a real, editable list (General/School/Motorsports by default) instead of a dead display-only constant — `/category add`/`/category remove` in Discord manage it, and Sunny asks which category when one isn't stated or implied in the phrasing.
- Deleting or finishing a task archives its file (`archive/deleted/` or `archive/finished/`) instead of removing it — no task data is ever actually lost, and lifetime stats still count what finished.
- The Discord task dashboard is now a live-updating embed instead of plain text, with a Projects section listing real project folders.
- New "new project" flow: say "new project" (or similar), answer three quick questions, and Sunny drafts a real multi-file project folder under `sunny-vault/projects/` via one Claude call.
- Broadened natural-phrasing coverage for add/complete/delete (inline categories like "...to my school tasks", "put X on my tasks", "check off my X task").
- Fixed a real pre-existing bug: a blank reply during *any* pending follow-up question fell through to the help text instead of re-prompting.

**Web search**
- Claude can search the web from open-ended conversation (capped at 3 searches/call, off by default per question — it decides when a question genuinely needs current info, steered in `general-chat.md`).
- A distinct "searching" cue (a third audio tone, different from the wake chime and the thinking cue) plays over voice while a search is in flight; the Pi companion gets a matching state event.

**Spotify voice control**
- "play `<song>`", "pause", "resume", "skip", "previous song", "volume up/down" or "set volume to N", "what's playing" — works from any voice or text interface, same as tasks/lists. Acts on whatever device Spotify itself considers active (no device-targeting concept in Sunny, matching how Siri/the Spotify app behave). Requires Spotify Premium.
- OAuth (PKCE) mirrors the Google Sign-In pattern — a "Connect Spotify Account" card on `/console`, token stored/refreshed locally (`spotify_token.json`).
- Found live: Spotify rejects any redirect URI over plain HTTP except the literal loopback `127.0.0.1` — a Tailscale IP doesn't qualify. Fixed by reusing the Tailscale-issued HTTPS cert already set up for Google's integration (`TLS_PORT` 5443) instead of a new cert.

**Sunny Companion**
- Removed `pi-client/avatar-app/` (the bible-strong-avatar-lab implementation) — it was already scrapped once, but came back into `main` via a merge that resurrected files a prior commit had deleted, contradicting what `BUILD_PLAN.md` itself claimed ("removed entirely").
- Built the Phase 4 restart's standalone prototype — `pi-client/face_renderer/renderer.py`, a pygame(-ce) amplitude-reactive circle with keyboard-driven state switching (idle/listening/thinking/searching/speaking) and a 5-hue emotion-overlay stub. Real mic RMS drives `listening`; synthesized breathing sines drive `thinking`/`searching`; `speaking` reuses the mic feed as a placeholder until Phase 4.5 wires in the real TTS playback buffer. Verified running on this dev machine (real window, steady frame rate) — not yet on real Pi 3 B hardware, which is Phase 4's one remaining checkbox. Had to switch to `pygame-ce` over upstream `pygame`, which has no Python 3.14 wheel yet.
- Added `pi-client/Dockerfile.test` + `face_renderer/smoke_test.py` — a dev-only, QEMU-emulated arm64 Debian Bookworm image (matching Raspberry Pi OS Lite 64-bit) that installs the real `pi-client/requirements.txt` and runs a headless render smoke test, to catch arm64 packaging problems (native-extension wheels for `pygame-ce`/`sounddevice`/`openwakeword`) before physical Pi hardware exists. Proves install + non-crashing render only — not real Pi 3 B frame timing (QEMU emulation isn't representative either way), not `kmsdrm`/real display output, not live mic capture (no audio hardware in a container).

**Other**
- "run health check" runs a real check on demand instead of only showing the last cached one — short spoken summary over voice, full report in text; the #health channel is now one pinned message edited in place, with key figures **bolded**.
- `/usage`'s chart is now a persistent dashboard, hourly-updated — moved into the same #health channel as the weekly report (was its own dedicated channel), same embed style with bold key figures, and delete-and-resend instead of edit-in-place since Discord's embed image cache can hold a stale thumbnail through an attachment-replacing edit. Plus a once-a-day ping when spend crosses 70% of the daily/monthly self-imposed cap or a key is expiring within a week, same channel now too. `DISCORD_USAGE_CHANNEL_ID` no longer exists as a setting.
- Rewrote the LLM's conversational voice (`general-chat.md`) for a terser, three-part response style (acknowledgment / payload / optional tail), merged with the existing TTS-safety and no-fabricated-data constraints.
- Fixed a real STT race: `on_audio()` (the voice decode thread) and `silence_watchdog()` (the asyncio loop) both called into the same Vosk recognizer with no lock — a feed landing mid-finalize corrupted it (Vosk's own "AcceptWaveform called after InputFinished" check, followed by invalid JSON on the next result). Same class of bug, same fix, as the DAVE-session race below.
- Storm mode: "storm mode" in Discord asks for an update interval and a duration, then posts real, web-searched weather updates (not the API) on that interval until time's up or it's stopped early.
- Morning prep: the scheduler now prewarms the morning briefing a few minutes ahead of the next alarm, so a real "good morning" right after returns instantly instead of waiting on live weather/calendar/email calls — while still keeping email fresh at wake-up.
- The "new project" wizard now recaps and asks yes/no before actually building (a firm "no" skips the LLM entirely), with a few phrasing variants per question instead of one fixed line. Morning/evening briefing triggers broadened past bare "morning"/"evening" ("good morning sunny", "im up", "going to bed", etc.).

## 2026-08-21 – 2026-08-22

- Streaming LLM replies: `/join` starts speaking the first sentence of an open-ended answer while Claude is still writing the rest, instead of waiting for the whole response (`ask_claude_stream`, sentence-boundary splitting).
- Barge-in: saying "Hey Sunny" again mid-reply now stops the current audio and discards anything else queued or still being synthesized for the interrupted response, instead of continuing to talk over it (generation-tagged playback queue).
- Reused Anthropic API clients instead of reconnecting per call; added a short "thinking" audio cue for the gap while a slow LLM reply is generating.
- Fixed a real regression: the wake word plus a natural pause before the actual sentence could get split into two utterances, silently dropping the second half.
- Hardened the task/list parsers against real STT mishearings found by reading actual `/join` transcripts (e.g. "add" heard as "i'd").
- Fixed a weather-location save bug (OpenWeatherMap needs `City,State,Country`, not free text) and added validation before saving.

## 2026-08-19 – 2026-08-20

- Moved `/join`'s entire real-time audio pipeline (Discord voice, DAVE encryption, Opus, Vosk STT, Piper TTS) into an isolated child process, so a native crash there can only end that one voice session instead of taking down the whole bot.
- Root-caused and fixed a real DAVE session threading race (a shared native object touched by 3+ OS threads with no synchronization) behind several native crashes.
- Root-caused a genuine bug in the large Vosk/Kaldi model via `faulthandler`-captured native stack traces (a real, unfixable-from-userland assertion failure); reverted to the small model.
- Migrated task/list storage onto the Obsidian vault as markdown (one file per item) instead of SQLite, so tasks and lists are directly readable/editable in Obsidian.

## Earlier

Task/list/briefing/Discord-bot/dashboard foundation, weather/calendar/Gmail integrations, alarms & reminders, the Sunny Companion hardware groundwork (wake-word prototype, avatar). See [[phases.md]] and the `architecture/` folder for how each of these actually works.
