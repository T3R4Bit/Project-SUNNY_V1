"""Read-only markdown mirror of current alarms/reminders in the vault.

Unlike tasks/lists, alarms/reminders stay in SQLite (sunny_code.components.
scheduled_db.ScheduledDB) — the 30-second due-check that pings Discord needs
reliable, automatic background writes that don't belong in a hand-browsable
vault file. This module only ever reads from ScheduledDB and writes a
snapshot; nothing ever reads this file back in. See
sunny-vault/docs/architecture/alarms-reminders.md.

Wired as scheduled_engine.on_change in sunny_code/main.py (not
discord_bot.py — this must work whether or not Discord is configured).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from sunny_code.components import vault_io
from sunny_code.components.scheduled_db import ScheduledDB

logger = logging.getLogger(__name__)

_FIELD_ORDER = ["id", "type", "status", "updated_at"]


def _format_item(item: dict) -> str:
    """One line for the vault mirror — no kind label needed, items are
    already grouped under separate "## Alarms"/"## Reminders" headers."""
    try:
        when = datetime.fromisoformat(item["trigger_at"]).strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
    except (ValueError, TypeError):
        when = item["trigger_at"]
    line = f"- {when} — {item['label']}"
    if item.get("recurrence"):
        line += f" ({item['recurrence']})"
    return line


def _render(scheduled_db: ScheduledDB) -> str:
    items = scheduled_db.get_active_items()
    alarms = [i for i in items if i["kind"] == "alarm"]
    reminders = [i for i in items if i["kind"] == "reminder"]

    metadata = {
        "id": "alarms-reminders-mirror",
        "type": "mirror",
        "status": "active",
        "updated_at": datetime.utcnow().isoformat(),
    }

    body = "\n# Alarms & Reminders\n\n"
    body += (
        "Read-only snapshot — the real data lives in SQLite (scheduled.db), not here. "
        "Editing this file has no effect and any edits will be overwritten on the next change.\n\n"
    )
    body += "## Alarms\n\n"
    body += "\n".join(_format_item(i) for i in alarms) if alarms else "(none active)"
    body += "\n\n## Reminders\n\n"
    body += "\n".join(_format_item(i) for i in reminders) if reminders else "(none active)"
    body += "\n"

    return vault_io.serialize_frontmatter(metadata, body, _FIELD_ORDER)


def write_scheduled_mirror(scheduled_db: ScheduledDB, vault_root: Path) -> None:
    """Sync entry point — also called once directly at startup so the mirror
    reflects reality from process start, not just after the first change."""
    path = vault_root / "state" / "alarms-reminders.md"
    vault_io.atomic_write_text(path, _render(scheduled_db))


def create_scheduled_vault_mirror(scheduled_db: ScheduledDB, vault_root: Path) -> Callable[[], None]:
    """Returns an async-compatible closure matching scheduled_engine.on_change's
    zero-arg contract (confirmed: invoked as `await self.on_change()`, no message
    arg — unlike tasks_engine.on_change, which now optionally carries one)."""

    async def on_change():
        try:
            write_scheduled_mirror(scheduled_db, vault_root)
        except Exception as e:
            logger.error(f"Failed to update alarms-reminders vault mirror: {e}")

    return on_change
