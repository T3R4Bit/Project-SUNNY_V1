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

**Other**
- "run health check" runs a real check on demand instead of only showing the last cached one — short spoken summary over voice, full report in text.
- `/usage` — a dark-themed chart of daily Claude API cost, posted as a Discord image attachment (the one actually-paid API in this app).
- Rewrote the LLM's conversational voice (`general-chat.md`) for a terser, three-part response style (acknowledgment / payload / optional tail), merged with the existing TTS-safety and no-fabricated-data constraints.

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
