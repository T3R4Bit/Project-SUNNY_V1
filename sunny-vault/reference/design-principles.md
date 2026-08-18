---
id: sunny-principles
type: reference
status: active
source: notion
created: 2026-08-18
tags: [principles, design, philosophy]
---

# Design Principles

Core philosophy guiding all Sunny development.

## Templates First, Tokens Last

The morning briefing is a fixed script with slots filled from APIs. No LLM call needed for facts.

**Application**: Calendar, weather, task summary, commute time — all deterministic lookups. The LLM is never asked "what's the weather?" or "what's on my calendar?" Answers come from direct API calls.

**Why**: Minimize token spend on retrieval. Reserve LLM for judgment.

---

## LLM Only for Judgement

Email triage, task interpretation, freeform phone conversation — these genuinely need semantic understanding and context. Use the LLM here.

**Application**: 
- Read incoming email, decide if it's urgent or can wait
- Interpret vague task ("fix the car") into concrete action
- Have a real conversation over the phone

**Not for**:
- Checking facts (weather, calendar, traffic)
- Formatting output (briefing template)
- Routing logic (pattern matching)

**Why**: Maximize LLM value where it actually helps. Avoid wasting tokens on deterministic operations.

---

## No LLM for Information Lookups

Any time Sunny is checking or fetching information, it must use direct API calls or deterministic logic, **never routing through the LLM** unless genuine judgement is actually required.

**Applies globally** across every feature:
- Calendar events → Query calendar API, not LLM
- Weather → Query weather API, not LLM  
- Traffic/commute → Query maps API, not LLM
- Financial emails → Pattern match or shallow parse, flag for human review if needed
- API status → Check service status page, not LLM
- Location → Tailscale or location API, not LLM

**Why**: Reduces latency, reduces cost, increases reliability. APIs are fast and cheap; LLM is slow and expensive.

---

## Sonic API for Fluent Voice

Use Sonic API for TTS to produce natural, fast voice output. Fall back to local Piper TTS if Sonic is down or for cost-saving during long conversations.

**Application**:
- Primary: Sonic API (costs a few cents per call, sounds natural)
- Fallback: Piper TTS (free, local, acceptable quality)
- Suggestion: During long conversations (20+ minute call), offer to switch to Piper to save cost

**Why**: Natural voice feels more like a personal assistant. Fallback ensures alarm works even if API is down.

---

## Fail Quietly

If the weather API is down, the alarm still goes off. Missing an alarm is worse than missing weather.

**Application**: 
- If weather API fails → Briefing continues without weather, note it in Discord #warnings
- If traffic API fails → Commute time not available, briefing continues
- If Sonic API fails → Fall back to Piper TTS, briefing continues with robot voice
- If email API fails → Skip email triage, briefing continues with "email unavailable"

**Never**:
- Crash the process
- Hang waiting for an API
- Omit the entire briefing if one section fails

**Why**: Sunny is a bedside alarm first. Everything else is a bonus feature. Reliability is non-negotiable.

---

## Privacy by Default

No data leaves the house unless explicitly needed and authorized.

**Application**:
- Wake word detection: Local on ESP32, never sent to cloud
- Voice commands: Transcribed locally first, then sent to Claude only if LLM needed
- Calendar/tasks: Stored locally in Obsidian, synced to Notion only when explicitly marked ready
- Location: Rough only, shared with Tailscale mesh only (encrypted)
- No analytics, no telemetry, no tracking

**Why**: You own your data. No third-party access without explicit consent.

---

## Deterministic Over Heuristic

If a behavior can be hard-coded, hard-code it. Heuristics and "smart" logic invite edge cases and bugs.

**Application**:
- Alarm time: Set it in config, don't try to infer optimal wake time
- Briefing order: Fixed sequence (calendar → weather → tasks → email → commute)
- Priority queue: Explicit priority levels, not ML-inferred importance
- Task parsing: Regex patterns, not NLP

**Why**: Predictable, debuggable, cheap. At 3am, you want to know exactly what's going to happen.

---

## Async + Priority

Multiple input surfaces can be active concurrently (wake word + Discord + scheduled job). Foreground requests preempt background tasks so interaction never feels slow.

**Application**:
- Phone call (incoming) → Stop background checks, handle call immediately
- Wake word (user speaking) → Interrupt briefing playback if needed
- Scheduled briefing (background) → Can be paused for real-time interaction

**Why**: Responsiveness matters for voice interaction. If Sunny feels laggy, it's unusable.

---

## Single Point of Truth

Each piece of data has one authoritative source:
- Calendar → Notion (synced from phone)
- Tasks → Discord (live) and optionally Notion (finalized)
- Logs → Discord (#activity-log) + local Obsidian mirror
- Obsidian vault → Local source of truth before Notion push

**Why**: Prevents sync conflicts, reduces complexity, makes audit trails clear.

---

## Test Often, Automate Where Possible

- Unit tests for critical paths (token counting, priority queue, Obsidian sync)
- Integration tests against real APIs (with fallback stubs)
- Manual smoke test every new feature: does it work end-to-end?
- Logging from the start so you can debug at 3am without adding debug code

**Why**: Always-on system fails at midnight, not business hours. Reliability requires confidence.

---

## Simplicity Over Flexibility

Don't build abstractions for hypothetical features. Don't add configuration options for "someday." Build exactly what's needed now.

**Application**:
- One Lenovo mini PC, not a distributed system
- One systemd unit, not Kubernetes
- One person (Keaton) talking to it, not multi-user ACLs
- Fixed briefing order, not customizable sequence

**Future**: When the system actually needs multi-device support or customization, refactor then. Not before.

**Why**: Simpler code is easier to debug at 3am. Feature creep is the enemy of reliability.

---

## Cost Awareness

Hard spending caps at provider level. Monitor token usage in real-time. Kill requests if they exceed thresholds.

**Application**:
- Anthropic API: $20/month hard cap
- Twilio: $10/month hard cap
- Sonic API: Soft limit, fall back to Piper if approaching
- Dashboard shows spend by feature, so you know what costs what

**Why**: A runaway API call at 2am should not cost $500. Caps prevent surprise bills.
