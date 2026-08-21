"""The one place any future LLM-powered feature in Project SUNNY (email
triage, task interpretation, freeform phone conversation, storm mode, etc. —
see sunny-vault/docs/architecture/llm-integration.md) must call through.

Built ahead of those features, per sunny-vault/docs/architecture/
llm-readiness.md, so the safety rails already exist and are already tested
by the time a real feature needs them: honest "not configured" handling
(matches the rest of the app's pattern for every other integration), a hard
spend-cap circuit breaker (token_tracker.py), an auth-failure latch, and a
complete vault usage log (every call attempt, not just successes — see
log_llm_call below). Nothing in the app calls ask_claude() yet — wiring a
real feature to it is a deliberate, separate decision.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic

from sunny_code.components import instructions, token_tracker
from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

MODELS = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
}

# SUNNY is a single-user personal assistant — one in-flight LLM call at a
# time is enough and keeps spend/behavior easy to reason about. Stands in
# for the "Priority Scheduler" backlog item until there's an actual
# concurrent-caller scenario (e.g. a phone call interrupting a briefing)
# that would justify a real queue.
_concurrency_guard = asyncio.Semaphore(1)

# Set once an invalid API key is detected; latched for the rest of the
# process per the documented policy ("invalid key -> stop all calls +
# require manual restart") — deliberately not auto-cleared, since a bad key
# won't fix itself without the user editing .env and restarting anyway.
_auth_disabled = False


async def ask_claude(
    prompt: str,
    model: str = "haiku",
    max_tokens: int = 1024,
    system: Optional[str] = None,
    purpose: str = "unspecified",
    temperature: Optional[float] = None,
) -> Optional[str]:
    """Ask Claude a question. Never raises — returns None on any failure
    (not configured, over budget, rate limited, API/network error) so a
    caller can always fall back to existing non-LLM behavior instead of
    crashing a request.

    If `system` isn't given, it's auto-loaded from
    sunny-vault/instructions/{purpose}.md — see instructions.py. A caller
    that passes `system` explicitly always wins.

    temperature controls response randomness/variety (0.0 = deterministic,
    1.0 = Anthropic's own default, higher = more varied). None (the
    default) omits it entirely from the request so the API's own default
    applies — deliberately not defaulted to a specific number here, so
    "not configured" and "explicitly set to the API default" stay
    distinguishable in the vault log below.

    Every exit point logs to the vault (see log_llm_call) — not just
    successful calls. That's deliberate: the point is to see everything
    that *would* reach the LLM, including calls refused before ever making
    a request, so patterns worth hardcoding are visible over time."""
    global _auth_disabled

    settings = get_settings()
    model_id = MODELS.get(model, MODELS["haiku"])
    if system is None:
        system = instructions.load_instructions(purpose)

    if not looks_configured(settings.claude_api_key):
        logger.info("ask_claude: no Claude API key configured, skipping")
        log_llm_call(purpose, model_id, prompt, status="not_configured")
        return None

    if _auth_disabled:
        logger.warning("ask_claude: disabled after an invalid API key error earlier this run — restart required")
        log_llm_call(purpose, model_id, prompt, status="auth_disabled")
        return None

    ok, reason = token_tracker.check_budget()
    if not ok:
        logger.warning(f"ask_claude: refusing call, {reason}")
        log_llm_call(purpose, model_id, prompt, status="budget_exceeded", detail=reason)
        return None

    async with _concurrency_guard:
        try:
            response = await asyncio.to_thread(
                _call_claude_sync, settings.claude_api_key, model_id, max_tokens, system, prompt, temperature
            )
        except anthropic.AuthenticationError:
            _auth_disabled = True
            logger.error("ask_claude: invalid Claude API key — disabling further calls until restart")
            log_llm_call(purpose, model_id, prompt, status="auth_error")
            return None
        except anthropic.RateLimitError:
            logger.warning("ask_claude: rate limited — failing this call, a later message can retry")
            log_llm_call(purpose, model_id, prompt, status="rate_limited")
            return None
        except anthropic.APIStatusError as e:
            logger.error(f"ask_claude: Claude API error ({e.status_code}): {e.message}")
            log_llm_call(purpose, model_id, prompt, status="api_error", detail=f"HTTP {e.status_code}: {e.message}")
            return None
        except anthropic.APIConnectionError as e:
            # type(e).__name__ only, never str(e) — a connection error's
            # message can embed the full request URL, which includes the
            # API key (same caution as weather.py's equivalent handler).
            logger.error(f"ask_claude: connection error: {e}")
            log_llm_call(purpose, model_id, prompt, status="connection_error", detail=type(e).__name__)
            return None

    text = "".join(block.text for block in response.content if block.type == "text")

    token_tracker.record_usage(
        model=model_id,
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
        cost=token_tracker.calculate_cost(model_id, response.usage.input_tokens, response.usage.output_tokens),
    )
    log_llm_call(purpose, model_id, prompt, status="success", response=text)

    return text


def _call_claude_sync(
    api_key: str, model_id: str, max_tokens: int, system: Optional[str], prompt: str, temperature: Optional[float] = None
):
    """Runs in a thread via asyncio.to_thread — the anthropic SDK's client is
    sync/blocking, and this is a network call, so it must not run directly
    on the event loop (unlike vault_io's local file writes, which are fast
    enough to stay inline — see vault_io.py's concurrency note)."""
    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {"model": model_id, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    return client.messages.create(**kwargs)


def log_llm_call(
    purpose: str,
    model: str,
    prompt: str,
    status: str = "success",
    detail: Optional[str] = None,
    response: Optional[str] = None,
) -> None:
    """Append a timestamped record to the vault for *every* call attempt,
    not just successful ones — per BACKLOG.md: "All chats that were forced
    to an llm... get a copy of the message logged with a time stamp into
    the obsidian vault." Logging refusals too (not_configured,
    budget_exceeded, etc.) with the full prompt is the point: that's what
    would have gone to the LLM, which is exactly what's useful for spotting
    patterns worth hardcoding later."""
    settings = get_settings()
    log_path = settings.project_root / "sunny-vault" / "log" / "llm-usage.md"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = f"## {timestamp} — {purpose} ({model}) — {status}\n\n**Prompt:** {prompt}\n\n"
        if detail is not None:
            entry += f"**Detail:** {detail}\n\n"
        if status == "success":
            entry += f"**Response:** {response}\n\n"
        entry += "---\n\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        logger.error(f"Failed to write to LLM usage log: {e}")
