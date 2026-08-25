---
id: sunny-llm
type: component
status: active
created: 2026-08-18
tags: [llm, claude, api, reasoning]
---

# LLM Integration — Claude API

Uses Claude API for judgment and reasoning tasks only. Never for information retrieval. All deterministic operations (weather, calendar, time) bypass LLM entirely.

**Status**: The safety-rail infrastructure this doc describes (spend caps, error handling, usage logging) is built and tested — see [[llm-readiness]] for the full built-vs-not checklist. Of the four tasks below, **Freeform Conversation is now partially wired** (2026-08-21) — see the note under that task. Email Triage, Task Interpretation, and Email Reply Drafting are still not wired up — that's a deliberate, separate decision from building the rails.

`ask_claude()` is no longer only called by Freeform Conversation — as of 2026-08-23/24 it also powers the weekly health check (`purpose="weekly_health_check"`), the "new project" wizard (`purpose="project_scaffold"`), and Storm Mode's web-searched weather updates (`purpose="storm_mode"`). As of 2026-08-24/25 it also powers exam-prep's LLM-written study review (`purpose="exam_prep_review"`, see [[exam-prep]]) and class setup's syllabus parsing (`purpose="syllabus_parse"`, see [[class-setup]]). Each purpose has its own hand-editable system prompt in `sunny-vault/instructions/`, loaded automatically — see [[llm-instructions]]. Real web search is also wired in (2026-08-23): `ask_claude`/`ask_claude_stream` accept `enable_web_search=True`, which adds Anthropic's server-side `web_search_20250305` tool (capped at 3 searches/call). Claude decides for itself whether a given question needs it — used today by the Freeform Conversation fallback (`briefing.py`) and Storm Mode (`storm_mode.py`).

## Core Principle

**LLM only for judgment.**

LLM is used only when genuine semantic understanding or context is needed. Information lookups (weather, calendar, traffic, time, status) always use direct APIs.

## Supported Models

| Model | Model ID | Input/1M | Output/1M | Use Case |
|-------|----------|----------|-----------|----------|
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1.00 | $5.00 | Quick judgments, fast response |
| Claude Sonnet 5 | `claude-sonnet-5` | $3.00 | $15.00 | Balanced quality/cost |
| Claude Opus 5 | `claude-opus-5` | $5.00 | $25.00 | Complex reasoning, rare use |

**Default**: Haiku for most tasks (fast + cheap)
**Fallback to Sonnet**: If Haiku confidence too low or task complex
**Opus**: Never used (cost not justified)

These three map to `"haiku"`/`"sonnet"`/`"opus"` in `llm_client.MODELS` — pass the short name to `ask_claude(model=...)`, not the raw model ID.

## LLM Tasks

### 1. Email Triage

**When**: New email arrives
**Input**: Email subject, sender, headers
**LLM**: "Is this urgent? Action needed? From who?"
**Output**: Priority label (urgent, action, fyi)
**Cost**: ~500 tokens per email
**Frequency**: ~3-5 emails/day = 2-3 calls/day

```python
prompt = f"""
Subject: {email_subject}
From: {email_sender}
Date: {email_date}

Is this email:
1. Urgent (reply needed <1 day)?
2. Action item (requires reply)?
3. FYI only (no action)?

Respond with one word: URGENT, ACTION, or FYI.
"""

response = claude.prompt(prompt, model="haiku")  # Fast classification
```

### 2. Task Interpretation

**When**: User says "work on the engine thing"
**Input**: Vague task description + context (user's other tasks, calendar)
**LLM**: "What specifically should I create a task for?"
**Output**: Structured task (title, priority, due date estimate)
**Cost**: ~300-500 tokens per interpretation
**Frequency**: ~1-2 times/week (only for ambiguous requests)

```python
prompt = f"""
User said: "work on the engine thing"
Their other tasks:
- Engine rebuild plan (high priority)
- Research parts (medium)

Which task is the user referring to?
Or should a new task be created?

Respond with:
EXISTING: <task_id>
or
NEW: <task_title>, <priority>, <due_date_estimate>
"""

response = claude.prompt(prompt, model="haiku")
```

### 3. Freeform Conversation (Phone)

**Partially built, 2026-08-21** — a narrower "answer the question" slice of
this exists today, reachable from both text chat and voice: when
nothing else matches (no command, no known-topic keyword like weather/
calendar), `briefing.py`'s `custom_briefing()` calls `ask_claude(purpose=
"general_chat")` for a real answer instead of a canned "I don't know." The
system prompt is `sunny-vault/instructions/general-chat.md` (hand-editable,
no redeploy). Model/max_tokens/temperature are `.env`-configurable
(`LLM_CHAT_MODEL`/`LLM_CHAT_MAX_TOKENS`/`LLM_CHAT_TEMPERATURE`, see
config.py) — see [[voice-join]]'s latency chart for real, measured timing.

**Conversation memory** (2026-08-24): `sunny_code/components/conversation_memory.py`
gives this fallback short-term context — the last 6 turns (3 exchanges) per
`session_id`, so "why" or "what about that" resolves the way it would in a
real back-and-forth instead of every message being answered in isolation.
In-memory only, never written to the vault, resets on restart. Bounded two
ways: `MAX_TURNS` caps an *active* conversation's prompt size, and a
2-hour idle expiry (`IDLE_EXPIRY_SECONDS`) drops the history entirely once
it's been that long since the last turn — without it, a quiet conversation
from days ago would silently resurface as "recent conversation" context on
whatever gets said next. Scoped only to this LLM fallback — command
routing (tasks/lists/alarms/calendar/etc.) stays stateless by design and
never touches this.

**Not yet built**: the "execute action" half below — today's version only
*answers*, it never creates/updates a task or calendar event on its own
initiative. The original phone-call framing (Twilio) is also still fully
unbuilt; what exists today is the same underlying mechanism reached via
Discord voice/text instead.

**When**: Phone call incoming, user talks freely
**Input**: User speech transcript, call context
**LLM**: Understand intent and execute action
**Output**: Action (calendar update, task create, answer) + spoken response
**Cost**: ~1000-2000 tokens per minute of conversation
**Frequency**: On-demand, rare

```python
prompt = f"""
During a phone call, user said: "{user_transcript}"

Available actions:
- Create/update calendar event
- Create/reschedule task
- Answer question from facts
- Execute command

What should happen?
"""

response = claude.prompt(prompt, model="sonnet")  # Better for conversation
```

### 4. Email Reply Drafting (Planned)

**When**: Certain emails warrant a draft reply
**Input**: Email subject, content, user's context
**LLM**: "Draft a response"
**Output**: Text (not sent, requires review)
**Cost**: ~500-1000 tokens per draft
**Frequency**: Optional, few times/week

## Cost Tracking

Built: `sunny_code/components/token_tracker.py`. Reuses the `token_usage` table in `sunny.db` (`dashboard.py`'s schema). `record_usage()` upserts today's row with a per-model breakdown; `get_today_usage()` / `get_month_cost()` read it back; `check_budget()` is the actual circuit breaker — `llm_client.ask_claude()` calls it before every request and refuses (returns `None`) once either cap is hit. Cost is self-calculated from a local `$/1M token` table (not authoritative Anthropic billing — update `token_tracker._PRICING` if rates change); an unrecognized model ID prices at the most expensive known tier rather than the cheapest, so an unmapped model can't quietly slip under the cap.

Live numbers: `GET /api/dashboard/spend/today`, `GET /api/dashboard/spend/month`.

**Daily limit**: `daily_spend_cap` in `.env` (default $20) — enforced in-app by `check_budget()`.
**Monthly budget**: `monthly_spend_cap` in `.env` (default $100) — same enforcement.
**Not yet done**: a second, independent hard cap set at the Anthropic account level (console.anthropic.com) — the app's own cap is self-tracked and could in principle be wrong if `_PRICING` drifts from real billing; the account-level cap is the actual backstop and is a manual step only the account owner can do. See [[llm-readiness]].

## Implementation

Built: `sunny_code/components/llm_client.py`. The one function any future feature calls through — `ask_claude(prompt, model="haiku", max_tokens=1024, system=None, purpose="...", enable_web_search=False)`, plus a streaming sibling `ask_claude_stream(...)` (sentence-boundary chunked, used by Sunny's live voice replies — see [[voice-join]]). Real callers today: Freeform Conversation, the weekly health check, the project wizard, Storm Mode, exam-prep's study review, and class setup's syllabus parsing (see Status above).

```python
async def ask_claude(prompt: str, model: str = "haiku", ...) -> Optional[str]:
    if not looks_configured(settings.claude_api_key):
        return None                       # honest "not connected", same pattern as every other integration
    if _auth_disabled:
        return None                       # latched after an invalid-key error, until restart
    ok, reason = token_tracker.check_budget()
    if not ok:
        return None                       # circuit breaker
    async with _concurrency_guard:        # asyncio.Semaphore(1) — see priority-queue note below
        response = await asyncio.to_thread(_call_claude_sync, ...)  # sync SDK call off the event loop
    token_tracker.record_usage(...)
    log_llm_call(...)                     # vault usage log, see below
    return text
```

Never raises — every failure path returns `None` so a caller can always fall back to existing non-LLM behavior.

### Error Handling (implemented)

**API rate limit** (`anthropic.RateLimitError`):
- Fails the call immediately, logs a warning. **Deviates from the original plan of "retry after 60s inline"** — blocking a live chat/Discord response for 60 seconds is bad UX for an interactive assistant; the next user message naturally retries instead.

**API timeout / connection error** (`anthropic.APIConnectionError`):
- Logged, returns `None`. The SDK itself already retries transient connection failures (`max_retries`, default 2) before this is reached.

**API key invalid** (`anthropic.AuthenticationError`):
- Sets a module-level `_auth_disabled` latch — every subsequent call short-circuits to `None` without even attempting the SDK call, for the rest of the process. Matches the original policy exactly ("stop all calls, require manual restart").

**Token budget exceeded**:
- `token_tracker.check_budget()` returns `False`; `ask_claude()` refuses before making the call at all. Resumes automatically once the day/month rolls over (no explicit "resume" step needed — the cap check is always computed against "today"/"this month").

**Not yet done**: routing any of the above to a Discord `#warnings` post — today they only go to the app log. Worth adding once a real feature is calling this regularly enough for silent-log failures to matter.

## Fallbacks

**No LLM**:
```python
# Email without LLM: Use header flags and patterns
if email.has_flag("urgent"):
    priority = "URGENT"
elif email.is_from_professor:
    priority = "ACTION"
else:
    priority = "FYI"

# Task without LLM: Ask user to be specific
"I didn't understand. Please describe the task with more detail."

# Phone without LLM: Hardcoded commands only
if "what time" in transcript:
    speak(f"It is {get_time()}")
else:
    speak("I can't understand that. Please try again.")
```

## Prompt Engineering

System prompts live in the vault, not in Python — `sunny-vault/instructions/{purpose}.md`, one file per task, loaded by `ask_claude()` automatically when a caller passes `purpose=` and no explicit `system=`. See [[llm-instructions]]. This replaced the original plan of fully-hardcoded, Python-embedded prompts — the user wanted to edit prompts directly without a redeploy, which vault-loaded prompts give for free.

**Examples**:
- Email triage: 3-sentence prompt, ask for one-word response
- Task interpret: 5-sentence prompt, structured output format
- Phone conversation: 10-sentence system prompt, conversation context

**Prompt injection**: loading prompt *text* from hand-editable vault files is a different threat model than the original fixed-Python-template design, which is why this doc used to say there was no injection risk at all — that claim no longer holds in the strict sense. Accepted as a deliberate risk (2026-08-20): Sunny is single-user, the vault isn't shared or synced anywhere untrusted reaches it, and the user made this call explicitly rather than it being an oversight. Revisit if that threat model ever changes (e.g. multi-user, a synced/shared vault, or instruction files ever being written by anything other than the user).

## Privacy & Data

- API calls include only necessary context (email subject, task title)
- Never send full email body unless explicitly needed
- User data sent to Anthropic (API requirement)
- Consider using on-premise LLM in future (Phase 7)

## Future: Local LLM

Long-term option (once GPUs affordable):
```python
# Replace
response = ask_claude(prompt)

# With
response = ask_local_llm(prompt)  # Llama 3, Mistral, etc. on TrueNAS
```

**Advantages**:
- No API cost
- Full privacy (never leaves home)
- Lower latency (local inference)

**Disadvantage**: Requires GPUs + setup complexity

## Dependencies

- [[brain]] — Python + anthropic SDK
- [[networking]] — Internet access for Anthropic API
- `token_tracker.py` — Usage tracking + spend circuit breaker (built; was `[[token-circuit-breaker]]` in the original plan)
- Priority queue — LLM calls queued, not all simultaneous. Not built as a real scheduler; `llm_client.py`'s `asyncio.Semaphore(1)` is a lightweight stand-in that's enough for a single-user assistant with no concurrent LLM-triggering surfaces yet. Revisit if [[phone]]/[[clock]] hardware ever creates a genuine "interrupt one in-flight call with another" scenario.
- [[voice-io]] — Text input (transcripts), text output (responses)
- [[discord-bot]] — Alert channel for errors (not yet wired — see Error Handling above)

## Implementation Checklist

- [x] Anthropic API account setup + API key in `.env` — done, 2026-08-21
- [x] anthropic SDK installed (`requirements.txt`)
- [x] Token tracking integration (`token_tracker.py`, tested)
- [x] Error handling + retries (`llm_client.py`: rate limit, timeout/connection, invalid key, budget — all tested against mocked failures)
- [x] Freeform conversation (Q&A slice) system prompt — `sunny-vault/instructions/general-chat.md`, live, wired into `briefing.py`'s `custom_briefing()`
- [x] Real web search for freeform conversation + Storm Mode — `enable_web_search=True`, Anthropic's `web_search_20250305` tool, Claude decides when a question needs it
- [x] Weekly health check, project-scaffold wizard, Storm Mode, exam-prep review, and syllabus-parse system prompts — `sunny-vault/instructions/{weekly-health-check,project-scaffold,storm-mode,exam-prep-review,syllabus-parse}.md`, all live
- [x] Streaming replies (`ask_claude_stream`) — sentence-boundary chunked into TTS for `/join`, live since 2026-08-21
- [ ] Email triage system prompt — not written, feature not built
- [ ] Task interpretation system prompt — not written, feature not built
- [ ] Phone conversation (action-taking + Twilio) — not built; the answer-only Q&A slice above is live
- [x] Hard spending cap enforced in-app (`token_tracker.check_budget()`, tested)
- [ ] Hard spending cap at Anthropic account level — external, user action, separate from the in-app cap above
- [ ] Test with sample emails — needs the email-triage feature built (API key itself is no longer the blocker)
- [x] Monitor costs — `GET /api/dashboard/spend/today` and `/spend/month`, live and tested

Full built-vs-not-vs-external breakdown, and what's still gated on this: [[llm-readiness]].
