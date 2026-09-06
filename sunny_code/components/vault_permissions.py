"""Permission-leveled vault write access -- the Layer 5 (executor/permission
check) groundwork from sunny-vault/docs/architecture/personal-assistant-vision.md
section 7. No real caller yet: this exists so a future feature that wants to
modify the vault on its own initiative (the knowledge health check
suggesting cleanup, eventually) has one place to ask "should this actually
happen automatically, or does a human need to say yes first" instead of
each feature inventing its own answer.

Four levels (vision doc's own definitions):
  0 -- read only, never reaches this module at all (nothing to gate)
  1 -- safe edits: add a tag, add a link, update an index, append, create a
       new note
  2 -- controlled organization: rename a file, move a file, reorganize a
       folder
  3 -- destructive: delete a note, bulk-modify files, large-scale
       restructuring -- ALWAYS requires explicit approval, confidence is
       irrelevant (the vision doc states this as a hard rule under Level 3,
       not just a confidence-band consequence)

Confidence thresholds (also the vision doc's own numbers), applied to
levels 1-2 only: >95% auto, 80-95% suggest, <80% ask.

Every call is logged, not just autos -- same "log every attempt, not just
what happened" reasoning as llm_client.log_llm_call, so a future audit can
see what was asked for and refused/deferred, not just what actually ran.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

Decision = Literal["auto", "suggest", "ask"]

_OPERATION_LEVELS = {
    # Level 1 -- safe edits
    "add_tag": 1,
    "add_link": 1,
    "update_index": 1,
    "append": 1,
    "create_note": 1,
    # Level 2 -- controlled organization
    "rename_file": 2,
    "move_file": 2,
    "reorganize_folder": 2,
    # Level 3 -- destructive, explicit approval always required
    "delete_note": 3,
    "bulk_modify": 3,
    "large_restructure": 3,
}

_AUTO_THRESHOLD = 0.95
_SUGGEST_THRESHOLD = 0.80


def operation_level(operation: str) -> int:
    """The permission level for a named operation. An unrecognized
    operation is treated as level 3 (safest default -- ask, never guess
    that something unfamiliar is safe to automate) and logged as a warning
    so a genuinely new, legitimate operation gets added to the table above
    instead of silently always requiring approval forever."""
    if operation not in _OPERATION_LEVELS:
        logger.warning(f"vault_permissions: unrecognized operation {operation!r}, treating as level 3")
        return 3
    return _OPERATION_LEVELS[operation]


def classify(operation: str, confidence: float) -> Decision:
    """The decision for one write, without logging it -- request_vault_write()
    below is the real entry point (it also logs); this is split out so a
    caller that just wants to know the answer for planning purposes (e.g.
    deciding what to even offer to the user) doesn't write a log entry for
    a hypothetical it never acts on."""
    level = operation_level(operation)
    if level >= 3:
        return "ask"
    if confidence >= _AUTO_THRESHOLD:
        return "auto"
    if confidence >= _SUGGEST_THRESHOLD:
        return "suggest"
    return "ask"


def _log_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "log" / "vault-edits.md"


def _log(operation: str, level: int, confidence: float, description: str, decision: Decision) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = (
        f"**{ts}** [{operation}] level={level} confidence={confidence:.0%} "
        f"-> {decision} — {description}\n"
    )
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        logger.error(f"vault_permissions: failed to write edit log: {e}", exc_info=True)


def request_vault_write(operation: str, confidence: float, description: str) -> Decision:
    """The real entry point: classifies the write and logs the decision
    (every call, not just "auto" ones -- see module docstring). Returns
    what should happen, the caller is responsible for actually acting on
    it (performing the write for "auto", presenting the suggestion for
    "suggest", or asking and waiting for "ask") -- this module only
    decides, it never touches vault files itself."""
    level = operation_level(operation)
    decision = classify(operation, confidence)
    _log(operation, level, confidence, description, decision)
    return decision


def recent_log(limit: int = 20) -> Optional[str]:
    """The last `limit` lines of the edit log, or None if nothing's been
    logged yet -- for a future "what have you been doing to my vault"
    query, not wired to any interface yet."""
    path = _log_path()
    if not path.exists():
        return None
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return None
    return "\n".join(lines[-limit:])
