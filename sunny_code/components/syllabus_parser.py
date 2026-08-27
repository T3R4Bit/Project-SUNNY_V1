"""Turns a pasted syllabus into structured schedule data via one Claude
call -- meeting times, due dates, exams, semester start/end, and a
plain-text summary (grading breakdown, instructor contact). Same "ask for
bare JSON, defensively strip a markdown fence if it shows up anyway"
pattern as project_engine.py's _parse_file_plan(); see
sunny-vault/docs/instructions/syllabus-parse.md for the exact schema Claude is
asked to return.
"""

import json
import logging
import re
from typing import Dict, Optional

from sunny_code.components.llm_client import ask_claude

logger = logging.getLogger(__name__)

_PARSE_MODEL = "sonnet"
_PARSE_MAX_TOKENS = 2048
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _validate(data: Dict) -> Dict:
    """Raises ValueError/TypeError/KeyError on anything malformed --
    caller (class_setup_engine.py) turns that into an honest failure
    message rather than acting on a half-trusted structure. class_name is
    allowed to come back empty (the syllabus genuinely didn't state one
    anywhere) -- the caller asks the user directly in that case rather
    than this module rejecting the whole parse over one missing field."""
    if not isinstance(data.get("class_name", ""), str):
        raise ValueError("invalid class_name")
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

    for field in ("semester_start", "semester_end"):
        value = data.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"invalid {field}")
        if value and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            raise ValueError(f"{field} has a bad date: {value}")

    return data


async def parse_syllabus(semester_name: str, syllabus_text: str) -> Optional[Dict]:
    """Returns the parsed structure (class_name/meeting_times/due_dates/
    exams/semester_start/semester_end/summary, exact shape in
    syllabus-parse.md) or None if Claude's unreachable or the response
    came back malformed -- caller decides how to phrase that, same
    fail-quiet contract as every other ask_claude() consumer here.
    class_name is pulled from the syllabus text itself, not supplied by
    the caller -- most syllabi state the course code/title somewhere, and
    asking the user to retype it when it's already right there is
    unnecessary friction; class_setup_engine.py falls back to asking only
    if this comes back empty. semester_start/semester_end work the same
    way -- pulled from whatever the syllabus itself states about when the
    term runs (an explicit date range, or the first/last dated item in a
    schedule), not asked of the user; semester_name is given only as a
    year/season hint for resolving a bare month/day in the source text."""
    prompt = f"Semester: {semester_name}\n\n{syllabus_text}"

    raw = await ask_claude(
        prompt, model=_PARSE_MODEL, max_tokens=_PARSE_MAX_TOKENS, purpose="syllabus_parse"
    )
    if raw is None:
        return None

    try:
        cleaned = _JSON_FENCE_RE.sub("", raw.strip()).strip()
        return _validate(json.loads(cleaned))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.error(f"syllabus_parser: malformed response: {e}")
        return None
