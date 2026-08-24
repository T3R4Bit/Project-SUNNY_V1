"""Exam-prep / spaced-review -- personal-assistant-vision.md section 3.

Reads class notes from a real, user-confirmed vault convention (not
guessed): sunny-vault/KSU/<semester>/<class>/*.md, one file per topic.

Exam dates come from Google Calendar. There's no vault-side "exam date"
convention, and google_calendar.find_event_by_title()'s plain substring
match is too strict here -- it requires the query to already be a
substring of the real title, which won't reliably match a real calendar
entry like "BUS 2100 Midterm Exam" against a query like "BUS 2100 exam".
find_exam_date() below instead checks the class name and an exam keyword
independently against each candidate title.

The vision doc's five-stage New -> Review -> Weak -> Retest -> Mastered
pipeline is simplified to three real persisted states (new/weak/mastered).
Review and Retest are the ACT of calling record_review(), not separate
stored states -- modeling five persisted stages added complexity with no
behavioral difference for a single-user tool. See
sunny-vault/docs/architecture/exam-prep.md.

generate_study_review() is the one real LLM-backed feature here (the
vision doc's "night before" output) -- everything else is inert data
plumbing until a caller uses it, same as vault_permissions.py/
suggestion_tracker.py from the proactive-architecture pass.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Literal, Optional

from sunny_code.components import google_calendar, vault_io
from sunny_code.components.llm_client import ask_claude
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_EXAM_KEYWORDS = ("exam", "midterm", "final", "test", "quiz")
_REVIEW_FIELD_ORDER = ["id", "class_name", "note", "stage", "last_reviewed"]
_MAX_TOPICS_PER_REVIEW = 5
_MAX_NOTE_CHARS = 2000  # per note, keeps the review prompt bounded regardless of note length


def _ksu_root() -> Path:
    return get_settings().project_root / "sunny-vault" / "KSU"


def list_classes() -> List[Dict]:
    """Every class folder found under sunny-vault/KSU/<semester>/<class>/,
    across every semester folder present (no assumption about which
    semester is "current" -- semester folder naming isn't parsed, just
    walked). [] if the KSU folder doesn't exist yet at all."""
    root = _ksu_root()
    if not root.exists():
        return []

    classes = []
    for semester_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for class_dir in sorted(p for p in semester_dir.iterdir() if p.is_dir()):
            notes = sorted(class_dir.glob("*.md"))
            classes.append({
                "semester": semester_dir.name,
                "class": class_dir.name,
                "path": class_dir,
                "notes": notes,
            })
    return classes


def find_class(name: str) -> Optional[Dict]:
    """Case-insensitive exact or substring match on class folder name
    across every semester -- soonest-listed semester wins on ambiguity
    (list_classes() is already sorted). None if nothing matches or KSU/
    doesn't exist."""
    needle = name.strip().lower()
    if not needle:
        return None
    classes = list_classes()
    for c in classes:
        if c["class"].lower() == needle:
            return c
    for c in classes:
        if needle in c["class"].lower():
            return c
    return None


def find_exam_date(class_name: str, days_ahead: int = 60) -> Optional[Dict]:
    """The soonest upcoming calendar event whose title contains both
    `class_name` and one of _EXAM_KEYWORDS, independently (not as one
    combined substring -- see module docstring for why). Returns the raw
    event dict (has "summary", "start", etc.) or None if Calendar isn't
    connected or nothing matches."""
    now = datetime.now().astimezone()
    raw_events = google_calendar.get_events_range(now, now + timedelta(days=days_ahead))
    if raw_events is None:
        return None

    needle = class_name.strip().lower()
    if not needle:
        return None

    candidates = [
        e for e in raw_events
        if needle in e.get("summary", "").lower()
        and any(kw in e.get("summary", "").lower() for kw in _EXAM_KEYWORDS)
    ]
    if not candidates:
        return None

    def _sort_key(event: Dict) -> str:
        start = event.get("start", {})
        return start.get("dateTime") or start.get("date") or ""

    candidates.sort(key=_sort_key)
    return candidates[0]


def _review_path(class_name: str, note_stem: str) -> Path:
    slug = vault_io.slugify(f"{class_name}-{note_stem}")
    return get_settings().project_root / "sunny-vault" / "state" / "exam-review" / f"{slug}.md"


def get_review_state(class_name: str, note_stem: str) -> Dict:
    """{"stage": "new"|"weak"|"mastered", "last_reviewed": iso-string-or-None}.
    Defaults to "new" (never reviewed) if no state file exists yet -- this
    doesn't create one; only record_review() writes."""
    path = _review_path(class_name, note_stem)
    if not path.exists():
        return {"stage": "new", "last_reviewed": None}
    try:
        metadata, _body = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return {"stage": "new", "last_reviewed": None}
    return {"stage": metadata.get("stage", "new"), "last_reviewed": metadata.get("last_reviewed")}


def record_review(class_name: str, note_stem: str, result: Literal["good", "weak"]) -> str:
    """Advances (or resets) the topic's stage and returns the new one.
    new/weak/mastered + "good" -> mastered. Any stage + "weak" -> weak
    (even a previously-mastered topic that's now shaky goes back to weak
    -- normal spaced-repetition behavior, not a bug)."""
    if result not in ("good", "weak"):
        raise ValueError(f"result must be 'good' or 'weak', got {result!r}")

    new_stage = "mastered" if result == "good" else "weak"
    now_iso = datetime.now().isoformat()
    metadata = {
        "id": vault_io.slugify(f"{class_name}-{note_stem}"),
        "class_name": class_name,
        "note": note_stem,
        "stage": new_stage,
        "last_reviewed": now_iso,
    }
    body = f"\n# Review state: {class_name} — {note_stem}\n\nMachine-managed, not meant for hand-editing.\n"
    content = vault_io.serialize_frontmatter(metadata, body, _REVIEW_FIELD_ORDER)
    vault_io.atomic_write_text(_review_path(class_name, note_stem), content)
    return new_stage


def topics_needing_review(class_name: str) -> List[Dict]:
    """Every note in `class_name` whose stage isn't "mastered" (an unseen
    note counts as "new"), ordered new-first-then-weak -- new topics have
    never been looked at, so they're the highest-value use of a review
    session. [] if the class isn't found."""
    class_info = find_class(class_name)
    if class_info is None:
        return []

    topics = []
    for note_path in class_info["notes"]:
        state = get_review_state(class_info["class"], note_path.stem)
        if state["stage"] != "mastered":
            topics.append({"note": note_path, "stage": state["stage"]})

    order = {"new": 0, "weak": 1}
    topics.sort(key=lambda t: order.get(t["stage"], 2))
    return topics


async def generate_study_review(class_name: str) -> Optional[str]:
    """The vision doc's "night before" output: the highest-value topics
    (new and weak, capped at _MAX_TOPICS_PER_REVIEW), their actual note
    content, written up by Claude into a short, focused review. Returns
    None if the class isn't found, has no topics needing review, or
    Claude is unreachable -- caller decides how to phrase that, matching
    every other ask_claude() consumer's fail-quiet contract."""
    class_info = find_class(class_name)
    if class_info is None:
        return None

    topics = topics_needing_review(class_info["class"])[:_MAX_TOPICS_PER_REVIEW]
    if not topics:
        return None

    sections = []
    for topic in topics:
        try:
            text = topic["note"].read_text(encoding="utf-8")
        except OSError:
            continue
        sections.append(f"## {topic['note'].stem} (stage: {topic['stage']})\n{text[:_MAX_NOTE_CHARS]}")

    if not sections:
        return None

    prompt = f"Class: {class_info['class']}\n\n" + "\n\n".join(sections)
    return await ask_claude(prompt=prompt, model="sonnet", purpose="exam_prep_review")
