---
id: roadmap-2026-09
type: planning
status: active
created: 2026-09-20
tags: [roadmap, timeline, planning, garmin, pwa, memory]
---

# Roadmap — September 2026

Sequenced plan for the 13 items raised 2026-09-20. Complements [[BACKLOG.md]]
(unscoped item list) and [[phases.md]] (historical build timeline) — this doc is
specifically *what order, and why*. Pull each stage into `phases.md` as it starts.

Effort sizes are XS/S/M/L. Dates are indicative from 2026-09-20 assuming part-time
evenings — treat the **order** as the commitment and the dates as an estimate.

---

## Decisions locked (2026-09-20)

| Decision | Choice | Consequence |
| --- | --- | --- |
| Messaging transport | **PWA only, no Telegram** | Nothing leaves the tailnet. iOS push via Web Push (payloads encrypted client-side, RFC 8291). Requires the existing Tailscale cert + a service worker. |
| Garmin headline metric | **Composite 0-100 "Sunny Readiness"** | Transparent weighted blend, not a clone of Bevel's proprietary score. Weights live in config and get tuned after real data exists. |
| GPU for voice | **Try the GTX 970 in TrueNAS first** | Maxwell (sm_52). Works only pinned to CUDA 12.6/12.7 — PyTorch dropped Maxwell in cu128 builds (2.8+), CUDA 13.0 dropped everything below Turing. Borrowed time, not a solution. |
| TrueNAS edition | **SCALE** | Linux + Docker + NVIDIA driver support. GPU inference runs as a container on the tailnet; the CUDA pin is isolated inside it. |
| Pi display | **Single pygame app, no browser** | GUI required by the Waveshare screen, but Chromium doesn't fit alongside it. See Stage F. |
| Brief period selection | **Explicit words win, window sets the default** | "good morning" at 2am gives the morning brief. Opening the app at 2am with no request gives nightly. |
| Logging day boundary | **05:00, not midnight** | Shared constant with the brief window. A migraine logged at 2am files against the previous day. |

---

## Why this order

Two constraints drive the sequence.

**Capture can't be backfilled.** Garmin Connect retains sleep/HR/Body Battery/load
history server-side, so most metrics can be recovered later. Daily check-in answers
cannot. Every night without the migraine question is a permanently missing row — so
capture goes first, before anything that displays or reasons over it.

**No more orphan infrastructure.** Sunny already has `vault_permissions.py`,
`context_engine.py` and `exam_prep.record_review()` built with no callers. Every stage
below ships a producer and a consumer in the same pass. Memory lands late specifically
so it has real material to remember, rather than being an empty store looking for input.

---

## Stage A — Start logging · S · ~Sep 22-26

Capture only. No score, no dashboard, no reasoning.

- [ ] `garminconnect` auth via `garth`, token cached to disk (~1yr before reauth)
- [ ] Daily pull job — once or twice a day, never polling
- [ ] `metrics(name, ts, value)` table, replacing the dead fixed-column one at
      `dashboard.py:51` (nothing has ever written to it)
- [ ] Backfill script for whatever history Connect will return
- [ ] Daily check-in framework — generic, migraine as its first question, delivered
      through the existing Discord nightly brief
- [ ] Barometric pressure logged on the same row from the existing weather API
- [ ] `DAY_BOUNDARY_HOUR = 5` as one shared constant

**Closes:** #7 (data half), #8
**Prereqs on you:** confirm the watch reports HRV Status; enable overnight Pulse Ox
if you want SpO₂ (off by default, costs battery).

> Barometric pressure is captured here rather than in Stage D on purpose. Migraine
> correlation needs both series to start on the same day; adding pressure later leaves
> a permanent hole in the useful half of the dataset.

---

## Stage A2 — Vault sync · M · ~Sep 22-Oct 3 (parallel with A)

Runs alongside Stage A rather than after it — this is server infrastructure, not
Sunny code, so the two don't collide.

### Why Syncthing is failing

Two causes, and the first one is probably decisive:

1. **No viable Syncthing client on iOS.** There is no official one. Möbius Sync is
   third-party, and iOS background execution limits mean it effectively only syncs
   while foregrounded. The phone drifts out of date, then reconciles a pile of stale
   edits against a moved-on desktop — which is exactly how `sync-conflict-*` files
   breed.
2. **Three writers on one tree.** You on desktop, you on phone, and Sunny writing
   markdown on the server continuously. Syncthing resolves conflicts by keeping both
   copies; it has no concept of "the server owns this file and I own that one."

- [ ] **Recommended: self-hosted [obsidian-livesync](https://github.com/vrtmrz/obsidian-livesync)** — CouchDB in a
      container on TrueNAS SCALE, reachable over Tailscale. Chunk-level sync with
      real conflict resolution, proper iOS support, free, self-hosted. It fits every
      constraint already committed to: nothing leaves the tailnet, no subscription,
      and the box to run it on is already there.
- [ ] Keep git as the history/backup layer. LiveSync is for *sync*; git is for
      *recovery*. Don't collapse the two.
- [ ] Structural fix, independent of tool choice — see below

| Option | Cost | iOS | Verdict |
| --- | --- | --- | --- |
| **Self-hosted LiveSync** | free | good | **Recommended** — needs TrueNAS SCALE + Tailscale, both already in place |
| Obsidian Sync (official) | ~$4-8/mo, verify current tiers | best | Works flawlessly, but third-party cloud — the same objection that killed Telegram |
| obsidian-git | free | poor | iOS support exists but is slow and unreliable on real vaults; markdown merge conflicts are worse to resolve than conflict files |
| Syncthing (current) | free | **unviable** | The iOS gap is not fixable |

**Caveats on LiveSync:** setup is fiddly (CouchDB CORS config in particular), the
database grows and wants periodic compaction, and initial sync on a large vault is slow.
Budget an evening, not an hour.

### The structural fix (do this regardless of sync tool)

No sync tool can cleanly resolve two writers editing the same file. So stop creating
that situation:

- **Machine-owned** — tasks, lists, logs, generated summaries. Sunny writes, you read.
  Already mostly true: one markdown file per task, and `vault_io.atomic_write_text`
  handles the write safely.
- **Human-owned** — `personality.md`, `profile.md`, `instructions/*.md`. You write,
  **Sunny only ever reads.**
- Where Sunny wants to change a human-owned file, it writes a proposal to
  `memory/suggestions.md` and you merge it deliberately. Sunny never edits those files
  in place.

That last rule is what keeps Stage B's personality file and Stage G's memory system
from becoming the single worst source of conflicts in the vault — both are files you
and Sunny would otherwise both want to write.

**Closes:** #15

---

## Stage B — Capture speed + brief windows · S · ~Sep 29-Oct 3

- [ ] `components/extract.py` — one Claude tool-use call, JSON schema, returns typed
      fields plus a confidence. Three callers land immediately:
- [ ] **Assignment capture (#11)** — "quiz 3 in physics due friday" → one extraction →
      `{title, due_date, category, class}` → Calendar all-day event + task, one turn,
      no wizard
- [ ] **Reminders (#3)** — keep `scheduled_parser.py` regex as the fast path, add
      extraction as the fallback instead of the current error
- [ ] **Category (#3)** — infer from title against `category_store`, auto-file above
      ~85% and say which one, ask only below that
- [ ] **Brief windows (#12)** — one `active_brief_period(now)`: daily 05:00-18:30,
      nightly 18:30-05:00. Every consumer calls it instead of deriving its own edge.
      Fix the alarm-prewarm boundary in `scheduled_check_loop`.
- [ ] Thin memory hook — hand-edited `sunny-vault/memory/profile.md` injected into the
      chat prompt, plus "remember that…". Proves the injection path for Stage E.
- [ ] **Personality file (#16)** — see below

**Closes:** #3, #11, #12, #16

### Tunable personality

`sunny-vault/personality.md` — frontmatter dials plus a freeform body:

```yaml
---
verbosity: 3      # 1 terse … 5 thorough
formality: 2      # 1 casual … 5 formal
humor: 3
bluntness: 4      # how directly to disagree with me
proactivity: 3    # how readily to volunteer things I didn't ask for
---
```

- [ ] Applies across **every** interface — chat, voice, briefs — not just the general-chat
      fallback. `instructions/general-chat.md` already exists as a hand-editable prompt;
      this generalizes that idea instead of duplicating it.
- [ ] Hot-reload on mtime change, so editing it in Obsidian takes effect without a restart
- [ ] Fail quiet — a malformed file logs and falls back to last-good, never breaks Sunny
- [ ] `bluntness` and `verbosity` should also reach `tts_delivery.py`, which already
      varies pace by message type

**This file is human-owned.** Sunny reads it and never writes it — see Stage A2's
structural fix. Personality proposals go to `memory/suggestions.md` for you to merge.

> `personality.md` (how Sunny behaves) and `profile.md` (who I am) are deliberately two
> files. They blur easily, and merging them makes both harder to tune.

### Three real bugs in the category flow

1. Asks on every add with no inline tag, even when obvious
2. `_finish_task_with_category` (`assistant.py:539`) accepts any string — a typo
   silently creates a phantom category
3. The `_looks_like_a_command` guard (`assistant.py:753`) can swallow your answer and
   route it to an unrelated feature

---

## Stage C — Gmail fix + diagnosability · XS · ~Oct 6

Small, but it's blocking trust in the website panel.

- [ ] Determine root cause live: `curl /api/gmail/flagged` and `/auth/google/status`
      on the Lenovo. The route exists and is mounted correctly (`main.py:264`), so it
      is *not* a missing endpoint.
- [ ] Likely: `_service()` returns None — creds expired, or the stored token predates
      the `gmail.readonly` scope. Status checks credentials, not scopes, so the status
      row reports "OK · email" while the mail panel says not connected.
- [ ] Stop `sunny_client.gmail_flagged()` (`sunny_client.py:177`) converting every
      failure into `{"available": False}`. That tolerance existed because the endpoint
      didn't exist yet; now it hides real errors. Same for `calendar_today()`.
- [ ] Surface the real reason in the UI — "token expired", not a generic placeholder

**Closes:** #14

---

## Stage D — Readiness score + workouts · M · ~Oct 7-17

Runs after Stage A has accumulated ~3 weeks of data. Tuning weights on three days
would be guessing.

- [ ] **Sunny Readiness (0-100)**, weights in config:
      - Training Readiness — 40%
      - Body Battery at wake — 25%
      - Sleep score — 20%
      - Acute:chronic load ratio, penalized outside the 0.8–1.3 band — 15%
- [ ] Tracked and charted but **not** scored: RHR delta vs 30-day baseline, overnight
      HRV vs baseline, respiration rate, SpO₂, skin temperature
- [ ] Workout windows — free gaps ≥45min over the next 48h from Calendar, ranked by
      readiness. First real caller for `rules_engine.py` and `vault_permissions.py`.
- [ ] Brief sections for readiness, sleep, step goal, workout suggestion

**Closes:** #7 (reasoning half)

> Not cloning Bevel. Bevel scores RHR, HRV (RMSSD during sleep), respiratory rate,
> SpO₂ and wrist temperature — but it runs on Apple Health, and Garmin's Training
> Readiness *already* blends sleep, HRV, recovery time and acute load internally.
> Stacking Bevel's input list on top double-counts the same signals. Those inputs are
> still worth charting as context, which is why they're tracked-but-unscored above.

---

## Stage E — PWA · M · ~Oct 20-31

`assistant.handle_message()` is already the shared core every interface routes
through, so this is an adapter, not a rewrite.

- [ ] Installable PWA over the existing Tailscale cert, service worker, Web Push
- [ ] Real threaded chat with SSE streaming — `pages.py:300` is a one-shot form today
- [ ] One session/history store, so a thread started on the phone continues on the laptop
- [ ] Push for reminders, alarms, deadline pings — everything currently stuck in Discord
- [ ] Windows: same app installed from Edge as an app window

**Closes:** #1 (chat half), #5 (messaging half)

Discord stays untouched throughout. Nothing gets removed until the PWA has earned it.

**Known limitation:** iOS can evict service workers, so PWA push is less reliable than
a native app. Expect to occasionally reopen the app.

---

## Stage F — Dashboards · M · ~Nov 3-14

- [ ] One reusable chart component with a stock-style range selector
      (1D/1W/1M/3M/1Y/ALL) against `GET /api/metrics/series`. Built once, pointed at
      spend, readiness, sleep, migraine, workouts, server stats. uPlot or Chart.js on
      the web; keep matplotlib for Discord images.
- [ ] Health metrics panel on the website, migraine included
- [ ] **Server stats (#13)** — small exporter on TrueNAS and the Lenovo pushing into
      the same metrics store. Same plumbing as the rest of this stage, so nearly free.
- [ ] **Pi (#4)** — `GET /api/companion/snapshot` returning calendar + weather + usage
      + tasks in one payload. Panes rotate when idle, face takes over when you talk.

**Closes:** #4, #9, #10, #13

### Pi: one pygame app, no browser

The Waveshare screen requires a GUI, which kills the original `cog --platform=drm`
kiosk plan from `BUILD_PLAN.md` Phase 2. But a GUI doesn't require a browser, and on
a **Pi 3 Model B with 1GB RAM** that distinction decides the whole design:

| Component | RAM |
| --- | --- |
| Full PIXEL desktop, idle | ~350-450MB |
| Chromium, one tab | ~300-500MB |
| pygame face renderer | ~50-80MB |
| Wake word + audio | ~100MB |

Desktop + Chromium + face does not fit; it swaps to the SD card, which is slow and
wears the card out. So: **one fullscreen pygame app renders both the dashboard panes
and the face**, extending the existing `pi-client/face_renderer/renderer.py` rather
than restarting Phase 4 a second time. One process owns the screen, so there's no
handoff problem. Charts on the Pi are sparklines, not the full range-selector
component — correct at that screen size anyway.

**Worth testing once:** if the GUI was only needed to *configure* the screen, a bare X
session running just the pygame app (no PIXEL desktop) recovers 300-400MB.

---

## Stage G — Memory · L · ~Nov 17-28

Deliberately late. By now check-ins, workouts, chat history and completed tasks exist
as material to remember.

- [ ] **Profile** — one slow-changing doc: how I think, how I plan, my flaws, standing
      preferences. LLM-proposed, hand-edited, always injected.
- [ ] **Episodic facts** — small vault notes with frontmatter (type, confidence,
      source, date), indexed in SQLite
- [ ] **Patterns** — derived weekly over the episodic layer plus the metrics.
      "Workouts get skipped in weeks with 3+ deadlines." "Migraines follow nights
      under 6h."
- [ ] **Debrief (#6)** — dump what happened, LLM asks 1-2 clarifying questions, then
      commits to memory or tasks. This is the write path.
- [ ] **Retrieval** — local embeddings (sentence-transformers, free, CPU-fine) feeding
      `context_engine.build_context()`, which exists today with no caller. That feeds
      briefs and chat.

**Closes:** #2, #6

> The debrief is the primary input on purpose. Scraping every message instead produces
> noise that takes months to clean out of a memory store.

---

## Stage H — Voice · L · ~Dec

- [ ] GPU inference sidecar container on TrueNAS SCALE, `/tts` and `/stt` on the tailnet
- [ ] Kokoro for TTS, faster-whisper for STT (CTranslate2, not PyTorch — sidesteps the
      Maxwell problem entirely)
- [ ] Sunny falls back to local Piper/Vosk when the sidecar is unreachable, same
      fail-quiet contract as every other integration
- [ ] Streaming/partial-hypothesis STT — the actual latency gap, per [[BACKLOG.md]]

**Closes:** #5 (voice half)

**Risks:** 3.5GB usable VRAM (fine for Kokoro at 82M params). The CUDA 12.6 pin can
never move. A 970 spinning up inside an otherwise idle-efficient NAS costs power.

---

## Item index

| # | Item | Stage |
| --- | --- | --- |
| 1 | Website chat + info sharing | E, F |
| 2 | Memory system | G (thin version in B) |
| 3 | LLM-run reminders + category fix | B |
| 4 | Pi rolling dashboard | F |
| 5 | Better TTS/STT + off-Discord messaging | E (msg), H (voice) |
| 6 | Debrief flow | G |
| 7 | Garmin body metrics + workout cross-ref | A (data), D (reasoning) |
| 8 | Nightly migraine check-in | A |
| 9 | Health metrics on dashboard | F |
| 10 | Chart timespan selector | F |
| 11 | Quick assignment capture | B |
| 12 | Brief display windows | B |
| 13 | Server stats tracking | F |
| 14 | Gmail broken on website | C |
| 15 | Obsidian sync without conflict hell | A2 |
| 16 | Tunable personality file | B |

---

## Open questions

- [ ] Watch model — does it report HRV Status? (blocks part of Stage D's scoring)
- [ ] Is Pulse Ox worth the battery cost for SpO₂?
- [ ] Does the Waveshare screen need the GUI at runtime, or only for setup? (Stage F)
- [ ] Readiness weights are a first guess — revisit after ~1 month of data
- [ ] When does Discord actually get retired, if ever? (post-Stage E decision)
- [ ] Sync: self-hosted LiveSync, or pay for Obsidian Sync and be done with it? (Stage A2)
- [ ] Which existing vault files does Sunny currently write that I also hand-edit?
      Audit before A2 — those are the actual conflict sources.

## Explicitly not doing

- **Telegram** — rejected 2026-09-20 to keep message content off third-party servers
- **Native Windows exe** — the PWA installs as an app window and covers it. An exe
  only adds a global hotkey and always-on desktop mic; revisit if those are missed.
- **Cloning Bevel's score** — proprietary weights, Apple Health inputs, and it would
  double-count what Training Readiness already blends
- **Buying a GPU** — not until the 970 is proven inadequate
