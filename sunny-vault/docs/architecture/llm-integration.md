---
id: sunny-llm
type: component
status: active
created: 2026-08-18
tags: [llm, claude, api, reasoning]
---

# LLM Integration — Claude API

Uses Claude API for judgment and reasoning tasks only. Never for information retrieval. All deterministic operations (weather, calendar, time) bypass LLM entirely.

## Core Principle

**LLM only for judgment.**

LLM is used only when genuine semantic understanding or context is needed. Information lookups (weather, calendar, traffic, time, status) always use direct APIs.

## Supported Models

| Model | Latency | Quality | Cost | Use Case |
|-------|---------|---------|------|----------|
| Claude Haiku | 0.5-1s | Good | $0.08/MTok | Quick judgments, fast response |
| Claude Sonnet | 1-3s | Excellent | $0.30/MTok | Balanced quality/cost |
| Claude Opus | 2-5s | Best | $0.80/MTok | Complex reasoning, rare use |

**Default**: Haiku for most tasks (fast + cheap)
**Fallback to Sonnet**: If Haiku confidence too low or task complex
**Opus**: Never used (cost not justified)

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

[[token-circuit-breaker]] tracks all LLM usage:

```python
usage = {
    "tokens": {
        "prompt": 2500,
        "completion": 800,
        "total": 3300,
    },
    "cost": "$0.27",  # Haiku pricing
    "model": "claude-haiku",
}
```

**Daily limit**: $20 hard cap (set at Anthropic account level)
**Monthly budget**: ~$100 (generous for expected usage)

## Implementation

### API Setup

```python
import anthropic

client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

def ask_claude(prompt: str, model: str = "claude-haiku-4.5") -> str:
    try:
        message = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Track usage
        token_circuit_breaker.log_usage(
            model=model,
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
        )
        
        return message.content[0].text
    
    except anthropic.APIError as e:
        log_to_discord("#warnings", f"Claude API error: {e}")
        return None  # Fallback behavior
```

### Error Handling

**API rate limit**:
- Retry after 60 seconds
- Alert in Discord #warnings

**API timeout**:
- Retry up to 2 times
- After 2 retries: Skip LLM step, use fallback

**API key invalid**:
- Stop all LLM calls, log to #warnings
- Require manual restart

**Token budget exceeded**:
- Pause LLM calls for day
- Alert user in Discord
- Resume tomorrow

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
- [[token-circuit-breaker]] — Usage tracking
- [[priority-queue]] — LLM calls queued, not all simultaneously
- [[voice-io]] — Text input (transcripts), text output (responses)
- [[discord-bot]] — Alert channel for errors

## Implementation Checklist

- [ ] Anthropic API account setup
- [ ] API key in environment variables
- [ ] anthropic SDK installed
- [ ] Token tracking integration
- [ ] Error handling + retries
- [ ] Email triage system prompt
- [ ] Task interpretation system prompt
- [ ] Phone conversation system prompt
- [ ] Hard spending cap at Anthropic level
- [ ] Test with sample emails
- [ ] Monitor costs
