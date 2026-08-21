---
id: sunny-voice-join
type: feature
status: active
created: 2026-08-20
tags: [voice, stt, tts, vosk, piper, discord, join]
---

# `/join` — Live Voice Conversation

`/join` has Sunny join your current Discord voice channel and have a real spoken conversation: your speech gets transcribed locally (Vosk), routed through the exact same `assistant.handle_message()` router every other interface (console, terminal, Discord text) already uses, and the reply is spoken back (Piper — see [[tts-piper]]). `/leave` ends it. No API key, no per-minute cost, either direction.

## Status

✅ Built — `sunny_code/components/stt.py`, `sunny_code/components/voice_session.py`, `/join`+`/leave` in `sunny_code/components/discord_bot.py`.

## Why This Is the Riskiest Feature Built This Session

Everything else in this app is request/response. This is the first live, bidirectional, real-time audio pipeline — and `discord.py` has real, structural gaps here: no voice support at all without an extra install, and **no built-in way to receive audio** from a channel, only send. Getting this right meant verifying every non-obvious claim empirically against the actually-installed packages (real installs, `inspect.getsource()`, not docs or recollection) before writing a line of the implementation — see "Verified Findings" below. One dependency this relies on is an unofficial, alpha-versioned community extension, not part of `discord.py` core — see Known Risks.

## Architecture

```
Discord voice channel
  │ (user speaks)
  ▼
VoiceRecvClient + BasicSink  →  per-user 48kHz stereo PCM callback (sync, off-loop thread)
  │
  ▼  (thread-safe handoff to the asyncio loop)
stt.py: audioop resample (48k stereo → 16k mono) → per-user KaldiRecognizer.AcceptWaveform()
  │  (True = segment finalized, Vosk's own internal silence-based endpointing)
  ▼
Result() JSON → transcribed text
  │
  ▼
assistant.handle_message(text, ..., session_id=f"voice:{guild_id}:{user_id}")   ← same router as every other interface
  │
  ▼  response text
tts.py: synthesize_wav_bytes() [already built for /speak] → audioop resample (22050 mono → 48k stereo)
  │
  ▼
voice_client.play(discord.PCMAudio(pcm_stream))   ← spoken back into the channel
```

**One session at a time.** Module-global state in `voice_session.py` (mirrors `tts.py`'s singleton pattern) — a second `/join` while one is active gets "Already in a voice call," not a second concurrent session. Matches this app's existing single-guild assumption (see [[discord-bot]]).

**No wake word.** Joining the channel *is* the "start listening" signal — the same way a real Discord voice channel already works (everyone in it can be heard). `/leave` is "stop listening." This is a deliberate difference from the wake-word design in [[clock]]/[[voice-io]] (built for an always-on physical device); a Discord `/join` you invoke on demand doesn't need one.

**No multi-speaker handling.** One recognizer per speaker (keyed by Discord user ID) so the common case (you, alone, talking) works cleanly, but there's no diarization — if two people talk over each other, both streams still get fed independently and could produce garbled/interleaved responses. Accepted, given the actual single-user use case.

## Verified Findings (2026-08-20, via real installs + `inspect`, not docs or recollection)

- **`discord.py`'s bare install has no voice support at all** — every deploy log this session logged `PyNaCl is not installed` / `davey is not installed, voice will NOT be supported`. Voice (send *and* receive) needs the `[voice]` extra: `PyNaCl` (encryption) + `davey` (Discord's newer DAVE end-to-end voice encryption). Confirmed real wheels exist for Python 3.14 (`PyNaCl` ships abi3; `davey` has a real `cp314` wheel) — installs cleanly.
- **`discord.py` has no built-in voice-*receive* API** — `VoiceClient` only sends. Used `discord-ext-voice-recv` (PyPI, latest `0.5.2a179`) instead — see Known Risks for what that tradeoff means. Confirmed via real install + `inspect.getsource()`:
  - `voice_recv.VoiceRecvClient` is a subclass of `discord.VoiceClient` — one client handles both directions (`.play()` still works), no second connection needed.
  - `channel.connect(cls=voice_recv.VoiceRecvClient)` to connect.
  - `voice_recv.BasicSink(callback)` — simplest receive path. `callback(user, data: VoiceData)` fires with `data.pcm` already Opus-decoded. **Confirmed via source: this callback is a plain sync function, called off the asyncio event loop** (a dedicated audio-decode thread) — `voice_session.py`'s `on_audio` never awaits directly, it hands off via `asyncio.run_coroutine_threadsafe()`.
- **PCM format** — confirmed via `discord.opus.Encoder` constants on the actually-installed package: `SAMPLING_RATE=48000`, `CHANNELS=2` (48kHz stereo 16-bit), both for what `VoiceData.pcm` delivers and what `discord.PCMAudio` expects for playback (confirmed via its docstring: "raw 16-bit 48KHz stereo PCM"). Piper's output is 22050Hz mono — both directions need resampling.
- **Resampling** — stdlib `audioop` was removed in Python 3.13 (this project runs 3.14). Checked whether this silently breaks `discord.py` itself: **`discord.py`'s own PyPI metadata lists `audioop-lts; python_version >= "3.13"` as a base dependency** (not just the voice extra), already auto-installed — `import audioop` works today, no new dependency, no scipy/numpy DSP code needed. `audioop.tomono()`/`audioop.tostereo()`/`audioop.ratecv()` cover both directions.
- **`discord.PCMAudio.read()` drops any trailing chunk shorter than one Opus frame** (`discord.opus.Encoder.FRAME_SIZE`, 3840 bytes) — treats it as end-of-stream. `tts.synthesize_discord_pcm()` pads the final chunk with silence to a full frame boundary so the last ~20ms of a spoken response never gets silently cut.
- **Vosk** (PyPI, latest `0.3.45`) — installs cleanly on Python 3.14. Confirmed via `inspect`:
  - `Model(lang="en-us")` **auto-downloads** the small model on first use (read `vosk.Model`'s own source — no custom download step, unlike Piper's `download_voices`). Cache dir controlled by `VOSK_MODEL_PATH` env var, set from `settings.vosk_model_dir`.
  - `KaldiRecognizer(model, 16000)`, then `rec.AcceptWaveform(chunk) -> bool`. **True means Vosk has finalized a segment (silence-based endpointing happens *inside* Vosk)** — no custom silence-timeout logic needed in `stt.py`; just keep feeding the same recognizer across chunks and call `Result()` whenever `AcceptWaveform()` returns True.

**Fully verified end-to-end with an automated loopback test** (no Discord, no human voice needed): synthesized "the quick brown fox jumps over the lazy dog" with Piper, converted to Discord's 48kHz-stereo capture format, fed through the resample+Vosk pipeline in real 20ms Discord-frame-sized chunks — **transcribed back word-for-word exactly**, in 0.51s of processing for 2.75s of audio (comfortably faster than real-time on this hardware). This proves the entire pipeline's audio-format math in both directions plus the STT engine itself, independent of anything Discord-specific.

## Known Risks

- **Needs the system `libopus0` library installed on the host — a native C library, not something pip can install.** `discord.py` bundles Opus for some platforms but not Linux; without it, both playback and incoming-audio decode fail with `OpusNotLoaded`. Found for real during send-side verification on the Lenovo (connect + `tree.sync()` + TTS synthesis all worked; the actual `voice_client.play()` call is what surfaced it) — not something pip installing `discord.py[voice]` alone catches, since that only covers the Python-level encryption/DAVE dependencies, not the audio codec itself. **Resolved**: `sudo apt-get install -y libopus0` on the Lenovo, then re-verified — real connect → synthesize → encode → play → clean disconnect all work. Worth remembering for any future redeploy to a fresh box.
- **`discord-ext-voice-recv` is an unofficial, alpha-versioned (`0.5.2a179`) community extension, not part of `discord.py` core.** It could break on a future `discord.py` voice-protocol change (voice internals are exactly the kind of thing that shifts between versions) without warning. This is the one real structural risk in this feature — nothing else added this session carries this kind of risk (Piper, Vosk, and every prior dependency are either official or a stable 1.0+ release).
- **Continuous CPU cost while a session is active.** Vosk decoding is real, ongoing work — unlike everything else in this app, which is pure request/response. Small model keeps this modest, but it's a genuinely different resource profile, worth watching if the Lenovo ever feels loaded during a long `/join` session.
- **Vosk's small model trades accuracy for speed/size** — same tradeoff already accepted for Piper's default voice and Haiku-tier LLM defaults, in keeping with "local and free."
- **No wake word, no wire-level privacy indicator beyond Discord's own** — being in the channel means Sunny is listening to everyone in it, same as any other bot/human in a Discord voice channel. `/leave` is how you stop that.

## Not Included This Pass

- **No persistent transcript log** — exchanges are logged via the normal Python app logger only, not a new `sunny-vault/log/` file. A natural addition later if wanted; not built ahead of an actual need.
- **No STT/TTS tuning for the voice pipeline specifically** — Piper's existing tuning knobs (`PIPER_LENGTH_SCALE` etc., see [[tts-piper]]) still apply to spoken replies. No equivalent Vosk knobs (bigger model, different language) yet — natural follow-up if accuracy needs it.

## Files

- `sunny_code/components/stt.py` — Vosk model loading, `new_recognizer()`, `resample_to_16k_mono()`, `feed()`
- `sunny_code/components/tts.py` — `synthesize_discord_pcm()` (new, alongside the existing `synthesize_wav_bytes()` used by `/speak`)
- `sunny_code/components/voice_session.py` — session orchestration: connect, per-user recognizers, the receive callback and its thread-safe handoff, assistant routing, response playback, disconnect
- `sunny_code/components/discord_bot.py` — `/join`, `/leave` commands
- `sunny_code/config.py` — `vosk_model_dir`, `vosk_lang`
- `vosk_models/` (gitignored) — downloaded model files

## Dependencies

- [[tts-piper]] — reuses `synthesize_wav_bytes()`, and is the doc this one supersedes the "Deferred: /join" section of
- [[voice-io]] — the full hardware-bound pipeline this is a software-only, Discord-only slice of
- [[discord-bot]] — hosts the commands, guild sync, channel restriction
- `sunny_code/components/assistant.py` — `handle_message()`, the shared router this reuses unchanged

## Implementation Checklist

- [x] `stt.py` — Vosk wrapper, verified via an automated loopback test (Piper → resample → Vosk → exact transcript match)
- [x] `tts.py: synthesize_discord_pcm()` — verified PCM format/frame-padding math
- [x] `voice_session.py` — connect/listen/dispatch/respond/disconnect, verified via mocked Discord objects (bot-user filtering, mid-utterance buffering, session_id construction, full response pipeline)
- [x] `/join`/`/leave` slash commands, channel-restricted
- [x] Connect + command registration verified live against the real Discord API (3 commands registered, `channel.connect()` succeeds)
- [x] `libopus0` installed on the Lenovo (`sudo apt-get install -y libopus0`) — send-side re-verified after: real connect → real Piper synthesis → real Opus encode → real playback → clean disconnect, all against the live bot
- [ ] Real end-to-end verification with a live human voice in a real channel — the one thing that categorically can't be scripted
