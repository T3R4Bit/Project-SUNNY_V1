"""Layer 2 rules engine -- hardcoded, deterministic automation from
personal-assistant-vision.md section 10: "Hard-coded logic for predictable
behavior", explicitly NOT an LLM call per check. Deliberately a plain
ordered list of (name, condition, action) tuples, not a DSL or a
plugin/registration system -- this project's stated anti-overengineering
stance, and there's no real need yet for anything more dynamic than "add a
tuple to the list."

Seeded with the two rules actually implementable today against real Layer 1
sensor data (sensors.py) with no new external integration: a vault note
changed, or a calendar event changed. The vision doc's other example rules
(exam-date study prep, workout-window suggestions) need data sources that
don't exist yet (a Classes/ vault convention, Garmin) -- see BACKLOG.md,
left for when those are actually being built.

evaluate() is called on a scheduled loop (see main.py's rules_engine_loop)
-- this module itself has no scheduling logic, just "run once, report what
fired."
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional

from sunny_code.components import sensors
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)


class Rule(NamedTuple):
    name: str
    condition: Callable[[Dict], bool]
    action: Callable[[Dict], Optional[str]]


def _log_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "log" / "rules-engine.md"


def _append_log(line: str) -> None:
    from datetime import datetime, timezone

    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"**{datetime.now(timezone.utc).isoformat()}** {line}\n")
    except OSError as e:
        logger.error(f"rules_engine: failed to write log: {e}")


def _describe_and_log(prefix: str, items: List[str]) -> str:
    shown = ", ".join(items[:5])
    more = f" (+{len(items) - 5} more)" if len(items) > 5 else ""
    description = f"{prefix}: {len(items)} — {shown}{more}"
    _append_log(description)
    return description


def _vault_note_changed(context: Dict) -> bool:
    return bool(context["vault_changes"])


def _log_vault_note_changed(context: Dict) -> Optional[str]:
    names = [p.name for p in context["vault_changes"]]
    return _describe_and_log("vault note(s) changed", names)


def _calendar_event_changed(context: Dict) -> bool:
    return bool(context["calendar_changes"])


def _log_calendar_event_changed(context: Dict) -> Optional[str]:
    titles = [e.get("summary", "(untitled)") for e in context["calendar_changes"]]
    return _describe_and_log("calendar event(s) changed", titles)


_RULES: List[Rule] = [
    Rule("vault_note_changed", _vault_note_changed, _log_vault_note_changed),
    Rule("calendar_event_changed", _calendar_event_changed, _log_calendar_event_changed),
]


def evaluate() -> List[str]:
    """Runs every Layer 1 sensor once, builds a small shared context, and
    checks every rule's condition against it -- a rule whose condition
    fires runs its action and its description (if any) is included in the
    returned list. Nothing here calls an LLM. The returned list is for
    logging/visibility -- no interface surfaces it to the user yet, this
    is the first real end-to-end trip through Layers 1-2 with a genuine
    (if modest) consumer, not a no-op placeholder."""
    context = {
        "vault_changes": sensors.vault_file_changes(),
        "calendar_changes": sensors.calendar_changes(),
    }
    fired = []
    for rule in _RULES:
        try:
            if rule.condition(context):
                result = rule.action(context)
                if result:
                    fired.append(result)
        except Exception as e:
            logger.error(f"rules_engine: rule {rule.name!r} failed: {e}", exc_info=True)
    return fired
