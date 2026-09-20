"""The one place any future LLM-powered feature in Project SUNNY (email
triage, task interpretation, freeform phone conversation, storm mode, etc. —
see sunny-vault/docs/architecture/llm-integration.md) must call through.

Built ahead of those features, per sunny-vault/docs/architecture/
llm-readiness.md, so the safety rails already exist and are already tested
by the time a real feature needs them: honest "not configured" handling
(matches the rest of the app's pattern for every other integration), a hard
spend-cap circuit breaker (token_tracker.py), an auth-failure latch, and a
complete vault usage log (every call attempt, not just successes — see
log_llm_call below). briefing.py's custom_briefing() Q&A fallback (wired
2026-08-21) is the first real feature calling ask_claude(); ask_claude_stream()
is the streaming variant built for /join specifically, so speech can start
on the first sentence instead of waiting for the whole reply.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Tuple

import anthropic

from sunny_code.components import instructions, personality, token_tracker
from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

MODELS = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
}

# Basic web search (not the newer dynamic-filtering variant, which needs
# Opus/Sonnet 4.6+) -- works on every model this app uses, including the
# Haiku default, and needs no code-execution provisioning of its own.
_WEB_SEARCH_TOOL = "web_search_20250305"
# "Simple factual queries typically use 1-3 searches" per Anthropic's own
# guidance -- capped, not unlimited, since every extra search is both real
# latency (this app plays an audio/state cue for exactly that reason -- see
# voice_worker.py's "searching" cue) and real per-1000-searches cost.
_WEB_SEARCH_MAX_USES = 3

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

# Cached client, keyed by the API key it was built with — reused across
# calls so consecutive requests get a warm HTTP connection instead of
# paying a fresh TCP+TLS handshake every time (constructing a new
# anthropic.Anthropic() per call, as this used to do, throws that away).
# Keyed rather than a single cached instance so a live .env key rotation
# (no restart needed, matching get_settings()'s own uncached-by-design
# pattern) still picks up the new key on the very next call instead of
# silently continuing to use a stale one.
_client_cache: tuple[Optional[str], Optional["anthropic.Anthropic"]] = (None, None)


def _get_client(api_key: str) -> "anthropic.Anthropic":
    global _client_cache
    cached_key, cached_client = _client_cache
    if cached_key == api_key and cached_client is not None:
        return cached_client
    client = anthropic.Anthropic(api_key=api_key)
    _client_cache = (api_key, client)
    return client


# Same reuse-with-key-invalidation approach as _get_client, for the async
# client ask_claude_stream() needs -- streaming uses AsyncAnthropic
# directly (native `async for` over stream.text_stream) rather than
# running the sync client through asyncio.to_thread, since bridging a
# blocking generator across that boundary would need its own thread+
# queue plumbing for no benefit when an async-native client already does
# the same job.
_async_client_cache: tuple[Optional[str], Optional["anthropic.AsyncAnthropic"]] = (None, None)


def _get_async_client(api_key: str) -> "anthropic.AsyncAnthropic":
    global _async_client_cache
    cached_key, cached_client = _async_client_cache
    if cached_key == api_key and cached_client is not None:
        return cached_client
    client = anthropic.AsyncAnthropic(api_key=api_key)
    _async_client_cache = (api_key, client)
    return client


async def _preflight_refusal(purpose: str, model_id: str, prompt: str) -> Optional[str]:
    """Checks shared by ask_claude() and ask_claude_stream() so the two
    never drift out of sync on when a call gets refused before it's even
    attempted. Returns the refusal status string (also what gets logged)
    if the call should be refused, else None."""
    settings = get_settings()
    if not looks_configured(settings.claude_api_key):
        logger.info("ask_claude: no Claude API key configured, skipping")
        await log_llm_call_async(purpose, model_id, prompt, status="not_configured")
        return "not_configured"

    if _auth_disabled:
        logger.warning("ask_claude: disabled after an invalid API key error earlier this run — restart required")
        await log_llm_call_async(purpose, model_id, prompt, status="auth_disabled")
        return "auth_disabled"

    ok, reason = token_tracker.check_budget()
    if not ok:
        logger.warning(f"ask_claude: refusing call, {reason}")
        await log_llm_call_async(purpose, model_id, prompt, status="budget_exceeded", detail=reason)
        return "budget_exceeded"

    return None



def _with_personality(system: str | None) -> str | None:
    """Prepend the user's tunable personality (sunny-vault/personality.md)
    to whatever per-purpose system prompt was loaded.

    Applied here rather than in each caller so it reaches every interface
    and every purpose at once -- chat, voice, briefs, study reviews --
    which is the whole point of a single personality file. Per-purpose
    instructions still follow it, so a specific prompt can override the
    general register where it needs to (the health report should stay
    structured even at humor: 5).

    Never raises: personality.as_prompt_section() already falls back to
    its last good rendering, and a personality file must not be able to
    break an LLM call.
    """
    try:
        section = personality.as_prompt_section()
    except Exception:
        return system
    if not section:
        return system
    if not system:
        return section
    return section + "\n" + system


async def ask_claude(
    prompt: str,
    model: str = "haiku",
    max_tokens: int = 1024,
    system: Optional[str] = None,
    purpose: str = "unspecified",
    temperature: Optional[float] = None,
    enable_web_search: bool = False,
) -> Optional[str]:
    """Ask Claude a question. Never raises — returns None on any failure
    (not configured, over budget, rate limited, API/network error) so a
    caller can always fall back to existing non-LLM behavior instead of
    crashing a request.

    If `system` isn't given, it's auto-loaded from
    sunny-vault/docs/instructions/{purpose}.md — see instructions.py. A caller
    that passes `system` explicitly always wins.

    temperature controls response randomness/variety (0.0 = deterministic,
    1.0 = Anthropic's own default, higher = more varied). None (the
    default) omits it entirely from the request so the API's own default
    applies — deliberately not defaulted to a specific number here, so
    "not configured" and "explicitly set to the API default" stay
    distinguishable in the vault log below.

    enable_web_search: off by default (existing behavior/other purposes
    unchanged) — Claude still decides for itself whether a given prompt
    actually needs a search (see general-chat.md's steering note); this
    just makes the tool available. No live "searching" cue on this
    non-streaming path — see ask_claude_stream()'s on_search_start for
    that (this function has no interface that streams intermediate
    progress today).

    Every exit point logs to the vault (see log_llm_call) — not just
    successful calls. That's deliberate: the point is to see everything
    that *would* reach the LLM, including calls refused before ever making
    a request, so patterns worth hardcoding are visible over time."""
    global _auth_disabled

    settings = get_settings()
    model_id = MODELS.get(model, MODELS["haiku"])
    if system is None:
        system = instructions.load_instructions(purpose)
    system = _with_personality(system)

    if await _preflight_refusal(purpose, model_id, prompt) is not None:
        return None

    async with _concurrency_guard:
        try:
            response = await asyncio.to_thread(
                _call_claude_sync, settings.claude_api_key, model_id, max_tokens, system, prompt, temperature,
                enable_web_search,
            )
        except anthropic.AuthenticationError:
            _auth_disabled = True
            logger.error("ask_claude: invalid Claude API key — disabling further calls until restart")
            await log_llm_call_async(purpose, model_id, prompt, status="auth_error")
            return None
        except anthropic.RateLimitError:
            logger.warning("ask_claude: rate limited — failing this call, a later message can retry")
            await log_llm_call_async(purpose, model_id, prompt, status="rate_limited")
            return None
        except anthropic.APIStatusError as e:
            logger.error(f"ask_claude: Claude API error ({e.status_code}): {e.message}")
            await log_llm_call_async(purpose, model_id, prompt, status="api_error", detail=f"HTTP {e.status_code}: {e.message}")
            return None
        except anthropic.APIConnectionError as e:
            # type(e).__name__ only, never str(e)/exc_info — a connection error's
            # message can embed the full request URL, which includes the
            # API key (same caution as weather.py's equivalent handler).
            logger.error(f"ask_claude: connection error: {type(e).__name__}")
            await log_llm_call_async(purpose, model_id, prompt, status="connection_error", detail=type(e).__name__)
            return None

    text = "".join(block.text for block in response.content if block.type == "text")

    token_tracker.record_usage(
        model=model_id,
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
        cost=token_tracker.calculate_cost(model_id, response.usage.input_tokens, response.usage.output_tokens),
    )
    await log_llm_call_async(purpose, model_id, prompt, status="success", response=text)

    return text


_SENTENCE_BREAK_RE = re.compile(r"[.!?]+(?=\s|$)")


def _next_sentence(buffer: str) -> Optional[Tuple[str, str]]:
    """(sentence, remainder) for the first complete sentence in buffer,
    or None if nothing's complete yet (still mid-sentence). A "complete
    sentence" is just "ends in ./!/? followed by whitespace or end of
    string" -- not real NLP segmentation, so it'll occasionally split on
    an abbreviation ("Mr. Smith") too early. Accepted: the only consumer
    is streamed TTS playback, where a false split just costs one tiny
    extra pause mid-sentence, not a functional bug worth a real sentence
    tokenizer for."""
    match = _SENTENCE_BREAK_RE.search(buffer)
    if match is None:
        return None
    return buffer[: match.end()].strip(), buffer[match.end() :]


async def ask_claude_stream(
    prompt: str,
    model: str = "haiku",
    max_tokens: int = 1024,
    system: Optional[str] = None,
    purpose: str = "unspecified",
    temperature: Optional[float] = None,
    enable_web_search: bool = False,
    on_search_start: Optional[Callable[[], Awaitable[None]]] = None,
):
    """Same safety contract as ask_claude() (never raises; an honest
    refusal reason logged to the vault either way) but yields the
    response sentence-by-sentence as it's generated, instead of waiting
    for the whole thing -- built specifically so /join can start
    speaking the first sentence while Claude is still writing the rest,
    the single biggest real latency win available in the voice pipeline
    (see the 2026-08-21 latency chart: the LLM call itself is the
    largest chunk of total response time). Yields nothing at all on any
    refusal or failure -- callers should treat "nothing was yielded" the
    same way they'd treat ask_claude() returning None, and fall back
    accordingly (this file has no opinion on what that fallback is).

    enable_web_search: off by default. When on, Claude still decides for
    itself whether a given prompt actually needs a search (see
    general-chat.md's steering note) -- this just makes the tool
    available. on_search_start, if given, fires the instant a search
    begins (a "server_tool_use"/web_search content block starting) --
    lets a caller play a distinct "searching" cue for what's otherwise a
    real, silent gap on top of the model's own thinking time (see
    voice_worker.py's _get_searching_pcm()). Never fires if
    enable_web_search is False, and may fire more than once in a single
    call if Claude searches multiple times.

    Iterates raw stream events (not the stream.text_stream convenience
    property) specifically so search-start events are visible at all --
    text_stream only ever surfaces text deltas."""
    global _auth_disabled

    settings = get_settings()
    model_id = MODELS.get(model, MODELS["haiku"])
    if system is None:
        system = instructions.load_instructions(purpose)
    system = _with_personality(system)

    if await _preflight_refusal(purpose, model_id, prompt) is not None:
        return

    kwargs = {"model": model_id, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    if enable_web_search:
        kwargs["tools"] = [{"type": _WEB_SEARCH_TOOL, "name": "web_search", "max_uses": _WEB_SEARCH_MAX_USES}]

    full_text_parts = []
    final_usage = None
    async with _concurrency_guard:
        try:
            client = _get_async_client(settings.claude_api_key)
            async with client.messages.stream(**kwargs) as stream:
                # Headers are on the response as soon as it starts, well
                # before the stream finishes -- same rate-limit capture as
                # the non-streaming path in _call_claude_sync above.
                token_tracker.record_rate_limit_headers(stream.response.headers)
                buffer = ""
                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if getattr(block, "type", None) == "server_tool_use" and on_search_start is not None:
                            await on_search_start()
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                        delta = event.delta.text
                        buffer += delta
                        full_text_parts.append(delta)
                        while True:
                            split = _next_sentence(buffer)
                            if split is None:
                                break
                            sentence, buffer = split
                            if sentence:
                                yield sentence
                if buffer.strip():
                    yield buffer.strip()
                final = await stream.get_final_message()
                final_usage = final.usage
        except anthropic.AuthenticationError:
            _auth_disabled = True
            logger.error("ask_claude: invalid Claude API key — disabling further calls until restart")
            await log_llm_call_async(purpose, model_id, prompt, status="auth_error")
            return
        except anthropic.RateLimitError:
            logger.warning("ask_claude: rate limited — failing this call, a later message can retry")
            await log_llm_call_async(purpose, model_id, prompt, status="rate_limited")
            return
        except anthropic.APIStatusError as e:
            logger.error(f"ask_claude: Claude API error ({e.status_code}): {e.message}")
            await log_llm_call_async(purpose, model_id, prompt, status="api_error", detail=f"HTTP {e.status_code}: {e.message}")
            return
        except anthropic.APIConnectionError as e:
            # type(e).__name__ only, never str(e)/exc_info — see ask_claude's
            # equivalent handler above.
            logger.error(f"ask_claude: connection error: {type(e).__name__}")
            await log_llm_call_async(purpose, model_id, prompt, status="connection_error", detail=type(e).__name__)
            return

    if final_usage is not None:
        token_tracker.record_usage(
            model=model_id,
            prompt_tokens=final_usage.input_tokens,
            completion_tokens=final_usage.output_tokens,
            cost=token_tracker.calculate_cost(model_id, final_usage.input_tokens, final_usage.output_tokens),
        )
    await log_llm_call_async(purpose, model_id, prompt, status="success", response="".join(full_text_parts))


def _call_claude_sync(
    api_key: str,
    model_id: str,
    max_tokens: int,
    system: Optional[str],
    prompt: str,
    temperature: Optional[float] = None,
    enable_web_search: bool = False,
):
    """Runs in a thread via asyncio.to_thread — the anthropic SDK's client is
    sync/blocking, and this is a network call, so it must not run directly
    on the event loop (unlike vault_io's local file writes, which are fast
    enough to stay inline — see vault_io.py's concurrency note).

    _get_client() reuses a cached client instead of constructing a fresh
    one per call -- safe to touch _client_cache here with no extra lock:
    ask_claude()'s own _concurrency_guard already limits this whole
    function to one in-flight call at a time, so this is never actually
    entered concurrently despite running off the event loop."""
    client = _get_client(api_key)
    kwargs = {"model": model_id, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    if enable_web_search:
        kwargs["tools"] = [{"type": _WEB_SEARCH_TOOL, "name": "web_search", "max_uses": _WEB_SEARCH_MAX_USES}]
    # with_raw_response instead of a plain .create() so the real Anthropic
    # rate-limit headers are reachable -- .parse() below gives back the
    # exact same Message object .create() would have, so nothing else in
    # this file changes.
    raw = client.messages.with_raw_response.create(**kwargs)
    token_tracker.record_rate_limit_headers(raw.headers)
    return raw.parse()


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
        logger.error(f"Failed to write to LLM usage log: {e}", exc_info=True)


async def log_llm_call_async(
    purpose: str,
    model: str,
    prompt: str,
    status: str = "success",
    detail: Optional[str] = None,
    response: Optional[str] = None,
) -> None:
    """log_llm_call, off the event loop. Every call site in this module
    uses this instead of calling log_llm_call directly, so the blocking
    file write there never runs inline on the event loop -- same reasoning
    as _call_claude_sync already being run via asyncio.to_thread instead of
    inline. Same content, same file, same order (each call is individually
    awaited under _concurrency_guard, so relative ordering across calls in
    the same coroutine is unchanged)."""
    await asyncio.to_thread(log_llm_call, purpose, model, prompt, status, detail, response)
