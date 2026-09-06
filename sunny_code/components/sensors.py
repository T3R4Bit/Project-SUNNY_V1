"""Layer 1 sensors -- cheap, deterministic, no LLM calls -- from
personal-assistant-vision.md section 10 ("Hybrid AI Architecture"). Each
function answers "what changed since I last checked", using only existing
data sources (Google Calendar, the vault filesystem) with no new external
integration. No real caller yet: rules_engine.py is the first consumer,
evaluating its rules against whatever these report.

Each sensor owns its own small persisted "what have I seen before" cursor
(a JSON file under sunny-vault/data/state/), so a caller just calls the
function every tick with no cursor bookkeeping of its own -- same shape as
category_store.py/location_store.py owning their own state file.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

from sunny_code.components import google_calendar, vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Vault subfolders that are Sunny's own bookkeeping, not user content --
# excluded from vault_file_changes() so the sensor reports things like a
# new note under Classes/ or Projects/, not every internal task/list file
# rewrite or log append this app already makes constantly on its own.
_EXCLUDED_VAULT_DIRS = {".obsidian", "archive", "log", "state", "instructions"}


def _calendar_cursor_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "data" / "state" / "sensor-calendar-cursor.json"


def _vault_cursor_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "data" / "state" / "sensor-vault-cursor.json"


def _load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.error(f"sensors: {path} unreadable: {e}", exc_info=True)
        return {}


def _save_json(path: Path, data: Dict) -> None:
    vault_io.atomic_write_text(path, json.dumps(data, indent=2))


def calendar_changes(days_ahead: int = 14) -> List[Dict]:
    """Calendar events that are new or have a different 'updated' timestamp
    than the last time this was called, looked ahead `days_ahead` days from
    now (matches google_calendar.find_event_by_title's existing lookahead
    convention). Returns [] if Calendar isn't connected -- same fail-quiet
    contract as google_calendar.py itself, not an error.

    Deletions aren't detected: Google's events().list() simply omits a
    deleted event from the results, indistinguishable here from "outside
    the window" -- real deletion tracking would need syncToken support,
    out of scope for this pass."""
    from datetime import datetime, timedelta

    now = datetime.now().astimezone()
    raw_events = google_calendar.get_events_range(now, now + timedelta(days=days_ahead))
    if raw_events is None:
        return []

    cursor = _load_json(_calendar_cursor_path())
    changed = []
    new_cursor = {}
    for event in raw_events:
        event_id = event.get("id")
        updated = event.get("updated")
        if not event_id:
            continue
        new_cursor[event_id] = updated
        if cursor.get(event_id) != updated:
            changed.append(event)

    _save_json(_calendar_cursor_path(), new_cursor)
    return changed


def vault_file_changes() -> List[Path]:
    """Markdown files under sunny-vault/ (excluding Sunny's own bookkeeping
    folders -- see _EXCLUDED_VAULT_DIRS) that are new or have a newer mtime
    than the last time this was called. A plain mtime scan, not a content
    hash -- cheap and sufficient for "does a rule need to look at this",
    not for detecting a no-op save that leaves mtime unchanged but content
    identical (not worth the extra I/O to distinguish)."""
    vault_root = get_settings().project_root / "sunny-vault"
    cursor = _load_json(_vault_cursor_path())
    changed = []
    new_cursor = {}

    for path in vault_root.rglob("*.md"):
        if any(part in _EXCLUDED_VAULT_DIRS for part in path.relative_to(vault_root).parts):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        key = str(path.relative_to(vault_root))
        new_cursor[key] = mtime
        if cursor.get(key) != mtime:
            changed.append(path)

    _save_json(_vault_cursor_path(), new_cursor)
    return changed
