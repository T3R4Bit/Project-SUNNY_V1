"""Per-class memory -- one vault-markdown file per class holding the
syllabus summary and a structured key-dates list, so Sunny can answer
"what's due in BUS 2100" or pull real context without re-parsing the
syllabus. Same per-item vault-markdown pattern as tasks_db.py/lists_db.py:
one file, slug from the class name, frontmatter + body via vault_io.

Deliberately separate from exam_prep.py's sunny-vault/KSU/<semester>/
<class>/*.md convention -- that's the user's own hand-written topic
notes; this is Sunny-managed state, so it lives under
sunny-vault/state/classes/ instead, matching how tasks/lists keep
Sunny-managed data under state/ while the user's own vault content stays
untouched elsewhere.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_FIELD_ORDER = ["id", "class_name", "semester", "created_at", "updated_at"]


def _classes_dir() -> Path:
    return get_settings().project_root / "sunny-vault" / "state" / "classes"


def _slug(class_name: str) -> str:
    return vault_io.slugify(class_name)


def _path(class_name: str) -> Path:
    return _classes_dir() / f"{_slug(class_name)}.md"


def save_class(class_name: str, semester: str, summary: str, key_dates: List[Dict]) -> None:
    """key_dates: [{"title": ..., "date": "YYYY-MM-DD", "kind": "due"|"exam"}, ...].
    Overwrites any existing file for this class wholesale -- re-running
    setup for the same class replaces its memory rather than merging,
    since a fresh syllabus paste is meant to be the new source of truth."""
    existing = get_class(class_name)
    now = datetime.utcnow().isoformat()
    metadata = {
        "id": _slug(class_name),
        "class_name": class_name,
        "semester": semester,
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
    }

    body = f"\n# {class_name} — {semester}\n"
    if summary:
        body += f"\n{summary}\n"
    if key_dates:
        body += "\n## Key Dates\n"
        for d in sorted(key_dates, key=lambda x: x["date"]):
            label = "Exam" if d.get("kind") == "exam" else "Due"
            body += f"- {d['date']}: {d['title']} ({label})\n"

    content = vault_io.serialize_frontmatter(metadata, body, _FIELD_ORDER)
    vault_io.atomic_write_text(_path(class_name), content)
    logger.info(f"Class memory saved: {class_name} ({semester})")


def get_class(class_name: str) -> Optional[Dict]:
    path = _path(class_name)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    metadata, body = vault_io.parse_frontmatter(text)
    if not metadata or "id" not in metadata:
        return None
    return {**metadata, "body": body}


def get_all_classes() -> List[Dict]:
    directory = _classes_dir()
    if not directory.exists():
        return []
    classes = []
    for path in sorted(directory.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Skipping unreadable class file {path}: {e}")
            continue
        metadata, body = vault_io.parse_frontmatter(text)
        if metadata and "id" in metadata:
            classes.append({**metadata, "body": body})
    return classes
