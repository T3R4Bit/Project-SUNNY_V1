"""One structured extraction, three callers.

"quiz 3 in physics due friday" should become a task, a due date, a
category and a calendar entry in one turn, with no wizard and no
follow-up questions when the answer is obvious. That is the whole point
of this module: capture speed. Every question Sunny asks after the fact
is a place where the thought gets dropped.

THREE CALLERS, ONE CALL
-----------------------
Assignment capture, reminders, and category inference were three separate
parsing problems in three places. They are the same problem: read a
scrap of natural language, return typed fields, say how sure you are.
Splitting them meant three prompts to keep in sync and three different
answers to "what date is 'friday'".

WHY THE CATEGORY IS AN ENUM IN THE SCHEMA
-----------------------------------------
`_finish_task_with_category` accepted any string, so a typo silently
created a phantom category that then showed up in menus forever. The
usual fix is to validate the model's answer afterwards and re-ask on a
miss. Constraining the schema is better: the category list becomes an
`enum`, the server will not generate a value outside it, and a phantom
category stops being something that can be *represented* rather than
something that gets caught. Validation still runs below, because a
schema is a promise about the model and not about the network.

CONFIDENCE IS THE POINT, NOT A DECORATION
-----------------------------------------
The model reports confidence per-field, and the caller decides. Above
AUTO_FILE_THRESHOLD Sunny files it and says which category it picked, so
a wrong guess is visible and correctable in one reply. Below it, Sunny
asks — but asks ONE question about the specific uncertain field, rather
than restarting the wizard that this module exists to delete.

Never raises. Returns None when there was nothing to extract or the LLM
path was unavailable, and every caller keeps its existing regex fast
path in front of this (see scheduled_parser.py) — extraction is the
fallback for what the regex cannot read, not a replacement for it.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sunny_code.components import category_store, day_boundary, llm_client

logger = logging.getLogger(__name__)

# Above this, file it and report what was chosen. Below, ask about the
# one field that was uncertain. 0.85 is deliberately high: the cost of
# asking a needless question is one extra line, and the cost of silently
# filing an assignment under the wrong class is a missed deadline.
AUTO_FILE_THRESHOLD = 0.85

# What the text turned out to be. "none" matters as much as the rest --
# without it, "thanks!" becomes a task called "thanks".
KINDS = ["assignment", "task", "reminder", "event", "none"]


def _schema(categories: List[str]) -> Dict[str, Any]:
    """The JSON schema for one captured item.

    Built per-call rather than defined as a constant because the category
    enum has to reflect the category list as it is right now -- a category
    added five minutes ago must be selectable, and a deleted one must not.
    """
    return {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": KINDS,
                "description": "What this text is. 'none' if it is not a capturable item at all.",
            },
            "title": {
                "type": "string",
                "description": "Short imperative title, no date words. '' when kind is none.",
            },
            "due_date": {
                "type": ["string", "null"],
                "description": "YYYY-MM-DD, resolved from relative words. null if no date was given.",
            },
            "due_time": {
                "type": ["string", "null"],
                "description": "HH:MM 24-hour. null unless a specific time was actually stated.",
            },
            "category": {
                "type": "string",
                "enum": categories,
                "description": "Best-fitting existing category. Never invent one.",
            },
            "category_confidence": {
                "type": "number",
                "description": (
                    "0.0-1.0 that this is the right category. High when the text clearly "
                    "belongs to one, AND high when nothing specific fits and the general "
                    "catch-all is therefore correct. Low only when two categories genuinely "
                    "compete and picking wrong would misfile it."
                ),
            },
            "class_name": {
                "type": ["string", "null"],
                "description": "Course name if one was named or clearly implied, else null.",
            },
            "notes": {
                "type": ["string", "null"],
                "description": "Anything specific worth keeping that the title drops, else null.",
            },
            "confidence": {
                "type": "number",
                "description": (
                    "0.0-1.0 that the kind and title are right. Judge only what was "
                    "stated, never how much was stated: a task with no date is not an "
                    "uncertain task. Low only when the text is genuinely ambiguous "
                    "about what is being asked for."
                ),
            },
        },
        "required": [
            "kind", "title", "due_date", "due_time", "category",
            "category_confidence", "class_name", "notes", "confidence",
        ],
        "additionalProperties": False,
    }


# Kept in code rather than sunny-vault/docs/instructions/ like other
# prompts, because this one is coupled to the schema above -- the two have
# to change together, and a hand-edit that drifts from the field list
# produces confidently wrong output rather than an obvious error. The
# personality file deliberately does not reach here either; see
# llm_client.ask_claude_json.
_SYSTEM = """You turn short scraps of natural language into one structured item.

Rules that matter:
- Resolve every relative date ("friday", "tomorrow", "next week") against the
  reference date given in the message. Never return a relative word.
- A bare weekday means the NEXT occurrence of that weekday, not one in the past.
- Only set due_time when a time was actually stated. Do not invent 9am.
- title is what the user would want to read in a list: no "remind me to",
  no trailing "due"/"by", no date words, no filler. "english essay draft due
  next tuesday" has the title "English essay draft".
- Pick the closest existing category. Where nothing specific fits, the most
  general category IS the right answer, not a fallback -- say so with high
  category_confidence rather than hedging.
- kind "none" for greetings, questions, chatter, or anything that is not a
  thing to do. Return empty title and low confidence in that case.

On confidence, which decides whether this gets filed silently or the user
gets interrupted with a question: report how sure you are that you read the
text CORRECTLY, not how much the text contained. "buy milk" is a complete
and unambiguous task and deserves high confidence despite naming no date,
no project and no detail. Reserve low numbers for real ambiguity -- text
that could reasonably mean two different things. Needless questions are the
specific failure this is meant to prevent; a guess reported as certain is
the other one."""


def _reference_block(today: date) -> str:
    """The date context the model resolves relative words against.

    Deliberately part of the user message rather than the system prompt:
    it changes every day, and anything volatile in a system prefix
    invalidates prompt caching for every call after it.

    `today` is the LOGGING day, not the wall clock date -- so at 2am on
    the 23rd, "today" is still the 22nd and "tomorrow" is the 23rd. That
    matches day_boundary's 5am rule and how someone up at 2am actually
    talks; using the calendar date here would have "tomorrow" silently
    mean two different things depending on the hour.
    """
    lines = [f"Reference date (treat as today): {today.isoformat()} ({today.strftime('%A')})"]
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        lines.append(f"  {day.strftime('%A')} = {day.isoformat()}")
    return "\n".join(lines)


def _valid_date(value: Optional[str]) -> Optional[str]:
    """An ISO date string, or None. The schema constrains the field's TYPE
    but not that the string is a real date -- "2026-02-31" satisfies
    {"type": "string"} perfectly well and would land in a calendar call as
    a crash rather than a bad guess."""
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        logger.warning(f"extract: discarding unparseable due_date {value!r}")
        return None


def _valid_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except (TypeError, ValueError):
        logger.warning(f"extract: discarding unparseable due_time {value!r}")
        return None


async def capture(text: str, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Extract one item from `text`, or None.

    None means "nothing to file here" and covers every failure mode the
    caller should treat identically: empty input, the LLM path being
    unavailable or over budget, and the model reading the text as not a
    capturable item at all. A caller that wants to distinguish those
    should check llm_client's own state, not this return value.

    The returned dict is the schema above with due_date/due_time
    validated, plus `auto_file` -- whether both confidences cleared
    AUTO_FILE_THRESHOLD -- and `uncertain`, naming the fields that did
    not, so a caller can ask about exactly one thing.
    """
    text = (text or "").strip()
    if not text:
        return None

    today = today or day_boundary.logging_day()
    categories = category_store.get_categories()
    if not categories:
        # Defensive: get_categories() seeds itself, so this needs a
        # corrupted file AND a failed reseed. An empty enum would be an
        # API error rather than a bad answer, so fail the soft way.
        logger.error("extract: no categories available, skipping extraction")
        return None

    prompt = f"{_reference_block(today)}\n\nText to capture:\n{text}"

    result = await llm_client.ask_claude_json(
        prompt=prompt,
        schema=_schema(categories),
        system=_SYSTEM,
        purpose="extract",
        max_tokens=512,
    )
    if result is None:
        return None

    if result.get("kind") == "none":
        logger.debug(f"extract: {text!r} read as not a capturable item")
        return None

    result["due_date"] = _valid_date(result.get("due_date"))
    result["due_time"] = _valid_time(result.get("due_time"))

    # The enum should make this impossible. Checked anyway -- this is the
    # exact bug the enum exists to kill, and a silent phantom category is
    # precisely the failure that went unnoticed long enough to reach the
    # roadmap.
    if result.get("category") not in categories:
        logger.error(f"extract: model returned off-enum category {result.get('category')!r}")
        result["category"] = categories[0]
        result["category_confidence"] = 0.0

    uncertain = []
    if float(result.get("confidence") or 0) < AUTO_FILE_THRESHOLD:
        uncertain.append("reading")
    if float(result.get("category_confidence") or 0) < AUTO_FILE_THRESHOLD:
        uncertain.append("category")

    result["uncertain"] = uncertain
    result["auto_file"] = not uncertain
    return result


def describe(result: Dict[str, Any]) -> str:
    """One line a human can check at a glance.

    Exists so every caller reports a filed item the same way. When Sunny
    files something automatically, the user needs to see what it decided
    without opening anything -- that readback is what makes auto-filing
    safe to do at all.
    """
    parts = [result.get("title") or "(untitled)"]

    due = result.get("due_date")
    if due:
        when = date.fromisoformat(due).strftime("%a %b ") + str(date.fromisoformat(due).day)
        if result.get("due_time"):
            when += f" {result['due_time']}"
        parts.append(f"due {when}")

    parts.append(f"#{result.get('category')}")
    if result.get("class_name"):
        parts.append(str(result["class_name"]))

    return " · ".join(parts)
