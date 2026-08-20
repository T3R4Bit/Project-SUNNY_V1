---
id: sunny-tts-piper
type: feature
status: active
created: 2026-08-20
tags: [voice, tts, piper, discord, speak]
---

# Piper TTS — `/speak` Discord Command

Free, fully local text-to-speech: type `/speak <text>` as a real Discord slash command and Sunny posts back a playable `.wav` attachment, synthesized on the Lenovo with no API call, no cost, no internet dependency beyond the one-time model download.

## Status

✅ Built — `sunny_code/components/tts.py`, `/speak` in `sunny_code/components/discord_bot.py`.

## Why This, Not the Full voice-io.md Pipeline

[[voice-io]] and [[clock]] describe a much bigger Phase 3/4 pipeline: Sonic API (primary) + Piper (fallback) TTS, Whisper/Vosk STT, wake-word detection, all streaming to/from a physical ESP32-S3 "Clock" device with its own microphone and speaker. None of that hardware has been ordered yet (`phases.md`: every Phase 3 hardware-assembly checkbox is still unchecked).

This is a deliberately narrower, software-only slice of that vision, built now because it doesn't need to wait on hardware:

- **No STT, no wake word, no live conversation.** Text goes in (typed by the user), audio comes out (as a file). One-shot, not a stream.
- **No Sonic API.** Piper only — it's free and local, which is what makes this buildable without any new account/API key.
- **Output is a Discord attachment, not a speaker.** There's no physical speaker to play audio through yet — Discord's own client is the playback device today.

Piper itself — the actual TTS engine — is the same piece `voice-io.md` already names as the local fallback for the eventual Clock hardware. Building and proving it here means that when the Clock hardware exists, the hard part (getting Piper working, choosing a voice, understanding its API) is already done; only the audio-transport layer (Discord attachment → I2S stream to a speaker) changes.

## How It Works

- `sunny_code/components/tts.py`: `synthesize_wav_bytes(text: str) -> bytes`. Lazily loads a `PiperVoice` once (real cost: ~1s to read the ONNX model off disk and start an onnxruntime session) and caches it in a module global for the process lifetime — matches `llm_client.py`'s pattern for state that's expensive to (re)create. Auto-downloads the voice model on first use via `python -m piper.download_voices <voice> --download-dir <dir>` if it isn't already on disk (~60MB, one time, skipped automatically after that). Raises on failure — the caller decides how to tell the user, matching this app's everywhere-else "never crash, say what's wrong" contract.
- `sunny_code/components/discord_bot.py`: `/speak` is a real registered Discord slash command (`discord.app_commands.CommandTree` bound directly to the bot's bare `discord.Client` — no `commands.Bot` needed), the first one this bot has. Only usable in the configured chat channel (same restriction every other command already has); capped at 1000 characters per call (a practical limit on synthesis time/file size, well under Discord's own 6000-char slash-command string cap, not a Piper limitation). Defers the interaction (`interaction.response.defer(thinking=True)`) since Piper's first call can take longer than Discord's 3-second initial-response window, synthesizes off the event loop via `asyncio.to_thread`, then replies with `discord.File(io.BytesIO(wav_bytes), filename="speech.wav")` — Discord renders a native inline audio player for `.wav` attachments.
- Commands are synced to this bot's one guild rather than globally — guild-scoped sync is instant, global sync takes up to ~1 hour to propagate, and this bot is already single-server by design (see [[discord-bot]]). `@tree.command()` (no `guild=`) registers a **global** command, and `tree.sync(guild=...)` alone only uploads that guild's own (initially empty) command list — it does **not** implicitly copy global commands into it. The actual fix, found by testing against the real Discord API (a first attempt without this silently synced zero commands, no error): `tree.copy_global_to(guild=guild)` **then** `await tree.sync(guild=guild)`, in `on_ready`, guarded against re-syncing on reconnect.

## External Setup Step: `applications.commands` Scope

Registering a slash command requires the bot's Discord invite to include the `applications.commands` OAuth2 scope, not just `bot`. If the original invite only checked `bot`, re-run the invite URL with `applications.commands` also checked and re-authorize — [[discord-bot]] already documents this exact non-destructive re-invite flow for adding permissions later (Discord updates the existing bot in place, no kick/re-invite needed); this is the same mechanism, just adding a scope instead of a permission.

## Verified Package Details (2026-08-20, via live WebFetch — not recollection)

`piper-tts` is the actively maintained `OHF-Voice/piper1-gpl` fork/successor of the original `rhasspy/piper`, GPL-3.0.

- `pip install piper-tts` (1.7.0 at time of writing). Wheels use the stable ABI (`cp39-abi3`) — one wheel covers Python 3.9 through 3.14+, confirmed installing cleanly on both this dev machine (Python 3.14.3) and the Lenovo (3.14.4).
- Core dependency `onnxruntime<2,>=1` — a real per-Python-version native wheel (not abi3), confirmed a `cp314` wheel exists and installs cleanly for 1.29.0.
- `from piper import PiperVoice; voice = PiperVoice.load(path_to_onnx)`, then `voice.synthesize_wav(text, wav_file)` where `wav_file` is any file-like object opened via the stdlib `wave` module — works with an in-memory `io.BytesIO`, no temp file needed.
- Default voice: `en_US-lessac-medium` (22050Hz mono). Config: `PIPER_VOICE` in `.env`, default matches.

## Known Limitations

- **One-shot, not streaming/conversational.** You type text, you get a file back — no live back-and-forth, no STT. That's the deferred `/join` work below.
- **First call after a restart is slower** (~1s model load) than subsequent calls (cached, near-instant synthesis). Not user-visible thanks to `defer()`, but worth knowing if debugging latency.
- **1000-character cap.** Longer text needs to be split into multiple `/speak` calls for now.

## Deferred: `/join` — Live Voice Channel Conversation

Explicitly requested by the user as a followup, not part of this build: a `/join` command that has the bot join a live Discord voice channel for real-time conversation, rather than posting one-shot audio attachments. Tracked in [[../BACKLOG.md]]. `tts.synthesize_wav_bytes()` is written to be reusable by that work — nothing here is one-shot-specific at the synthesis layer, only at the Discord-transport layer (`/speak`'s file-attachment reply vs. `/join`'s live audio stream into a `discord.VoiceClient`).

## Files

- `sunny_code/components/tts.py` — `synthesize_wav_bytes()`, `is_voice_downloaded()`
- `sunny_code/components/discord_bot.py` — `/speak` command, `CommandTree` setup, guild sync
- `sunny_code/components/setup_guides.py` — `"setup piper"`/`"setup speak"` guide
- `sunny_code/config.py` — `piper_voice`, `piper_voices_dir`
- `piper_voices/` (gitignored) — downloaded model files

## Dependencies

- [[voice-io]] — the full pipeline this is a narrower, hardware-free slice of
- [[clock]] — the eventual hardware Piper was originally scoped as a fallback for
- [[discord-bot]] — hosts the slash command, guild sync, channel restriction

## Implementation Checklist

- [x] `tts.py` — lazy-loaded/cached `PiperVoice`, auto-download-on-first-use, `synthesize_wav_bytes()`
- [x] `/speak` slash command — channel restriction, length cap, defer + threaded synthesis, file attachment reply
- [x] Guild-scoped command sync, guarded against re-sync on reconnect
- [x] `"setup piper"` guide + overview entry
- [ ] `/join` — live voice channel conversation (deferred, see BACKLOG.md)
