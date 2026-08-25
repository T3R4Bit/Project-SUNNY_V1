---
id: sunny-voice-join
type: feature
status: active
created: 2026-08-20
tags: [voice, stt, tts, vosk, piper, discord, join]
---

# Live Voice Conversation

**2026-08-24: `/join`/`/leave` are gone.** Sunny now stays persistently connected to `DISCORD_VOICE_CHANNEL_ID` — a `voice_presence_loop` in `discord_bot.py` reconciles actual connection state against desired state (the `voice_join` service enabled + a channel configured) every 30s, reconnecting automatically after a drop or a crash, connecting/disconnecting within one tick of `/service voice_join enable|disable`. Everything below describing the pipeline itself, the crash history, and the fixes is unchanged and still accurate — only *what triggers* `voice_session.start()`/`stop()` changed, from a slash-command interaction to this loop. See "Persistent Voice Presence + Conversation Memory (2026-08-24)" further down for the full change.

Sunny joins the configured voice channel and has a real spoken conversation: your speech gets transcribed locally (Vosk), routed through the exact same `assistant.handle_message()` router every other interface (console, terminal, Discord text) already uses, and the reply is spoken back (Piper — see [[tts-piper]]). No API key, no per-minute cost, either direction.

Say **"Hey Sunny"** (or "Hello Sunny", or just "Sunny") before every separate request — there's no conversational listening window. (An earlier 2026-08-20 design armed a `WAKE_WINDOW_SECONDS` (20s) window so follow-ups needed no repeat; reverted 2026-08-21 per direct request — every request needs its own "Hey Sunny", matching the physical-Clock design in [[clock]]/[[voice-io]].) The one exception is `WAKE_TO_COMMAND_GRACE` (4.0s, `voice_worker.py`): a bare wake word with nothing after it stays briefly armed for the command that's probably still coming — bridging the natural pause between saying "Hey Sunny" and then saying the actual sentence — not a general "keep listening" window. Outside that brief grace period, speech is transcribed (still real CPU work — see Known Risks) but never reaches the assistant router at all.

Detection is **fuzzy, not exact**: Vosk's small model reliably mis-hears "Hey Sunny" as things like "the sunny it up" or "a sony what's the one" (confirmed against real transcripts, 2026-08-20 — an exact-match first version meant the wake word essentially never actually fired). `_strip_wake_phrase()` scans the first few words for anything close enough to "sunny" (`difflib.SequenceMatcher`, threshold 0.6) rather than requiring "hey"/"hello" to also survive intact — that lead-in gets garbled unpredictably, but "sunny" itself is the one reliably-recognizable anchor.

A short generated chime (~200ms, two rising tones) plays the instant the wake word is heard — the same "I heard you, go ahead" confirmation an Alexa/Google Home gives, so there's audible feedback even before a spoken reply is ready (which can take a beat: transcribe → route → synthesize → play).

## Status

✅ Built — `sunny_code/components/stt.py`, `sunny_code/components/voice_session.py`, `sunny_code/voice_worker.py`, `voice_presence_loop` in `sunny_code/components/discord_bot.py`.

**2026-08-20, later the same night**: four separate native crashes (process-ending `SIGABRT`/`SIGSEGV`) during live testing, each taking the *entire bot* down — see "The Four Crashes" below for the full history, the verified root cause, and the two-layer fix (a real threading lock, plus moving the whole pipeline into an isolated worker process). Architecture diagram below reflects the post-fix design.

## Why This Is the Riskiest Feature Built This Session

Everything else in this app is request/response. This is the first live, bidirectional, real-time audio pipeline — and `discord.py` has real, structural gaps here: no voice support at all without an extra install, and **no built-in way to receive audio** from a channel, only send. Getting this right meant verifying every non-obvious claim empirically against the actually-installed packages (real installs, `inspect.getsource()`, not docs or recollection) before writing a line of the implementation — see "Verified Findings" below. One dependency this relies on is an unofficial, alpha-versioned community extension, not part of `discord.py` core — see Known Risks.

## Architecture

**Process-isolated as of 2026-08-20** (see "The Four Crashes" below for why): the entire real-time audio pipeline runs in its own OS process, spawned by `voice_presence_loop` (see the 2026-08-24 note above) and torn down the same way. Only recognized command text and reply text cross the process boundary — a native crash inside the worker can only end that one session, never the rest of the bot.

```
PARENT PROCESS (the main bot — web dashboard, Discord text commands, tasks, alarms)
  sunny_code/components/voice_session.py
  │
  │  multiprocessing.Process(target=voice_worker.run_worker, ...)
  ▼
WORKER PROCESS (one per voice session — sunny_code/voice_worker.py)
  Its own discord.Client, same bot token, a second independent gateway session
  │ (user speaks)
  ▼
VoiceRecvClient + BasicSink  →  per-user 48kHz stereo PCM callback (sync, off-loop thread)
  │
  ▼  (thread-safe handoff to the worker's own asyncio loop)
stt.py: audioop resample (48k stereo → 16k mono) → per-user KaldiRecognizer.AcceptWaveform()
  │  (True = segment finalized, Vosk's own internal silence-based endpointing)
  ▼
Result() JSON → transcribed text
  │
  ▼
wake-phrase gate (voice_worker.py) — outside the listening window and no
"Hey Sunny"? dropped here, never crosses the process boundary at all.
  │  (awake, or wake phrase found — stripped from the text)
  ▼
multiprocessing.Queue: {"type": "utterance", "text": ..., "user_id": ...}
  │
  ▼ ═══════════════ process boundary ═══════════════
  ▼
PARENT: assistant.handle_message(command, ..., session_id=f"voice:{user_id}")   ← same router as every other interface, needs the live engine objects that only exist here
  │
  ▼  response text
multiprocessing.Queue: {"type": "speak", "text": response}
  │
  ▼ ═══════════════ process boundary ═══════════════
  ▼
WORKER: tts.py: synthesize_discord_pcm() → audioop resample (22050 mono → 48k stereo)
  │
  ▼
voice_client.play(discord.PCMAudio(pcm_stream))   ← spoken back into the channel
```

**One session at a time.** Module-global state in `voice_session.py` (mirrors `tts.py`'s singleton pattern) — `voice_presence_loop` only calls `start()` when `is_active()` is already False, so this never actually races in practice, but `start()` still guards it directly ("Already in a voice call") for safety. Matches this app's existing single-guild assumption (see [[discord-bot]]).

**A second `discord.Client`, same token, connecting to voice while the main bot's own client is already connected — verified empirically live against the real bot** (not assumed): confirmed both that Discord allows a bot token to hold two simultaneous independent gateway sessions, and that the main bot's own connection is completely unaffected while the second one connects, speaks, and disconnects.

**Wake phrase required before every separate request, not a listening window.** A fuzzy match on "sunny" anywhere in the first few words (not an exact `"hey sunny"` prefix — see the real-transcript examples above) gates each utterance individually; a bare wake word with nothing after it just arms a brief `WAKE_TO_COMMAND_GRACE` (4.0s) so the very next utterance is treated as the still-coming command rather than requiring "sunny" to appear in it too. Everything Vosk transcribes still gets STT'd continuously the whole time you're joined (that part *is* "always listening," same as any Discord voice channel) — the gate is purely about what gets forwarded to the assistant router, so idle chatter in the channel doesn't trigger a response. This is a reversal of this doc's original design: a 2026-08-20 `WAKE_WINDOW_SECONDS` (20s) conversational window meant a real follow-up needed no repeated wake word — reverted 2026-08-21 per direct request, back to "wake word required before every single sentence" (matching the physical-Clock design in [[clock]]/[[voice-io]]) precisely because a standing-open window was the wrong tradeoff for this use case.

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
- **Confirmed, hit for real**: a single corrupted/lost Opus packet (routine on real UDP voice traffic — packet loss, jitter, nothing actually wrong) crashed the library's `PacketRouter` thread entirely and silently ended the whole listening session (`stop_listening()` fires in a `finally` block on any decode error). A real user's very first `/join` test went unresponsive after exactly one `OpusError: corrupted stream`, ~2 seconds after joining — matches known upstream reports (GitHub issues #43/#49/#53/#61 on `discord-ext-voice-recv`, several referencing DAVE-encrypted packets specifically). No PyPI release fixes this; there's a matching **open, unmerged** upstream PR (#57) that catches the decode error per-packet instead of letting it kill the thread. **Fixed**: `voice_session.py` monkey-patches `PacketRouter._do_run` at import time with the same one-method fix the PR proposes (skip the bad packet, keep the router running), rather than depending on an unofficial fork as a pip dependency. Documented here in detail since this is exactly the kind of alpha-library fragility the previous bullet warned about in the abstract — now a concrete, worked example of it.
- **Root cause of the above, found on the second real test**: with the crash patched, the router kept running but logged "skipped a corrupted/undecodable audio packet" for essentially *every* packet — not occasional loss, systematic failure. Confirmed via `discord.py`'s own source (`voice_state.py`/`gateway.py`): whether a voice connection uses Discord's newer end-to-end **DAVE** encryption is decided by `max_dave_protocol_version`, which is `0` unless the `davey` package is importable — i.e. purely a client-side opt-in, gated on one import succeeding. `discord-ext-voice-recv`'s decode path predates DAVE and can't decrypt DAVE-encrypted frames before handing them to the Opus decoder, hence "corrupted" on every single packet once DAVE is active.
  - First attempted fix: force `has_dave = False` to make `discord.py` negotiate classic (pre-DAVE) encryption. **Wrong direction entirely** — Discord made DAVE **mandatory platform-wide in March 2026, no opt-out, no server setting**. A client that doesn't support it gets refused outright at connect time with voice close code **4017** ("this channel requires E2EE via the DAVE Protocol") — confirmed live: `/join` started failing to connect at all, retrying the handshake 5 times over ~25s before giving up, exactly matching this close code's documented meaning. DAVE has to stay on.
  - **Actual fix**: keep DAVE enabled, and instead decrypt inbound frames before Opus ever sees them. `voice_session.py` patches `PacketDecoder._process_packet` (adding a `_dave_decrypt` method) to decrypt each frame using discord.py's own `DaveSession` — the same session object it already maintains for the *sending* side — before handing it to the Opus decoder. No PyPI release of `discord-ext-voice-recv` has this yet, but there's a real, working fix: PR #58 on the project's GitHub (open, unmerged as of 2026-08-20 — the author reports it's been running 24/7 in a production voice bot). Verified by installing that exact fork/branch locally and reading the actual installed source via `inspect.getsource()` — not a summarized diff — then replicated faithfully as a runtime patch, same reasoning as the `PacketRouter` patch above: don't depend on someone's personal fork as a pip dependency for something this central.
  - Also fixed two related robustness gaps found from the same live tests: (1) a second `/join` fired while a first one was still mid-connect (the handshake retry loop can take 25+ seconds) sailed past the `is_active()` check entirely, since `_voice_client` isn't assigned until connect *finishes* — now guarded by a separate `_connecting` flag. (2) if `channel.connect()` returned without raising but the connection wasn't actually usable, the follow-up `.listen()` call raised an exception that was never caught, which left Discord's "thinking..." indicator stuck forever (the interaction never got a followup response) — `start()` now wraps the whole connect-then-listen sequence and always returns a string, cleaning up (disconnecting) if `.listen()` fails after a successful connect.
- **Continuous CPU cost while a session is active.** Vosk decoding is real, ongoing work — unlike everything else in this app, which is pure request/response. Small model keeps this modest, but it's a genuinely different resource profile, worth watching if the Lenovo ever feels loaded during a long `/join` session.
- **Vosk's model choice trades accuracy for speed/size/download** — same kind of tradeoff already accepted for Piper's default voice and Haiku-tier LLM defaults, in keeping with "local and free." The default started on Vosk's tiniest model (~39MB) and had real accuracy problems in practice (2026-08-20) — now defaults to `vosk-model-en-us-0.22-lgraph` (~125MB, bigger vocabulary, verified against the real model list at alphacephei.com/vosk/models, not guessed) via the new `VOSK_MODEL_NAME` setting. Vosk's full model (`vosk-model-en-us-0.22`, ~1.8GB) is more accurate still, at a real CPU/RAM cost per session on hardware with no GPU — set `VOSK_MODEL_NAME` to it if `lgraph` still isn't accurate enough; blank falls back to the original small-model-by-language lookup.
- **The wake phrase only gates what reaches the assistant, not what gets transcribed.** Being in the channel means Sunny's STT is running on everyone in it continuously (same as any other bot/human in a Discord voice channel could theoretically be recording) — the wake phrase decides what gets *acted on*, not what gets *heard*. No wire-level privacy indicator beyond Discord's own. `/leave` is how you stop all of it.
- **`/speak`'s responses are ephemeral** ("only you can see this message") — Discord's ephemeral flag, so the chat channel doesn't fill up with bot command noise. Set at `defer(ephemeral=True)` time; Discord automatically keeps every `followup.send()` for that interaction ephemeral too. Voice presence itself has no slash-command confirmation to make ephemeral anymore (see the 2026-08-24 note above) — the bot visibly joining/staying in the voice channel is seen by everyone in it regardless, same as any human.

## The Four Crashes (2026-08-20, later the same night)

Live testing after the fixes above still shipped produced **four separate native crashes** — process-ending `SIGABRT`/`SIGSEGV`, not a catchable Python exception — each taking the *entire bot* down (web dashboard, all Discord text commands, tasks, alarms, everything) for the ~10s until systemd auto-restarted it:

1. `free(): invalid size` — the `/join` pre-warm task and the first real speaker's on-demand recognizer creation both called `KaldiRecognizer(model, ...)` (native Kaldi construction) concurrently from two different threads off one shared Vosk `Model`. **Fixed**: `stt.py`'s `new_recognizer()` now serializes construction under `_model_lock`, not just model *loading* as before.
2. `free(): invalid pointer` — Discord sends its own literal 3-byte Opus-silence marker (`b'\xf8\xff\xfe'`, see `rtp.py`'s `OPUS_SILENCE`) as a plain, deliberately *unencrypted* `RTPPacket` regardless of DAVE state — confirmed via `voice_recv`'s own `reader.py`, which checks `is_silence()` for an unrelated reason but proves these packets flow through the exact same pipeline as real audio. The DAVE-decrypt patch fed that non-ciphertext buffer into `DaveSession.decrypt()`, which expects real MLS-framed ciphertext far longer than 3 bytes. **Fixed**: skip decrypt when `packet.is_silence()`.
3. `Segmentation fault` — Opus's forward-error-correction path (`_decode_packet`'s fake-packet branch) reads the *next* buffered packet directly via `self._buffer.peek_next()`, bypassing `_process_packet` (and therefore DAVE decrypt) entirely — so on any real packet loss, exactly when FEC recovery kicks in, still-encrypted ciphertext reached `opus_decode()` as if it were real audio. Zero preceding warning, since nothing here ever raised. **Fixed**: decrypt the peeked-ahead packet too, with a double-decrypt guard (DAVE decryption is a real AEAD cipher, not idempotent — a packet that reaches decrypt via both the FEC peek and its own later normal pop must only actually decrypt once, tracked via a small per-decoder set of recently-seen sequence numbers).
4. **`Segmentation fault` again**, ~3.4s after joining, with **zero** preceding warnings, errors, or unusual packets in the log — none of the first three fixes touched this one, and its total lack of a preceding symptom ruled out "one more bad-input edge case" as a complete explanation.

### Root cause of #4 (verified via source inspection, not guessed)

`DaveSession` (the `davey` package, v0.1.6 — a young, pre-1.0, third-party Rust extension by "Snazzah") is touched by **three different OS threads** with **zero synchronization anywhere**, confirmed by direct inspection of the installed `discord.py` and this codebase:

1. **`discord.player.AudioPlayer`** (its own dedicated `threading.Thread`) calls `dave_session.encrypt_opus()` for every outgoing packet — used whenever `/join` plays the wake chime or a spoken reply.
2. **`voice_recv`'s packet-processing thread** calls `dave_session.decrypt()` for every incoming packet — added entirely by this feature's own monkey-patch. Confirmed via `grep` across the whole installed `discord` package: **`discord.py`'s own official code never calls `.decrypt()` anywhere** — voice receive isn't an officially supported `discord.py` feature yet, so this concurrent-with-encrypt access pattern was never part of what `davey` was built or tested against.
3. **The asyncio event loop thread** manages the session's lifecycle (`reinit_dave_session`, key rotation/transitions) in `discord/voice_state.py`.

Confirmed via `grep` for `Lock`/`RLock`/`asyncio.Lock` in `voice_state.py`: **no lock exists anywhere** protecting this shared native object. A data race explains what three sequential single-trigger fixes couldn't: every crash looked different (two distinct heap-corruption signatures, two distinct segfault circumstances) because a race manifests differently depending on timing, not deterministically from one bad input.

### The fix — two layers ("always overdo your fixes")

**Layer 1 — close the actual race**: one process-wide `threading.Lock()` (`voice_worker.py`'s `_dave_lock`), held around *every* call that touches the shared `DaveSession`, both directions — `_dave_decrypt`'s `session.decrypt(...)` call, and a new patch on `discord.VoiceClient._get_voice_packet` (the method that calls `dave_session.encrypt_opus()`) via `_patch_dave_encrypt_lock()`.

**Layer 2 — contain the blast radius regardless**: even with the lock, `davey` 0.1.6 and `discord-ext-voice-recv` 0.5.2-alpha are both young/unofficial enough that no fix can *prove* no other native crash trigger exists. The entire voice pipeline now runs in an isolated child process (`voice_worker.py`, spawned by `voice_session.py` — see Architecture above) specifically so a native crash there can only end that `/join` session, never the rest of the bot. Verified empirically, not just architecturally reasoned: a real worker process was killed with `SIGSEGV` mid-session (`os.kill(pid, signal.SIGSEGV)`) while the main bot was live — `journalctl` showed zero trace of it in the main bot's logs, and the main bot kept running uninterrupted throughout. `process.exitcode` correctly came back `-11` (killed by signal 11), confirming the parent's crash-detection mechanic (`voice_session.py`'s `_watch_worker`) has the signal it needs.

A real bug surfaced during this build, worth recording: the worker's `client.start(token)` call was only ever awaited as a background `asyncio.Task`, with the main coroutine separately `await`ing `stop_event.wait()` — meaning a login failure (or any fatal error from `client.start()` before `on_ready` ever fires) left that task's exception sitting unretrieved forever, and the whole worker process hung indefinitely instead of reporting failure. Found via a deliberate bad-token test, not live — fixed by racing `client_task` against `stop_event.wait()` with `asyncio.wait(..., return_when=FIRST_COMPLETED)` and reporting the failure if `client_task` finishes first.

### Crash #5 — the first lock was incomplete

Deployed the Layer 1 lock above (encrypt_opus/decrypt only) and Layer 2 (process isolation) together. Process isolation worked exactly as intended — a worker crash no longer took the whole bot down, confirmed live: `voice_session: worker process ended unexpectedly (exitcode=-11)` logged cleanly while the main bot kept running, zero disruption to text commands or the dashboard. But the worker itself still segfaulted, ~9s into a session, with **no one even speaking in the channel** — ruling out real-speech-triggered activity as a precondition and proving the first lock's scope was wrong, not just its presence.

`grep dave_session discord/gateway.py` found the actual gap: `set_external_sender()`, `process_proposals()`, `process_commit()`, and `process_welcome()` are the real MLS protocol handlers for incoming key-rotation/commit messages from Discord's voice gateway — called on the asyncio loop thread as the group's cryptographic state updates, which happens periodically during a normal call, not just at connect. The first lock never touched any of these.

**Fix**: stopped trying to enumerate individual call sites scattered across `gateway.py` and `voice_state.py` (exactly how the FEC-peek bug and this one both slipped through) and instead locked `DaveSession` itself — `_patch_dave_session_locking()` wraps every real (`method_descriptor`) method on the class with `_dave_lock`, verified via inspecting `vars(DaveSession)` directly to correctly skip plain attribute reads (`ready`, `status`, `epoch`, ... — `getset_descriptor`, not callable) since wrapping those would silently turn every existing `session.ready`-style boolean read in both `discord.py` and this file into a bound method object instead.

**Verified against the real bot, not just reasoned about**: an automated test joined the real voice channel and held for 2 minutes with a spoken message every 5s (23 encrypt-path calls) — 4 consecutive clean runs post-fix, versus consistent ~9s crashes on the same test before it. The one thing this can't cover is the decrypt side under real, sustained human speech (packet loss, real MLS traffic patterns) — that still needs a live test.

## Streaming Replies + Barge-In (2026-08-21/22)

Two follow-up improvements after the crash-fixing above, not yet reflected in the Architecture diagram (still text-only round-trip there — this section covers what changed):

- **Streaming replies**: `/join` now starts speaking the first sentence of an open-ended answer while Claude is still generating the rest, instead of waiting for the whole response — `ask_claude_stream()` (see [[llm-integration]]) splits at sentence boundaries and each chunk is synthesized/queued for playback as soon as it's ready, rather than one big `synthesize_discord_pcm()` call after the full text arrives. A short "thinking" audio cue plays during the gap while a slow reply is still generating.
- **Barge-in**: saying "Hey Sunny" again while Sunny is still talking stops the current audio immediately and discards anything else queued or still being synthesized for the interrupted response, instead of talking over it — the playback queue is generation-tagged so a new wake-word detection can invalidate everything from the prior turn in one step.
- Reused Anthropic API clients across calls instead of reconnecting per request (latency win, unrelated to voice specifically but most noticeable here).
- A real regression fixed: the wake word plus a natural pause before the actual sentence could get split into two separate utterances, silently dropping the second half — the wake-window logic above now tolerates that pause correctly.

## Persistent Voice Presence + Conversation Memory (2026-08-24)

Two changes, requested together but genuinely separate:

**Persistent presence, no more `/join`/`/leave`.** New `voice_presence_loop` (`discord_bot.py`, `@tasks.loop(seconds=30)`) reconciles actual state against desired state every tick: `service_registry.is_enabled("voice_join")` and `DISCORD_VOICE_CHANNEL_ID` configured → connected; either false → disconnected. This is the same "every loop checks `is_enabled()` at the top of its tick" pattern [[service-orchestration]] already established for the other five services — `voice_join` was already one of them, previously just gating whether `/join` was accepted at all; now it gates the persistent connection itself. `/service voice_join enable|disable` is the only control surface — takes effect within one tick, same as any other service. Reconnects automatically after a drop or a worker crash (previously required a manual `/join` again); `notify_fn`'s crash message updated accordingly.

`voice_session.start()` no longer takes a Discord `interaction` — it takes a `discord.VoiceChannel` directly, resolved by the loop via `client.get_channel(voice_channel_id)`. There was no other real caller to update; the whole point of the old signature (deriving the channel from `interaction.user.voice.channel`) only made sense for a per-use slash command.

**"Hey Sunny" is still required before every request** — explicitly kept, not removed, when this was scoped: an always-listening open mic that acts on any speech in the channel has real false-trigger and privacy implications neither asked for nor wanted here. Being persistently connected only changes *when* Sunny is in the channel, not the wake-word gate described above.

**Session-scoped conversation memory** — new `conversation_memory.py`, wired into `briefing.py`'s `custom_briefing()` general-chat fallback (the genuinely open-ended LLM path, not the deterministic weather/calendar/task branches, which stay stateless by design). Up to 3 recent user/assistant exchanges per `session_id`, prepended as plain text to the next prompt, so a real follow-up ("why", "tell me another one") resolves instead of landing as a fresh, context-free question. In-memory only — resets on restart, never written to the vault, deliberately not the bigger "remembers things across days" scope. Same `session_id` voice already used for `handle_message()`'s pending-followup mechanism, so voice and text chat in the same session share memory naturally.

## Not Included This Pass

- **No persistent transcript log** — exchanges are logged via the normal Python app logger only, not a new `sunny-vault/log/` file. A natural addition later if wanted; not built ahead of an actual need.
- **No STT/TTS tuning for the voice pipeline specifically** — Piper's existing tuning knobs (`PIPER_LENGTH_SCALE` etc., see [[tts-piper]]) still apply to spoken replies. No equivalent Vosk knobs (bigger model, different language) yet — natural follow-up if accuracy needs it.

## Latency

Reported "very very bad" delay on a live test, 2026-08-20. Root-caused with real data from the timing instrumentation below, not guessed:

- **The response pipeline itself is fast** — first real numbers: `route=0.19s tts=2.00s total(heard→playing)=2.20s` (the `tts` figure includes Piper's one-time first-call model load, same ~1.2–2s cost `/speak` already has). Not the problem.
- **The actual bottleneck: the gap between one utterance finishing and the next being "heard"** — 5+ seconds observed between consecutive `heard from` log lines for what was continuous, back-to-back speech. That gap happens entirely *before* any of the instrumented timing starts, inside Vosk's own `AcceptWaveform()` — which only finalizes a segment once it decides there's been enough trailing silence. Confirmed directly (`KaldiRecognizer` has no `SetEndpointerMode`/silence-timeout method — checked the actual class, not guessed) that the simple Vosk Python API exposes no way to shorten this. A synthetic loopback test with exactly 2s of true digital silence appended finalized promptly; real Discord audio — room tone, mic hiss, never *quite* silent — likely needs much longer to read as "silence" to Vosk's endpoint detector, explaining the gap between that clean test and the live numbers.
- **Fix: stopped waiting on finalization for the wake-word chime.** Vosk's `PartialResult()` (new `stt.partial()`) gives the decoder's in-progress hypothesis with far lower latency — confirmed in the same loopback test, the wake word showed up in a partial at 0.34s into processing, well before the segment finalized. `on_audio` now checks partials for the wake word and fires the chime immediately on a match, per user, once per utterance (`chimed` flag, reset when the segment finally finalizes) — `handle_utterance` skips replaying it if the early check already did. The *command* itself still waits for the final, complete text (partials are a hypothesis, not final — using them for the wake word only, not the command content, keeps this safe: worst case on a flickering partial is a stray chime with nothing following, never a wrong action).
- **Also fixed**: `_get_model()` had a real thread-safety bug the pre-warm change exposed — the pre-warm task and the first real audio packet could both see the model as unloaded at once and each build a separate `Model` instance (confirmed live: two "Vosk model ready" log lines back to back). Now guarded with a `threading.Lock`; verified with 5 concurrent callers producing exactly 1 load.
- **Vosk model pre-warmed during `/join`'s connect**, in parallel with the voice handshake, so the first real utterance doesn't pay the model-load cost while blocking `discord-ext-voice-recv`'s own audio-decode thread.

**The real root cause, found on the very next live test**: after the chime fix, the chime fired fast — but no response ever followed. Logs showed why: after one brief burst of packets at the very start, **zero audio packets arrived for the remaining ~50 seconds** of the session, just Discord's once-a-second RTCP keepalive. Discord's voice transport doesn't send "quiet" audio packets during real silence — it simply stops sending anything. That's the actual reason `AcceptWaveform()` was never finalizing: it's stream-based silence detection, and once the speaker pauses, there's no more stream at all for it to detect silence *in*. Confirmed directly: `stt.finalize()` (new, wraps `FinalResult()`) correctly recovered the complete buffered text from a recognizer that `AcceptWaveform()` had never once finalized, in a loopback test with no trailing silence fed at all.

**Fix**: a `silence_watchdog()` coroutine (started alongside the session) polls every `SILENCE_WATCHDOG_INTERVAL` for any user whose last audio packet was more than `SILENCE_TIMEOUT` ago while their recognizer still has unfinalized buffered audio (`pending` flag, set in `on_audio`, cleared on natural or forced finalization) — and force-finalizes via `stt.finalize()`, using the *absence* of packets as the actual end-of-utterance signal instead of waiting on Vosk to notice silence it's never fed. Verified via a mocked test reproducing the exact failure: speak (chime fires from partial, buffering continues), go silent (no more `on_audio` calls at all), watchdog fires and the response follows.

**Retuned 2026-08-21**, after live testing with the fix above still shipped: `SILENCE_TIMEOUT` was originally set to a guessed 1.2s (with `SILENCE_WATCHDOG_INTERVAL` at 0.3s) — live measurement showed raw Vosk compute (~0.8s/utterance) mostly overlaps with the user still talking and is largely hidden, but this post-speech wait, which only starts once they stop, was not, making it the actual dominant cost in real, live latency. Lowered to `SILENCE_TIMEOUT = 0.3` (`voice_worker.py`) to hit a sub-0.3s post-speech target, with `SILENCE_WATCHDOG_INTERVAL` tightened to `0.05` (cheap — a dict iteration + a few time comparisons, 20x/sec) so the polling granularity doesn't stack meaningfully on top of `SILENCE_TIMEOUT` itself. Real tradeoff, not a free win: 0.3s of true silence is short enough that a natural mid-sentence pause (a breath, an "um") can plausibly get finalized as the end of the utterance — worth raising back toward 0.5–0.6s if that starts happening in practice, rather than all the way back to 1.2s. (This same retuning is also what made `WAKE_TO_COMMAND_GRACE`, 4.0s, necessary — see the wake-phrase section above: without it, a bare "Hey Sunny" followed by a natural pause before the actual sentence got finalized as its own complete utterance and silently dropped, confirmed live 2026-08-21.)

## Files

- `sunny_code/components/stt.py` — Vosk model loading (`_model_lock`-guarded, covering both model load *and* `KaldiRecognizer` construction — see crash #1 above), `new_recognizer()`, `resample_to_16k_mono()`, `feed()`
- `sunny_code/components/tts.py` — `synthesize_discord_pcm()` (alongside the existing `synthesize_wav_bytes()` used by `/speak`)
- `sunny_code/voice_worker.py` — the isolated worker process (see Architecture above): its own `discord.Client`/gateway session, the actual voice connect, all monkey-patches (`PacketRouter._do_run`, `PacketDecoder._process_packet`/`_dave_decrypt`/`_decode_packet`, `VoiceClient._get_voice_packet` — see Known Risks and "The Four Crashes"), per-user recognizers, wake-phrase gating, the generated wake chime, the `silence_watchdog()` coroutine, TTS playback, and the `multiprocessing.Queue`-based IPC with the parent (`run_worker()`, the process entry point)
- `sunny_code/components/voice_session.py` — the parent-side coordinator: spawns/monitors the worker (`start()`/`_watch_worker()`), relays `"utterance"`/`"speak"` messages through `assistant.handle_message()` (`_relay_from_worker()`), tears it down (`stop()`)
- `sunny_code/components/discord_bot.py` — `voice_presence_loop`; passes a `notify_fn` callback into `voice_session.start()` so a mid-session worker crash posts to the Discord warnings channel immediately, not just on the bot's next startup
- `sunny_code/components/conversation_memory.py` — session-scoped memory for the general-chat LLM fallback (see the 2026-08-24 section above)
- `sunny_code/config.py` — `vosk_model_dir`, `vosk_lang`, `vosk_model_name`, `discord_voice_channel_id`
- `vosk_models/` (gitignored) — downloaded model files

## Dependencies

- [[tts-piper]] — reuses `synthesize_wav_bytes()`, and is the doc this one supersedes the "Deferred: /join" section of
- [[voice-io]] — the full hardware-bound pipeline this is a software-only, Discord-only slice of
- [[discord-bot]] — hosts the commands, guild sync, channel restriction
- `sunny_code/components/assistant.py` — `handle_message()`, the shared router this reuses unchanged

## Implementation Checklist

- [x] `stt.py` — Vosk wrapper, verified via an automated loopback test (Piper → resample → Vosk → exact transcript match); `partial()` for low-latency wake detection, `finalize()` for the silence watchdog, `_get_model()` thread-safety verified with 5 concurrent callers
- [x] `tts.py: synthesize_discord_pcm()` — verified PCM format/frame-padding math
- [x] `voice_session.py` — connect/listen/dispatch/respond/disconnect, verified via mocked Discord objects (bot-user filtering, mid-utterance buffering, session_id construction, full response pipeline)
- [x] `/join`/`/leave` slash commands, channel-restricted (historical — removed 2026-08-24, see the persistent-presence section above; `channel.connect()`/registration verification below still stands, just triggered differently now)
- [x] Connect + command registration verified live against the real Discord API (3 commands registered, `channel.connect()` succeeds)
- [x] `libopus0` installed on the Lenovo (`sudo apt-get install -y libopus0`) — send-side re-verified after: real connect → real Piper synthesis → real Opus encode → real playback → clean disconnect, all against the live bot
- [x] Real end-to-end attempts with a live human voice caught three real bugs in turn, each only findable live: the `PacketRouter` crash-on-single-decode-error, the DAVE requirement/decrypt issue (two wrong turns before the real fix — see Known Risks), and an unguarded `.listen()` failure leaving Discord's "thinking..." stuck forever with no response
- [x] Wake phrase ("Hey Sunny"/"Hello Sunny"/"Sunny") required before every separate utterance — verified via mocked session tests (ignored with no wake word, processed + stripped on wake, bare wake word arms `WAKE_TO_COMMAND_GRACE` for the immediately-following command without a false action). Historical: a 2026-08-20 `WAKE_WINDOW_SECONDS` (20s) design let follow-ups skip the repeat; reverted 2026-08-21 per direct request back to a wake word on every request.
- [x] Fuzzy wake-word matching (`difflib.SequenceMatcher`, threshold 0.6, scans first 4 words) — first version used an exact prefix match and essentially never fired against real speech; verified against the actual mis-transcriptions from a live test ("the sunny it up", "a sony what's the one", "comfort" correctly rejected)
- [x] Generated wake-confirmation chime (`_get_chime_pcm()`, ~200ms two-tone), plays immediately on wake-word detection — verified via mocked session tests (plays on a bare wake word, plays before the response on wake+command)
- [x] `_connecting` guard against overlapping `/join` attempts, and guaranteed-honest-response error handling around connect/listen — verified via mocked tests (listen() failure cleans up and reports instead of crashing; a second /join mid-connect is rejected)
- [x] All three commands' responses ephemeral (`defer(ephemeral=True)`) — verified via mocked tests
- [x] Early wake-chime from partial results, not finalization — verified via mocked tests (fires once from a partial match, doesn't double-fire while still buffering, doesn't replay when the utterance finalizes)
- [x] `silence_watchdog()` — no-packets-for-`SILENCE_TIMEOUT` force-finalization, since Discord's transport sends nothing at all during real silence rather than quiet audio Vosk could detect — verified via a mocked test reproducing the exact live failure (speak, go silent, response still arrives)
- [x] Vosk `KaldiRecognizer` construction serialized under `_model_lock`, not just model loading (crash #1) — root-caused via exact crash timing correlation (a "free(): invalid size" abort ~1s after "Vosk model ready", before any transcript was ever heard), fixed and deployed
- [x] DAVE-decrypt skipped for Discord's literal Opus-silence marker packets (crash #2) — root-caused by tracing exactly which packets reach `_dave_decrypt` and confirming `is_silence()` frames are genuinely unencrypted plaintext by design, fixed and deployed
- [x] DAVE-decrypt applied to the Opus FEC peek-ahead packet too, with a double-decrypt guard (crash #3) — root-caused by reading `_decode_packet`'s fake-packet branch and finding it reads the jitter buffer directly, bypassing decrypt entirely, fixed and deployed
- [x] The actual unifying root cause (crash #4) — a data race on `DaveSession`, called from 3 unsynchronized OS threads — found via direct source inspection (confirmed no lock exists anywhere in `discord.py`'s `voice_state.py`), not guessed
- [x] Layer 1: `_dave_lock` serializing every `encrypt`/`decrypt` call on the shared `DaveSession` (`voice_worker.py`'s `_patch_dave_encrypt_lock()`)
- [x] Layer 2: entire pipeline moved into an isolated worker process (`voice_worker.py`) spawned/monitored by `voice_session.py`, so a native crash can only end one `/join` session — verified empirically via a real `SIGSEGV` kill mid-session (main bot logs showed zero trace, kept running uninterrupted; `process.exitcode` correctly came back `-11`)
- [x] A real bug found during this build (not live): `client.start()`'s exception was never observed when only awaited as a background task, hanging the whole worker forever on a login failure — found via a deliberate bad-token test, fixed with `asyncio.wait(..., return_when=FIRST_COMPLETED)` racing it against the shutdown signal
- [x] The "second `discord.Client`, same token, joins voice while the main bot is already connected" assumption behind the whole worker-process design — verified live against the real bot before building the rest, not assumed
- [ ] Re-verify with a live human voice now that all four crash fixes and the process-isolation rebuild are deployed — this is the one thing that categorically needs a real person talking, not a script
- [x] `voice_presence_loop` — connects/reconnects/disconnects based on `is_enabled("voice_join")` + `discord_voice_channel_id`, code-reviewed against the existing per-tick `is_enabled()` pattern from the other five services
- [x] `voice_session.start()` refactored to take a `discord.VoiceChannel` directly instead of a Discord interaction — no other real caller existed to update
- [x] `conversation_memory.py` — turn recording/formatting/per-session isolation/cap-at-6-turns, verified with a real test script (9/9 checks passing)
- [x] Live-verified the persistent-presence loop's reconnect, 2026-08-25 against the real Lenovo deployment: `kill -9` on the worker process (PID confirmed via `ps`) → `voice_session` logged the crash (`exitcode=-9`) within one tick → `voice_presence_loop`'s next 30s tick spawned a fresh worker → full voice handshake/DAVE/Vosk reconnect completed 33s after the kill, no restart, no manual `/join`. `DISCORD_VOICE_CHANNEL_ID` was previously unset on the live deployment (a config gap, not a code bug) — set it as part of this test.
- [ ] Live-verify conversation memory produces a coherent follow-up against real Claude output — still only unit-verified (9/9 checks on `conversation_memory.py` directly), not confirmed against a real multi-turn exchange yet
