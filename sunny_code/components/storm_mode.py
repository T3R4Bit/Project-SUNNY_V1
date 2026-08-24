"""Storm mode: on request, temporarily replaces the normal weather-API
lookup with periodic LLM-driven updates (real web search, not the
model's stale training knowledge) — for exactly the kind of fast-moving
severe-weather situation where checking on an interval matters more than
one free OpenWeatherMap snapshot. See BACKLOG.md.

Discord-only by design: this is a proactive, repeats-over-time posting
loop, not a request/response answer, so it's triggered directly in
discord_bot.py (same reasoning server-admin commands are handled there
instead of through the interface-agnostic assistant.handle_message()) --
there's no "periodic channel" concept on the web console, /join, or the
Pi companion to post updates into.

Module-level state, not a class -- one active storm mode at a time,
same "one active thing" pattern as voice_session.py's _worker global;
this is a personal, single-user, single-session app.
"""

import asyncio
import logging
import re
import time
from typing import Awaitable, Callable, Optional

from sunny_code.components.llm_client import ask_claude
from sunny_code.components.location_store import get_location
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

PostFn = Callable[[str], Awaitable[None]]

_DURATION_RE = re.compile(r"(\d+)\s*(minute|min|hour|hr)s?", re.IGNORECASE)

_task: Optional[asyncio.Task] = None
_ends_at: Optional[float] = None
_interval_minutes: Optional[int] = None


def parse_minutes(text: str) -> Optional[int]:
    """Extracts a duration in minutes from a short natural reply like
    "10 minutes", "every 15 min", "1 hour", "2 hrs". None if nothing
    duration-shaped is found -- not full NLP, just a number + unit,
    same "good enough for a short direct reply" standard as this file's
    sibling parsers (e.g. llm_client._next_sentence)."""
    match = _DURATION_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    return value * 60 if unit in ("hour", "hr") else value


def is_active() -> bool:
    return _task is not None and not _task.done()


def status() -> Optional[str]:
    """Human-readable status of the currently-active storm mode, or None
    if it's not running."""
    if not is_active():
        return None
    remaining = max(0, int((_ends_at - time.monotonic()) / 60))
    return f"Storm mode active — updates every {_interval_minutes} min, ~{remaining} min left."


async def start(interval_minutes: int, duration_minutes: int, post_fn: PostFn) -> None:
    """Starts the background update loop. Replaces any already-running
    one outright (a fresh start always wins over a stale one, same as a
    new /join elsewhere in this app) rather than requiring the caller to
    stop() first."""
    global _task, _ends_at, _interval_minutes
    if _task is not None and not _task.done():
        _task.cancel()

    _interval_minutes = interval_minutes
    _ends_at = time.monotonic() + duration_minutes * 60
    _task = asyncio.create_task(_run(interval_minutes, post_fn))


async def stop(post_fn: Optional[PostFn] = None) -> bool:
    """Manually ends storm mode early. Returns False (no-op) if nothing
    was running. Posts its own "ended" message (if post_fn is given)
    instead of letting _run's natural-completion message fire, since
    cancellation interrupts _run before it ever reaches that line."""
    global _task, _ends_at, _interval_minutes
    if _task is None or _task.done():
        return False
    _task.cancel()
    _task = None
    _ends_at = None
    _interval_minutes = None
    if post_fn is not None:
        await post_fn("Storm mode ended.")
    return True


async def _run(interval_minutes: int, post_fn: PostFn) -> None:
    global _task, _ends_at, _interval_minutes
    location = get_location() or "the user's area (no location configured -- ask generically)"
    settings = get_settings()

    while True:
        prompt = (
            f"Give a short, current weather/storm update for {location}. Search the "
            "web for real, up-to-date conditions and any active severe weather "
            "alerts or warnings right now -- don't answer from memory or guess. "
            "A few sentences, plain language, lead with anything urgent first."
        )
        answer = await ask_claude(
            prompt,
            model=settings.llm_chat_model,
            max_tokens=400,
            purpose="storm_mode",
            enable_web_search=True,
        )
        await post_fn(answer or "Couldn't get a storm mode update this round — will try again next interval.")

        if time.monotonic() >= _ends_at:
            break
        await asyncio.sleep(interval_minutes * 60)

    await post_fn("Storm mode ended — back to normal weather.")
    _task = None
    _ends_at = None
    _interval_minutes = None
