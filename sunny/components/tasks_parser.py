"""Hardcoded command parser for task management (no LLM).

Two input styles are understood, both fully deterministic (regex only):
- Natural phrasing (primary): "add buy milk to my tasks", "show my tasks",
  "mark a1b2c3d4 as done", "delete a1b2c3d4"
- Legacy `!task`/`!tasks` syntax (still works, no longer required or shown
  in the UI/docs): "!task add "buy milk" --priority 4", "!tasks --tag School"
"""

import re
from datetime import datetime
from typing import Dict, Optional, Tuple
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
    PRIORITY_PATTERN = r'--priority\s+([1-5])'
    DUE_PATTERN = r'--due\s+([\d\-]+)'  # YYYY-MM-DD
    DESCRIPTION_PATTERN = r'--describe\s+(["\']?)(.+?)\1(?:\s--|$)'

    # Natural-language triggers
    NATURAL_ADD_TRIGGERS = [
        re.compile(r'^add\s+(.+?)\s+to\s+(?:my\s+)?(?:task\s+)?list$', re.IGNORECASE),
        re.compile(r'^add\s+(.+?)\s+to\s+(?:my\s+)?tasks?$', re.IGNORECASE),
        re.compile(r'^add\s+task[:\s]+(.+)$', re.IGNORECASE),
        re.compile(r'^(?:create|new)\s+task[:\s]+(.+)$', re.IGNORECASE),
        re.compile(r'^remind\s+me\s+to\s+(.+)$', re.IGNORECASE),
    ]
    NATURAL_LIST_PATTERN = re.compile(
        r'^(?:show|list|see|view)\s+(?:my\s+)?tasks?$'
        r'|^what(?:\'s|s| is| are)\s+(?:on\s+)?my\s+tasks?\??$'
        r'|^my\s+tasks?$'
        r'|^tasks?$',
        re.IGNORECASE,
    )
    NATURAL_DONE_PATTERN = re.compile(
        r'^(?:mark|set)\s+(\w+)\s+(?:as\s+)?done$'
        r'|^(?:complete|finish)\s+(\w+)$',
        re.IGNORECASE,
    )
    NATURAL_DELETE_PATTERN = re.compile(
        r'^(?:delete|remove)\s+(\w+)(?:\s+from\s+(?:my\s+)?tasks?)?$',
        re.IGNORECASE,
    )

    @staticmethod
    def _split_flags(text: str) -> Tuple[str, str]:
        """Split 'phrase --tag X --priority 2' into ('phrase', '--tag X --priority 2')."""
        idx = text.find(' --')
        if idx == -1:
            return text.strip(), ""
        return text[:idx].strip(), text[idx + 1:].strip()

    @staticmethod
    def _fields_from_flags(flags: str) -> Dict:
        """Extract tag/priority/due/description from a --flag string. Shared by add paths."""
        result = {}

        tag_match = re.search(TaskCommandParser.TAG_PATTERN, flags)
        result["tag"] = tag_match.group(2) if tag_match else "General"

        priority_match = re.search(TaskCommandParser.PRIORITY_PATTERN, flags)
        result["priority"] = int(priority_match.group(1)) if priority_match else 3

        due_match = re.search(TaskCommandParser.DUE_PATTERN, flags)
        if due_match:
            result["due_date"] = due_match.group(1)

        desc_match = re.search(TaskCommandParser.DESCRIPTION_PATTERN, flags)
        if desc_match:
            result["description"] = desc_match.group(2)

        return result

    @staticmethod
    def _filters_from_flags(flags: str) -> Dict:
        """Extract status/tag/priority filters from a --flag string. Shared by list paths."""
        result = {}

        status_match = re.search(r"--status\s+(\w+)", flags)
        if status_match:
            result["status"] = status_match.group(1)

        tag_match = re.search(r"--tag\s+([^\s]+)", flags)
        if tag_match:
            result["tag"] = tag_match.group(1)

        priority_match = re.search(r"--priority\s+([1-5])", flags)
        if priority_match:
            result["min_priority"] = int(priority_match.group(1))

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
        """Parse: !task add "Title" --tag School --priority 4 --due 2026-08-20"""
        match = re.match(TaskCommandParser.TASK_ADD_PATTERN, command)
        if not match:
            return False, {"error": "Invalid add command format"}

        title = match.group(1)
        flags = match.group(2)

        result = {"title": title}
        result.update(TaskCommandParser._fields_from_flags(flags))
        return True, result

    @staticmethod
    def parse_natural_add(command: str) -> Optional[Tuple[bool, Dict]]:
        """Parse: "add buy milk to my tasks --priority 4" or "remind me to buy milk"."""
        phrase, flags = TaskCommandParser._split_flags(command)

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
        """Parse: !task abc123 status done OR !task abc123 priority 5"""
        match = re.match(TaskCommandParser.TASK_UPDATE_PATTERN, command)
        if not match:
            return False, {"error": "Invalid update command format"}

        task_id = match.group(1)
        field = match.group(2).lower()
        value = match.group(3).strip()
        return TaskCommandParser._validate_update(task_id, field, value)

    @staticmethod
    def _validate_update(task_id: str, field: str, value: str) -> Tuple[bool, Dict]:
        valid_fields = {"status", "priority", "tag", "title", "describe", "due"}
        if field not in valid_fields:
            return False, {"error": f"Invalid field: {field}. Valid: {valid_fields}"}

        result = {"task_id": task_id, "field": field}

        if field == "priority":
            if not re.match(r"^[1-5]$", value):
                return False, {"error": "Priority must be 1-5"}
            result["value"] = int(value)
        elif field == "status":
            if value not in {"open", "in_progress", "done"}:
                return False, {"error": "Status must be: open, in_progress, or done"}
            result["value"] = value
        elif field == "tag":
            if value not in {"School", "Motorsports", "General", "Project Ideas"}:
                return False, {"error": f"Invalid tag: {value}"}
            result["value"] = value
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
        """Parse: !tasks [--status open] [--tag School] [--priority 4] [--due-soon]"""
        match = re.match(TaskCommandParser.TASK_LIST_PATTERN, command)
        if not match:
            return False, {"error": "Invalid list command"}

        flags = match.group(1) or ""
        return True, TaskCommandParser._filters_from_flags(flags)

    @staticmethod
    def parse_natural_command(command: str) -> Optional[Tuple[str, bool, Dict]]:
        """Try every natural-language pattern. Returns None if nothing matches."""
        stripped = command.strip()
        phrase, _ = TaskCommandParser._split_flags(stripped)

        add_result = TaskCommandParser.parse_natural_add(stripped)
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
    def parse_command(command: str) -> Tuple[str, bool, Dict]:
        """
        Parse any task command (natural phrasing or legacy !task syntax) and
        return (command_type, success, data). Command types: add, update, delete, list, unknown
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
        natural = TaskCommandParser.parse_natural_command(command)
        if natural is not None:
            return natural

        return "unknown", False, {"error": f"Unknown command: {command}"}
