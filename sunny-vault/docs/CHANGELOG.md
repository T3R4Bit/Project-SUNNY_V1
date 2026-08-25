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
