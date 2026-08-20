"""The one place any future LLM-powered feature in Project SUNNY (email
triage, task interpretation, freeform phone conversation, storm mode, etc. —
see sunny-vault/docs/architecture/llm-integration.md) must call through.

Built ahead of those features, per sunny-vault/docs/architecture/
llm-readiness.md, so the safety rails already exist and are already tested
by the time a real feature needs them: honest "not configured" handling
(matches the rest of the app's pattern for every other integration), a hard
spend-cap circuit breaker (token_tracker.py), an auth-failure latch, and
vault usage logging. Nothing in the app calls ask_claude() yet — wiring a
real feature to it is a deliberate, separate decision.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic

from sunny_code.components import token_tracker
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
) -> Optional[str]:
    """Ask Claude a question. Never raises — returns None on any failure
    (not configured, over budget, rate limited, API/network error) so a
    caller can always fall back to existing non-LLM behavior instead of
    crashing a request."""
    global _auth_disabled

    settings = get_settings()

    if not looks_configured(settings.claude_api_key):
        logger.info("ask_claude: no Claude API key configured, skipping")
        return None

    if _auth_disabled:
        logger.warning("ask_claude: disabled after an invalid API key error earlier this run — restart required")
        return None

    ok, reason = token_tracker.check_budget()
    if not ok:
        logger.warning(f"ask_claude: refusing call, {reason}")
        return None

    model_id = MODELS.get(model, MODELS["haiku"])

    async with _concurrency_guard:
        try:
            response = await asyncio.to_thread(
                _call_claude_sync, settings.claude_api_key, model_id, max_tokens, system, prompt
            )
        except anthropic.AuthenticationError:
            _auth_disabled = True
            logger.error("ask_claude: invalid Claude API key — disabling further calls until restart")
            return None
        except anthropic.RateLimitError:
            logger.warning("ask_claude: rate limited — failing this call, a later message can retry")
            return None
        except anthropic.APIStatusError as e:
            logger.error(f"ask_claude: Claude API error ({e.status_code}): {e.message}")
            return None
        except anthropic.APIConnectionError as e:
            logger.error(f"ask_claude: connection error: {e}")
            return None

    text = "".join(block.text for block in response.content if block.type == "text")

    token_tracker.record_usage(
        model=model_id,
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
        cost=token_tracker.calculate_cost(model_id, response.usage.input_tokens, response.usage.output_tokens),
    )
    log_llm_call(purpose=purpose, model=model_id, prompt=prompt, response=text)

    return text


def _call_claude_sync(api_key: str, model_id: str, max_tokens: int, system: Optional[str], prompt: str):
    """Runs in a thread via asyncio.to_thread — the anthropic SDK's client is
    sync/blocking, and this is a network call, so it must not run directly
    on the event loop (unlike vault_io's local file writes, which are fast
    enough to stay inline — see vault_io.py's concurrency note)."""
    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {"model": model_id, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    return client.messages.create(**kwargs)


def log_llm_call(purpose: str, model: str, prompt: str, response: str) -> None:
    """Append a timestamped record to the vault — per BACKLOG.md: "All chats
    that were forced to an llm (except weather mode or project builds) get a
    copy of the message logged with a time stamp into the obsidian vault."""
    settings = get_settings()
    log_path = settings.project_root / "sunny-vault" / "log" / "llm-usage.md"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = (
            f"## {timestamp} — {purpose} ({model})\n\n"
            f"**Prompt:** {prompt}\n\n"
            f"**Response:** {response}\n\n---\n\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        logger.error(f"Failed to write to LLM usage log: {e}")
