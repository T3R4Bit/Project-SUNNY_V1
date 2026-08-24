"""Tracks what happened to a proactive suggestion Sunny made -- accepted,
rejected, ignored, or snoozed -- per personal-assistant-vision.md section 12
("Learning From Behavior"). No real caller yet: this exists so a future
proactive feature (a workout-window suggestion, an opportunity surfaced by
the opportunity engine, etc.) has one place to record outcomes instead of
each feature inventing its own tracking, and so acceptance_rate() below is
already available the day the first real suggestion-emitting feature is
built.

Append-only vault log, same shape as health_check.py's report log -- this
is "one growing timeline," not "many independent records," so it follows
that pattern rather than tasks_db.py's one-file-per-item shape (see
sunny-vault/docs/system-state.md's note on picking between the two).
"""

import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

Outcome = Literal["accepted", "rejected", "ignored", "snoozed"]
_OUTCOMES = ("accepted", "rejected", "ignored", "snoozed")

_SUGGESTED_RE = re.compile(r"^\*\*([\d\-T:.]+\+?[\d:]*)\*\* \[suggested\] id=(\S+) kind=(\S+) — (.*)$")
_OUTCOME_RE = re.compile(r"^\*\*([\d\-T:.]+\+?[\d:]*)\*\* \[outcome\] id=(\S+) kind=(\S+) -> (\w+)$")


def _log_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "log" / "suggestions.md"


def _append(line: str) -> None:
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        logger.error(f"suggestion_tracker: failed to write log: {e}")


def record_suggestion(kind: str, content: str) -> str:
    """Logs that Sunny made a suggestion and returns a new id for it --
    pass that id to record_outcome() once you know what happened. `kind`
    is a short, stable category (e.g. "workout_window", "opportunity",
    "study_review") -- acceptance_rate() groups by this, so keep it
    consistent per suggestion type rather than inventing a new string per
    call."""
    suggestion_id = uuid.uuid4().hex[:8]
    ts = datetime.now(timezone.utc).isoformat()
    _append(f"**{ts}** [suggested] id={suggestion_id} kind={kind} — {content}")
    return suggestion_id


def record_outcome(suggestion_id: str, outcome: Outcome) -> None:
    """Logs what happened to a suggestion. Takes the kind from the matching
    "suggested" line rather than as a separate argument -- one less thing
    for a caller to get wrong/inconsistent, and keeps kind grouping
    reliable even if a caller mislabels it here."""
    if outcome not in _OUTCOMES:
        raise ValueError(f"Unknown outcome {outcome!r} -- must be one of {', '.join(_OUTCOMES)}")

    kind = "unknown"
    path = _log_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _SUGGESTED_RE.match(line)
            if match and match.group(2) == suggestion_id:
                kind = match.group(3)
                break

    ts = datetime.now(timezone.utc).isoformat()
    _append(f"**{ts}** [outcome] id={suggestion_id} kind={kind} -> {outcome}")


def acceptance_rate(kind: str, days: int = 30) -> Optional[float]:
    """Fraction of `kind` suggestions in the last `days` days whose outcome
    was "accepted", counting only suggestions that actually got an outcome
    recorded (a suggestion with no outcome yet -- still pending -- isn't
    counted as ignored just because it hasn't resolved). None if there's no
    resolved suggestion of this kind in the window at all, so a caller can
    distinguish "no data" from "a real 0% rate"."""
    path = _log_path()
    if not path.exists():
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    outcomes = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _OUTCOME_RE.match(line)
        if not match or match.group(3) != kind:
            continue
        try:
            ts = datetime.fromisoformat(match.group(1))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        outcomes[match.group(4)] += 1

    total = sum(outcomes.values())
    if total == 0:
        return None
    return outcomes["accepted"] / total
