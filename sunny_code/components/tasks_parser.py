"""Hardcoded command parser for task management (no LLM).

Two input styles are understood, both fully deterministic (regex only):
- Natural phrasing (primary): "add buy milk to my tasks", "show my tasks",
  "mark a1b2c3d4 as done", "delete a1b2c3d4"
- Legacy `!task`/`!tasks` syntax (still works, no longer required or shown
  in the UI/docs): "!task add "buy milk" --tag School", "!tasks --tag School"

Tasks have no priority field (removed 2026-08-24, was a plain 1-5 int with
no real behavior tied to it beyond dashboard sort order) -- category and
due date are the only real organizing fields left.
"""

import re
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TaskCommandParser:
    """Parse task commands — natural phrasing or the legacy !task syntax."""

    # Legacy `!task` / `!tasks` patterns
    TASK_ADD_PATTERN = r'!task\s+add\s+"([^"]+)"(.*)'  # !task add "title" --flags
    TASK_UPDATE_PATTERN = r'!task\s+(\w+)\s+(\w+)\s+(.*)'  # !task id field value
    TASK_DELETE_PATTERN = r'!task\s+(\w+)\s+delete'  # !task id delete
    TASK_LIST_PATTERN = r'!tasks?(?:\s+(.*))?'  # !tasks [filters]

    # Sub-patterns for extracting flags (shared by legacy and natural add/list)
    TAG_PATTERN = r'--tag\s+(["\']?)([^"\'\s]+)\1'
    DUE_PATTERN = r'--due\s+([\d\-]+)'  # YYYY-MM-DD
    DESCRIPTION_PATTERN = r'--describe\s+(["\']?)(.+?)\1(?:\s--|$)'

    # Natural-language triggers — order matters, first match wins, so the specific
    # "X to my tasks" / "task: X" phrasings are tried before the bare "add X" catch-all.
    NATURAL_ADD_TRIGGERS = [
        # "to my task list" / "to my tasks" (explicit) is a task; bare "to my
        # list"/"to my X list" belongs to the separate Lists feature (see
        # lists_parser.py) now that it's a real thing, not just a synonym
        # for tasks. The leading "add" is optional here (or one of its
        # confirmed real speech-to-text mishearings, "i'd"/"id" — heard
        # live via /join, 2026-08-21: Vosk transcribed "add make pizza to
        # my tasks" as "i'd make pizza to my tasks", which the old
        # ^add-anchored pattern silently failed to recognize at all).
        # The trailing "to my task(s)" is the reliable anchor here, not
        # the leading word, which speech-to-text is far more likely to
        # garble — a short word like "add" has few phonemes to distinguish
        # it by. If the leading word is missing or isn't a recognized
        # variant, it just becomes (harmless) extra text at the front of
        # the title instead of failing the match outright.
        re.compile(r'^(?:add\s+|i\'?d\s+|id\s+)?(.+?)\s+to\s+(?:my\s+)?task\s+list$', re.IGNORECASE),
        re.compile(r'^(?:add\s+|i\'?d\s+|id\s+)?(.+?)\s+to\s+(?:my\s+)?tasks?$', re.IGNORECASE),
        # "put X on my tasks" — a real, natural alternative to "add X to my
        # tasks" that isn't just a rephrasing of an already-covered pattern.
        re.compile(r'^put\s+(.+?)\s+on\s+(?:my\s+)?tasks?$', re.IGNORECASE),
        # "add/create/make/new (a/an/me a) (new) task [title]" — title is optional
        # (`.*` not `.+`), so a bare "make a new task" is a valid empty-title
        # match too, which is what lets the assistant ask a follow-up for it.
        # No trailing anchor to fall back on here, so the leading verb stays
        # required — "make"/"create"/"new" are common enough words that
        # making them optional would risk swallowing unrelated sentences.
        re.compile(r'^(?:add|create|make|new)\s+(?:a\s+|an\s+|me\s+a\s+)?(?:new\s+)?task[:\s]*(.*)$', re.IGNORECASE),
        re.compile(r'^add\s+(.+)$', re.IGNORECASE),  # bare "add X" catch-all
    ]
    # Tried before NATURAL_ADD_TRIGGERS (see parse_natural_add) — same
    # leading-word tolerance as the plain "to my tasks" pattern above, but
    # captures a second group for an inline category word ("...to my school
    # tasks"). Only actually used as a category if it matches something in
    # the live category list (case-insensitive) — parse_natural_add falls
    # through to the plain trigger list otherwise, so an ordinary title
    # that happens to end in "to my <word> tasks" is never misparsed.
    NATURAL_ADD_WITH_CATEGORY = re.compile(
        r'^(?:add\s+|i\'?d\s+|id\s+)?(.+?)\s+to\s+(?:my\s+)?(\w+)\s+tasks?$', re.IGNORECASE
    )
    NATURAL_LIST_PATTERN = re.compile(
        r'^(?:show|list|see|view)\s+(?:my\s+)?tasks?$'
        r'|^what(?:\'s|s| is| are)\s+(?:on\s+)?my\s+tasks?\??$'
        r'|^my\s+tasks?$'
        r'|^tasks?$',
        re.IGNORECASE,
    )
    # Capture group is the raw identifier — a task ID or a title (possibly multi-word
    # or quoted). TaskEngine resolves it: exact ID match first, then title match.
    NATURAL_DONE_PATTERN = re.compile(
        r'^(?:mark|set)\s+(.+?)\s+(?:as\s+)?done$'
        r'|^(?:complete|finish)\s+(.+)$'
        # "cross off my X task" — a real, natural way to say "mark X done"
        # (crossing an item off a physical list), heard live via /join,
        # 2026-08-21, and not recognized by any pattern above. Trailing
        # " task" is stripped if present so the extracted identifier
        # matches cleanly against the stored title either way. "check off
        # my X task" is the same idea, different verb.
        r'|^(?:cross|check)\s+off\s+(?:my\s+)?(.+?)(?:\s+task)?$',
        re.IGNORECASE,
    )
    NATURAL_DELETE_PATTERN = re.compile(
        r'^(?:delete|remove)\s+(.+?)(?:\s+from\s+(?:my\s+)?tasks?)?$',
        re.IGNORECASE,
    )

    @staticmethod
    def _split_flags(text: str) -> Tuple[str, str]:
        """Split 'phrase --tag X --due 2026-08-20' into ('phrase', '--tag X --due 2026-08-20')."""
        idx = text.find(' --')
        if idx == -1:
            return text.strip(), ""
        return text[:idx].strip(), text[idx + 1:].strip()

    @staticmethod
    def _fields_from_flags(flags: str) -> Dict:
        """Extract tag/due/description from a --flag string. Shared by add paths.
        "tag" is only present if --tag was actually given -- no default here, so a caller
        (parse_natural_add) can tell "no category stated" apart from "General was chosen"
        and ask instead of silently guessing. parse_add_command (the legacy !task syntax)
        applies its own "General" default after calling this, since that path has no
        interactive follow-up to ask through."""
        result = {}

        tag_match = re.search(TaskCommandParser.TAG_PATTERN, flags)
        if tag_match:
            result["tag"] = tag_match.group(2)

        due_match = re.search(TaskCommandParser.DUE_PATTERN, flags)
        if due_match:
            result["due_date"] = due_match.group(1)

        desc_match = re.search(TaskCommandParser.DESCRIPTION_PATTERN, flags)
        if desc_match:
            result["description"] = desc_match.group(2)

        return result

    @staticmethod
    def _filters_from_flags(flags: str) -> Dict:
        """Extract status/tag filters from a --flag string. Shared by list paths."""
        result = {}

        status_match = re.search(r"--status\s+(\w+)", flags)
        if status_match:
            result["status"] = status_match.group(1)

        tag_match = re.search(r"--tag\s+([^\s]+)", flags)
        if tag_match:
            result["tag"] = tag_match.group(1)

        if "--due-soon" in flags:
            result["due_soon"] = True
        if "--all" in flags:
            result["all"] = True
        if "--done" in flags:
            result["status"] = "done"
        if "--open" in flags:
            result["status"] = "open"
        if "--in-progress" in flags:
            result["status"] = "in_progress"

        return result

    @staticmethod
    def parse_add_command(command: str) -> Tuple[bool, Dict]:
        """Parse: !task add "Title" --tag School --due 2026-08-20"""
        match = re.match(TaskCommandParser.TASK_ADD_PATTERN, command)
        if not match:
            return False, {"error": "Invalid add command format"}

        title = match.group(1)
        flags = match.group(2)

        result = {"title": title}
        result.update(TaskCommandParser._fields_from_flags(flags))
        result.setdefault("tag", "General")
        return True, result

    @staticmethod
    def parse_natural_add(
        command: str, known_categories: Optional[List[str]] = None
    ) -> Optional[Tuple[bool, Dict]]:
        """Parse: "add buy milk to my tasks --due 2026-08-20" or "add buy milk
        to my school tasks". known_categories, if given, lets an inline "to my
        <category> tasks" phrasing set the category directly; if that word
        isn't one of the known ones (or no list was passed at all), this
        falls through to the plain trigger list below and "tag" is left for
        the caller (assistant.py) to ask about instead of guessing.

        result never has a default "tag" -- see _fields_from_flags."""
        phrase, flags = TaskCommandParser._split_flags(command)

        if known_categories:
            cat_match = TaskCommandParser.NATURAL_ADD_WITH_CATEGORY.match(phrase)
            if cat_match:
                title = cat_match.group(1).strip().strip('"\'')
                category_word = cat_match.group(2).strip()
                matched = next((c for c in known_categories if c.lower() == category_word.lower()), None)
                if matched and title:
                    result = {"title": title, "tag": matched}
                    # Applied after the inline-category default so an explicit
                    # --tag flag (rare in the same phrase, but possible) wins.
                    result.update(TaskCommandParser._fields_from_flags(flags))
                    return True, result

        for trigger in TaskCommandParser.NATURAL_ADD_TRIGGERS:
            match = trigger.match(phrase)
            if not match:
                continue

            title = match.group(1).strip().strip('"\'')
            if not title:
                return False, {"error": 'Task needs a title — try "add buy milk to my tasks"'}

            result = {"title": title}
            result.update(TaskCommandParser._fields_from_flags(flags))
            return True, result

        return None

    @staticmethod
    def parse_update_command(command: str) -> Tuple[bool, Dict]:
        """Parse: !task abc123 status done OR !task abc123 tag School"""
        match = re.match(TaskCommandParser.TASK_UPDATE_PATTERN, command)
        if not match:
            return False, {"error": "Invalid update command format"}

        task_id = match.group(1)
        field = match.group(2).lower()
        value = match.group(3).strip()
        return TaskCommandParser._validate_update(task_id, field, value)

    @staticmethod
    def _validate_update(task_id: str, field: str, value: str) -> Tuple[bool, Dict]:
        valid_fields = {"status", "tag", "title", "describe", "due"}
        if field not in valid_fields:
            return False, {"error": f"Invalid field: {field}. Valid: {valid_fields}"}

        result = {"task_id": task_id, "field": field}

        if field == "status":
            if value not in {"open", "in_progress", "done"}:
                return False, {"error": "Status must be: open, in_progress, or done"}
            result["value"] = value
        elif field == "tag":
            if not value.strip():
                return False, {"error": "Category cannot be empty"}
            result["value"] = value.strip()
        elif field == "due":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                return False, {"error": "Date format: YYYY-MM-DD"}
            result["value"] = value
        else:  # title or describe
            result["value"] = value

        return True, result

    @staticmethod
    def parse_delete_command(command: str) -> Tuple[bool, Dict]:
        """Parse: !task abc123 delete"""
        match = re.match(TaskCommandParser.TASK_DELETE_PATTERN, command)
        if not match:
            return False, {"error": "Invalid delete command format"}

        task_id = match.group(1)
        return True, {"task_id": task_id}

    @staticmethod
    def parse_list_command(command: str) -> Tuple[bool, Dict]:
        """Parse: !tasks [--status open] [--tag School] [--due-soon]"""
        match = re.match(TaskCommandParser.TASK_LIST_PATTERN, command)
        if not match:
            return False, {"error": "Invalid list command"}

        flags = match.group(1) or ""
        return True, TaskCommandParser._filters_from_flags(flags)

    @staticmethod
    def parse_natural_command(
        command: str, known_categories: Optional[List[str]] = None
    ) -> Optional[Tuple[str, bool, Dict]]:
        """Try every natural-language pattern. Returns None if nothing matches."""
        stripped = command.strip()
        phrase, _ = TaskCommandParser._split_flags(stripped)

        add_result = TaskCommandParser.parse_natural_add(stripped, known_categories)
        if add_result is not None:
            success, data = add_result
            return "add", success, data

        if TaskCommandParser.NATURAL_LIST_PATTERN.match(phrase):
            _, flags = TaskCommandParser._split_flags(stripped)
            return "list", True, TaskCommandParser._filters_from_flags(flags)

        match = TaskCommandParser.NATURAL_DONE_PATTERN.match(phrase)
        if match:
            task_id = next(g for g in match.groups() if g)
            return "update", True, {"task_id": task_id, "field": "status", "value": "done"}

        match = TaskCommandParser.NATURAL_DELETE_PATTERN.match(phrase)
        if match:
            return "delete", True, {"task_id": match.group(1)}

        return None

    @staticmethod
    def parse_command(command: str, known_categories: Optional[List[str]] = None) -> Tuple[str, bool, Dict]:
        """
        Parse any task command (natural phrasing or legacy !task syntax) and
        return (command_type, success, data). Command types: add, update, delete, list, unknown

        known_categories is only used for natural "add" phrasing that names a
        category inline (e.g. "...to my school tasks") — see parse_natural_add.
        """
        command = command.strip()

        # Legacy `!task` / `!tasks` syntax — still works, just not advertised
        if command.startswith("!task add"):
            success, data = TaskCommandParser.parse_add_command(command)
            return "add", success, data
        elif re.match(TaskCommandParser.TASK_DELETE_PATTERN, command):
            success, data = TaskCommandParser.parse_delete_command(command)
            return "delete", success, data
        elif re.match(TaskCommandParser.TASK_UPDATE_PATTERN, command):
            success, data = TaskCommandParser.parse_update_command(command)
            return "update", success, data
        elif command.startswith("!tasks") or command.startswith("!task"):
            success, data = TaskCommandParser.parse_list_command(command)
            return "list", success, data

        # Natural phrasing — the primary, documented way to talk to the task system
        natural = TaskCommandParser.parse_natural_command(command, known_categories)
        if natural is not None:
            return natural

        return "unknown", False, {"error": f"Unknown command: {command}"}
