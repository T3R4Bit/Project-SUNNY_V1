"""Tracks due dates/exams pulled from a syllabus so the proactive
#reminders loop (discord_bot.py) can ping exactly twice per deadline --
2 days before, and the day of -- without re-pinging on every check. This
is the reminder half of class setup; class_memory.py is the reference-file
half; class_setup_engine.py wires both together with the actual calendar
writes.

Per-item vault-markdown state, same pattern as tasks_db.py: one file per
deadline, id/class_name/title/date/kind plus two sent-flags.
"""

import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Literal, Optional

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_FIELD_ORDER = ["id", "class_name", "title", "date", "kind", "t2_sent", "t0_sent", "created_at"]

PostFn = Callable[[str], Awaitable[None]]


def _deadlines_dir() -> Path:
    return get_settings().project_root / "sunny-vault" / "state" / "class-deadlines"


def create_deadline(class_name: str, title: str, deadline_date: str, kind: Literal["due", "exam"]) -> str:
    """deadline_date is a "YYYY-MM-DD" string -- matches syllabus_parser's
    output directly, no reparsing needed. Returns the new deadline's id."""
    deadline_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    metadata = {
        "id": deadline_id,
        "class_name": class_name,
        "title": title,
        "date": deadline_date,
        "kind": kind,
        "t2_sent": False,
        "t0_sent": False,
        "created_at": now,
    }
    body = f"\n# {title}\n"
    content = vault_io.serialize_frontmatter(metadata, body, _FIELD_ORDER)
    slug = vault_io.slugify(f"{class_name}-{title}-{deadline_id}")
    vault_io.atomic_write_text(_deadlines_dir() / f"{slug}.md", content)
    return deadline_id


def _iter_deadlines():
    directory = _deadlines_dir()
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Skipping unreadable deadline file {path}: {e}")
            continue
        metadata, _body = vault_io.parse_frontmatter(text)
        if metadata and "id" in metadata:
            yield path, metadata


async def check_and_notify(post_fn: PostFn) -> int:
    """Scans every tracked deadline; sends one #reminders ping via
    post_fn(text) at T-2 (2 days before the date) and one at T-0 (the day
    of), gated by the t2_sent/t0_sent flags so a check that runs more than
    once a day never double-pings. Date-only comparison, not exact time,
    so the check cadence doesn't need precise timing. Returns how many
    pings were sent this call."""
    today = date.today()
    sent_count = 0

    for path, metadata in _iter_deadlines():
        try:
            deadline_date = date.fromisoformat(metadata["date"])
        except (ValueError, KeyError):
            continue

        days_until = (deadline_date - today).days
        kind_label = "Exam" if metadata.get("kind") == "exam" else "Due"
        changed = False

        if days_until == 2 and not metadata.get("t2_sent"):
            await post_fn(
                f"{metadata['class_name']}: {metadata['title']} ({kind_label}) is in 2 days ({metadata['date']})."
            )
            metadata["t2_sent"] = True
            changed = True
            sent_count += 1

        if days_until == 0 and not metadata.get("t0_sent"):
            await post_fn(f"{metadata['class_name']}: {metadata['title']} ({kind_label}) is today.")
            metadata["t0_sent"] = True
            changed = True
            sent_count += 1

        if changed:
            body = f"\n# {metadata['title']}\n"
            content = vault_io.serialize_frontmatter(metadata, body, _FIELD_ORDER)
            vault_io.atomic_write_text(path, content)

    return sent_count


def get_upcoming(class_name: Optional[str] = None) -> List[Dict]:
    """Every tracked deadline from today onward, optionally filtered to
    one class."""
    today = date.today()
    result = []
    for _path, metadata in _iter_deadlines():
        try:
            if date.fromisoformat(metadata["date"]) < today:
                continue
        except (ValueError, KeyError):
            continue
        if class_name and metadata.get("class_name", "").lower() != class_name.lower():
            continue
        result.append(metadata)
    result.sort(key=lambda m: m["date"])
    return result
