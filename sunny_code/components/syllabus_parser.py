"""Turns a pasted syllabus into structured schedule data via one Claude
call -- meeting times, due dates, exams, and a plain-text summary (grading
breakdown, instructor contact). Same "ask for bare JSON, defensively strip
a markdown fence if it shows up anyway" pattern as project_engine.py's
_parse_file_plan(); see sunny-vault/instructions/syllabus-parse.md for the
exact schema Claude is asked to return.
"""

import json
import logging
import re
from datetime import date
from typing import Dict, Optional

from sunny_code.components.llm_client import ask_claude

logger = logging.getLogger(__name__)

_PARSE_MODEL = "sonnet"
_PARSE_MAX_TOKENS = 2048
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _validate(data: Dict) -> Dict:
    """Raises ValueError/TypeError/KeyError on anything malformed --
    caller (class_setup_engine.py) turns that into an honest failure
    message rather than acting on a half-trusted structure."""
    if not isinstance(data.get("meeting_times"), list):
        raise ValueError("missing or invalid meeting_times")
    if not isinstance(data.get("due_dates"), list):
        raise ValueError("missing or invalid due_dates")
    if not isinstance(data.get("exams"), list):
        raise ValueError("missing or invalid exams")
    if not isinstance(data.get("summary", ""), str):
        raise ValueError("invalid summary")

    for mt in data["meeting_times"]:
        if not mt.get("days") or not isinstance(mt["days"], list):
            raise ValueError(f"meeting_times entry missing days: {mt}")
        if not re.match(r"^\d{2}:\d{2}$", mt.get("start_time", "")):
            raise ValueError(f"meeting_times entry has a bad start_time: {mt}")
        if not re.match(r"^\d{2}:\d{2}$", mt.get("end_time", "")):
            raise ValueError(f"meeting_times entry has a bad end_time: {mt}")

    for entry in data["due_dates"] + data["exams"]:
        if not entry.get("title"):
            raise ValueError(f"date entry missing a title: {entry}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", entry.get("date", "")):
            raise ValueError(f"date entry has a bad date: {entry}")

    return data


async def parse_syllabus(
    class_name: str, semester_start: date, semester_end: date, syllabus_text: str
) -> Optional[Dict]:
    """Returns the parsed structure (meeting_times/due_dates/exams/summary,
    exact shape in syllabus-parse.md) or None if Claude's unreachable or
    the response came back malformed -- caller decides how to phrase that,
    same fail-quiet contract as every other ask_claude() consumer here."""
    prompt = (
        f"Class: {class_name}\n"
        f"Semester runs {semester_start.isoformat()} to {semester_end.isoformat()}\n\n"
        f"{syllabus_text}"
    )

    raw = await ask_claude(
        prompt, model=_PARSE_MODEL, max_tokens=_PARSE_MAX_TOKENS, purpose="syllabus_parse"
    )
    if raw is None:
        return None

    try:
        cleaned = _JSON_FENCE_RE.sub("", raw.strip()).strip()
        return _validate(json.loads(cleaned))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.error(f"syllabus_parser: malformed response for {class_name!r}: {e}")
        return None
