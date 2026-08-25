"""Per-class memory -- one vault-markdown file per class holding the
syllabus summary and a structured key-dates list, so Sunny can answer
"what's due in BUS 2100" or pull real context without re-parsing the
syllabus. Same per-item vault-markdown pattern as tasks_db.py/lists_db.py:
one file, slug from the class name, frontmatter + body via vault_io.
Lives under sunny-vault/state/classes/, matching how tasks/lists keep
Sunny-managed lookup state under state/.

save_class() above is Sunny's own fast-lookup copy. save_to_class_folder()
below writes two *different* files into the user's own
sunny-vault/KSU/<semester>/<class>/ folder (exam_prep.py's existing
convention for hand-written topic notes) -- a verbatim copy of the pasted
syllabus, and a class-info.md with the same summary/schedule/key-dates
content, so it's visible sitting right next to the user's own notes
instead of tucked away in a gitignored state/ folder only Sunny reads.
class-info.md is deliberately excluded from exam_prep.py's topic list
(see _NON_TOPIC_FILENAMES there) -- it's reference context, not a
spaced-repetition topic to track "mastered" on -- but
generate_study_review() reads it as prompt context when present.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_FIELD_ORDER = ["id", "class_name", "semester", "created_at", "updated_at"]

# Same set exam_prep.py excludes from its topic list -- keep in sync.
SYLLABUS_FILENAME = "syllabus.md"
CLASS_INFO_FILENAME = "class-info.md"

_UNSAFE_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _classes_dir() -> Path:
    return get_settings().project_root / "sunny-vault" / "state" / "classes"


def _slug(class_name: str) -> str:
    return vault_io.slugify(class_name)


def _path(class_name: str) -> Path:
    return _classes_dir() / f"{_slug(class_name)}.md"


def _safe_folder_name(text: str) -> str:
    """Strips characters that would break a filesystem path while keeping
    the original casing/spacing -- unlike vault_io.slugify(), which is
    meant for filenames, not the human-readable folder names exam_prep.py
    displays back verbatim (e.g. "BUS 2100", not "bus-2100")."""
    cleaned = _UNSAFE_PATH_CHARS_RE.sub("", text).strip()
    return cleaned or "untitled"


def _ksu_class_dir(class_name: str, semester: str) -> Path:
    return (
        get_settings().project_root / "sunny-vault" / "KSU"
        / _safe_folder_name(semester) / _safe_folder_name(class_name)
    )


def save_to_class_folder(
    class_name: str, semester: str, syllabus_text: str, summary: str,
    meeting_times: List[Dict], key_dates: List[Dict],
) -> None:
    """Writes syllabus.md (the raw pasted text, verbatim) and
    class-info.md (summary + schedule + key dates, same content
    save_class() above tracks internally) into the class's own
    sunny-vault/KSU/<semester>/<class>/ folder. Overwrites both wholesale
    on a re-run, same "fresh paste is the new source of truth" behavior
    as save_class(); never touches any other file already in that folder
    (the user's own hand-written topic notes)."""
    class_dir = _ksu_class_dir(class_name, semester)

    syllabus_body = f"# {class_name} — {semester}\n\nVerbatim copy of the syllabus pasted during class setup.\n\n---\n\n{syllabus_text.strip()}\n"
    vault_io.atomic_write_text(class_dir / SYLLABUS_FILENAME, syllabus_body)

    lines = [f"# {class_name} — {semester}\n"]
    if summary:
        lines.append(f"{summary}\n")
    if meeting_times:
        lines.append("## Meets")
        for mt in meeting_times:
            days_str = "/".join(d[:3] for d in mt["days"])
            loc = f" @ {mt['location']}" if mt.get("location") else ""
            lines.append(f"- {days_str} {mt['start_time']}-{mt['end_time']}{loc}")
        lines.append("")
    if key_dates:
        lines.append("## Key Dates")
        for d in sorted(key_dates, key=lambda x: x["date"]):
            label = "Exam" if d.get("kind") == "exam" else "Due"
            lines.append(f"- {d['date']}: {d['title']} ({label})")
        lines.append("")
    vault_io.atomic_write_text(class_dir / CLASS_INFO_FILENAME, "\n".join(lines))
    logger.info(f"Class vault copy saved: {class_name} ({semester}) -> {class_dir}")


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
