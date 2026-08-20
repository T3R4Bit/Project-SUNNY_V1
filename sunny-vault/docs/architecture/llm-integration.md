---
id: sunny-llm
type: component
status: active
created: 2026-08-18
tags: [llm, claude, api, reasoning]
---

# LLM Integration — Claude API

Uses Claude API for judgment and reasoning tasks only. Never for information retrieval. All deterministic operations (weather, calendar, time) bypass LLM entirely.

**Status**: The safety-rail infrastructure this doc describes (spend caps, error handling, usage logging) is built and tested — see [[llm-readiness]] for the full built-vs-not checklist. **None of the four tasks below are wired up yet** — that's a deliberate, separate decision from building the rails.

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

Built: `sunny_code/components/llm_client.py`. The one function any future feature calls through — `ask_claude(prompt, model="haiku", max_tokens=1024, system=None, purpose="...")`. Nothing calls it yet.

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

All prompts hardcoded (never dynamic).

**Examples**:
- Email triage: 3-sentence prompt, ask for one-word response
- Task interpret: 5-sentence prompt, structured output format
- Phone conversation: 10-sentence system prompt, conversation context

**No system prompt injection risks**: All input is treated as data, prompts are fixed templates.

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

- [ ] Anthropic API account setup — external, user action
- [ ] API key in environment variables — external, user action (`CLAUDE_API_KEY` in `.env`)
- [x] anthropic SDK installed (`requirements.txt`)
- [x] Token tracking integration (`token_tracker.py`, tested)
- [x] Error handling + retries (`llm_client.py`: rate limit, timeout/connection, invalid key, budget — all tested against mocked failures)
- [ ] Email triage system prompt — not written, feature not built
- [ ] Task interpretation system prompt — not written, feature not built
- [ ] Phone conversation system prompt — not written, feature not built
- [x] Hard spending cap enforced in-app (`token_tracker.check_budget()`, tested)
- [ ] Hard spending cap at Anthropic account level — external, user action, separate from the in-app cap above
- [ ] Test with sample emails — needs a real API key and the email-triage feature built
- [x] Monitor costs — `GET /api/dashboard/spend/today` and `/spend/month`, live and tested

Full built-vs-not-vs-external breakdown, and what's still gated on this: [[llm-readiness]].
