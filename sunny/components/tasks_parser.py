"""Hardcoded command parser for task management (no LLM)."""

import re
from datetime import datetime
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class TaskCommandParser:
    """Parse Discord-style task commands with regex patterns."""

    # Regex patterns for command parsing
    TASK_ADD_PATTERN = r'!task\s+add\s+"([^"]+)"(.*)'  # !task add "title" --flags
    TASK_UPDATE_PATTERN = r'!task\s+(\w+)\s+(\w+)\s+(.*)'  # !task id field value
    TASK_DELETE_PATTERN = r'!task\s+(\w+)\s+delete'  # !task id delete
    TASK_LIST_PATTERN = r'!tasks?(?:\s+(.*))?'  # !tasks [filters]

    # Sub-patterns for extracting flags
    TAG_PATTERN = r'--tag\s+(["\']?)([^"\'\s]+)\1'
    PRIORITY_PATTERN = r'--priority\s+([1-5])'
    DUE_PATTERN = r'--due\s+([\d\-]+)'  # YYYY-MM-DD
    DESCRIPTION_PATTERN = r'--describe\s+(["\']?)(.+?)\1(?:\s--|$)'

    @staticmethod
    def parse_add_command(command: str) -> Tuple[bool, Dict]:
        """Parse: !task add "Title" --tag School --priority 4 --due 2026-08-20"""
        match = re.match(TaskCommandParser.TASK_ADD_PATTERN, command)
        if not match:
            return False, {"error": "Invalid add command format"}

        title = match.group(1)
        flags = match.group(2)

        result = {"title": title}

        # Extract tag
        tag_match = re.search(TaskCommandParser.TAG_PATTERN, flags)
        if tag_match:
            result["tag"] = tag_match.group(2)
        else:
            result["tag"] = "General"  # Default tag

        # Extract priority
        priority_match = re.search(TaskCommandParser.PRIORITY_PATTERN, flags)
        if priority_match:
            result["priority"] = int(priority_match.group(1))
        else:
            result["priority"] = 3  # Default priority

        # Extract due date
        due_match = re.search(TaskCommandParser.DUE_PATTERN, flags)
        if due_match:
            result["due_date"] = due_match.group(1)

        # Extract description
        desc_match = re.search(TaskCommandParser.DESCRIPTION_PATTERN, flags)
        if desc_match:
            result["description"] = desc_match.group(2)

        return True, result

    @staticmethod
    def parse_update_command(command: str) -> Tuple[bool, Dict]:
        """Parse: !task abc123 status done OR !task abc123 priority 5"""
        match = re.match(TaskCommandParser.TASK_UPDATE_PATTERN, command)
        if not match:
            return False, {"error": "Invalid update command format"}

        task_id = match.group(1)
        field = match.group(2).lower()
        value = match.group(3).strip()

        valid_fields = {"status", "priority", "tag", "title", "describe", "due"}
        if field not in valid_fields:
            return False, {"error": f"Invalid field: {field}. Valid: {valid_fields}"}

        result = {"task_id": task_id, "field": field}

        # Parse value based on field
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
        result = {}

        # Extract filters
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

        return True, result

    @staticmethod
    def parse_command(command: str) -> Tuple[str, bool, Dict]:
        """
        Parse any task command and return (command_type, success, data).
        Command types: add, update, delete, list, unknown
        """
        command = command.strip()

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
        else:
            return "unknown", False, {"error": f"Unknown command: {command}"}
