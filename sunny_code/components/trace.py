"""Real-time execution-trace log for the web console's Logs tab.

Every call to assistant.handle_message() (web chat, Discord, and the Pi
companion all funnel through that one entry point) records one trace here:
what came in, which routing branch handled it, what went out, and whether it
errored. Traces are both persisted (traces.jsonl, rotated the same way
logging_config.py rotates sunny.log) and pushed live to any open Logs tab
over SSE.

mark_route() is a contextvars-based side channel: routing branches inside
handle_message() call it right before returning, without changing any
control flow. current_route() is read once by handle_message()'s wrapper
after the routing chain finishes.
"""

import asyncio
import contextvars
import json
import logging
import logging.handlers
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from sunny_code.config import get_settings

_UNCLASSIFIED = "unclassified"

_route_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_route", default=_UNCLASSIFIED)
_path_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_path", default="")

_subscribers: set = set()

_trace_logger = logging.getLogger("sunny.trace")
_trace_logger.propagate = False
_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        settings.logs_dir / "traces.jsonl",
        maxBytes=10_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    _trace_logger.addHandler(handler)
    _trace_logger.setLevel(logging.INFO)
    _configured = True


def mark_route(route: str, path: str = "") -> None:
    """Tag the routing decision (and optional sub-path) for the trace that
    will be recorded when the current handle_message() call finishes. A
    branch that never calls this just reports "unclassified" -- harmless,
    just a label worth tightening later."""
    _route_var.set(route)
    _path_var.set(path)


def current_route() -> tuple:
    """Read back what the active branch tagged, then reset for the next
    call on this task."""
    route, path = _route_var.get(), _path_var.get()
    _route_var.set(_UNCLASSIFIED)
    _path_var.set("")
    return route, path


def record_trace(
    *,
    source: str,
    session_id: str,
    input_text: str,
    route: str,
    path: str,
    result: Optional[str],
    error: Optional[str],
    duration_ms: float,
) -> None:
    """Persist one trace line and push it to any live Logs tab."""
    _ensure_configured()
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "session_id": session_id,
        "input": input_text,
        "route": route,
        "path": path,
        "result": result,
        "error": error,
        "success": error is None,
        "duration_ms": round(duration_ms, 1),
    }
    _trace_logger.info(json.dumps(event))
    for queue in list(_subscribers):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # a slow/stuck viewer shouldn't block or crash message handling


def recent_traces(limit: int = 200) -> list:
    """Last `limit` trace events, oldest first -- backs the Logs tab's
    initial render before the live SSE stream takes over."""
    _ensure_configured()
    settings = get_settings()
    path = settings.logs_dir / "traces.jsonl"
    if not path.exists():
        return []
    lines: deque = deque(maxlen=limit)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def subscribe() -> asyncio.Queue:
    """Register a new SSE client. Pair with unsubscribe() in a finally block."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)
