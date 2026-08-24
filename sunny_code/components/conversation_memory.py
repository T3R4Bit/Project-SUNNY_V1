"""Session-scoped memory for open-ended conversation (the general-chat LLM
fallback in briefing.py's custom_briefing) -- in-memory only, resets on
restart, never written to the vault or persisted anywhere. Deliberately
narrow scope: command routing (tasks/lists/alarms/calendar/etc.) is
stateless by design and doesn't touch this; this exists only so a genuine
conversational follow-up ("why", "tell me another one", "what about that")
makes sense to Claude the way it would in a real back-and-forth, not so
Sunny remembers facts across days.
"""

from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

MAX_TURNS = 6  # 3 user/assistant exchanges -- enough for a real follow-up
# to resolve without growing the prompt unbounded

_history: Dict[str, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_TURNS))


def record_turn(session_id: str, role: str, text: str) -> None:
    """role is "user" or "assistant". No-ops on falsy text (nothing to
    remember from an empty answer)."""
    if not text:
        return
    _history[session_id].append((role, text))


def format_for_prompt(session_id: str) -> str:
    """Recent turns as plain text, oldest first, ready to prepend to a new
    prompt -- empty string if there's no history yet, so callers can
    prepend this unconditionally without a branch."""
    turns: List[Tuple[str, str]] = list(_history[session_id])
    if not turns:
        return ""
    lines = [f"{'Sunny' if role == 'assistant' else 'User'}: {text}" for role, text in turns]
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"
