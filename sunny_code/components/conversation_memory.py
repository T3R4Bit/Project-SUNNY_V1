"""Session-scoped memory for open-ended conversation (the general-chat LLM
fallback in briefing.py's custom_briefing) -- in-memory only, resets on
restart, never written to the vault or persisted anywhere. Deliberately
narrow scope: command routing (tasks/lists/alarms/calendar/etc.) is
stateless by design and doesn't touch this; this exists only so a genuine
conversational follow-up ("why", "tell me another one", "what about that")
makes sense to Claude the way it would in a real back-and-forth, not so
Sunny remembers facts across days.

Bounded two ways, not just one: MAX_TURNS caps how much of an *active*
conversation gets sent (unbounded turn count would grow the prompt
forever), and IDLE_EXPIRY_SECONDS caps how long a *quiet* conversation
stays around at all -- without it, the last few messages from three days
ago would silently resurface as "recent conversation" context on whatever
you happen to say next, which reads as Sunny confusing an old thread with
a new one. 2 hours, not session-count-based, so it survives normal pauses
(a few minutes away from Discord) but not a genuinely separate later
conversation.
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

MAX_TURNS = 6  # 3 user/assistant exchanges -- enough for a real follow-up
# to resolve without growing the prompt unbounded
IDLE_EXPIRY_SECONDS = 2 * 60 * 60  # 2 hours since the last turn

_history: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_TURNS))
_last_touched: Dict[str, float] = {}


def _expire_if_idle(session_id: str) -> None:
    last = _last_touched.get(session_id)
    if last is not None and time.time() - last > IDLE_EXPIRY_SECONDS:
        _history.pop(session_id, None)
        _last_touched.pop(session_id, None)


def record_turn(session_id: str, role: str, text: str) -> None:
    """role is "user" or "assistant". No-ops on falsy text (nothing to
    remember from an empty answer)."""
    if not text:
        return
    _expire_if_idle(session_id)
    _history[session_id].append((role, text))
    _last_touched[session_id] = time.time()


def format_for_prompt(session_id: str) -> str:
    """Recent turns as plain text, oldest first, ready to prepend to a new
    prompt -- empty string if there's no history yet, or if the last turn
    was more than IDLE_EXPIRY_SECONDS ago, so callers can prepend this
    unconditionally without a branch."""
    _expire_if_idle(session_id)
    turns: List[Tuple[str, str]] = list(_history[session_id])
    if not turns:
        return ""
    lines = [f"{'Sunny' if role == 'assistant' else 'User'}: {text}" for role, text in turns]
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"
