"""Natural-language command parser for lists (no LLM, regex only).

Separate from tasks_parser.py's task commands — a list is just checkable
items with no priority/status/due-date, e.g. "add milk to my grocery list"
vs. "add buy milk to my tasks". "To-Do" is the default list name.
"""

import re
from typing import Dict, List, Optional, Tuple

DEFAULT_LIST_NAME = "To-Do"


class ListCommandParser:
    """Parse list commands: create, add item(s), query, remove item, list all."""

    LIST_ALL_TRIGGERS = [
        re.compile(r'^(?:what|show|list)\s+(?:are\s+)?(?:my\s+)?lists\??$', re.IGNORECASE),
        re.compile(r'^my\s+lists\??$', re.IGNORECASE),
    ]

    CREATE_TRIGGERS = [
        re.compile(r'^(?:create|make|new)\s+(?:a\s+)?list\s+called\s+(.+)$', re.IGNORECASE),
    ]

    # Named ("add X to my Y list") tried before bare ("add X to my list" -> default list).
    ADD_ITEM_NAMED = re.compile(r'^add\s+(.+?)\s+to\s+(?:my\s+)?(.+?)\s+list$', re.IGNORECASE)
    ADD_ITEM_BARE = re.compile(r'^add\s+(.+?)\s+to\s+(?:my\s+)?list$', re.IGNORECASE)

    QUERY_NAMED = [
        re.compile(r"^what(?:'s|s| is| are)\s+on\s+(?:my\s+)?(.+?)\s+list\??$", re.IGNORECASE),
        re.compile(r'^(?:read|show|see|view)\s+(?:my\s+)?(.+?)\s+list$', re.IGNORECASE),
    ]
    QUERY_BARE = [
        re.compile(r"^what(?:'s|s| is| are)\s+on\s+(?:my\s+)?list\??$", re.IGNORECASE),
        re.compile(r'^(?:read|show|see|view)\s+(?:my\s+)?list$', re.IGNORECASE),
    ]

    REMOVE_ITEM_NAMED = re.compile(r'^remove\s+(.+?)\s+from\s+(?:my\s+)?(.+?)\s+list$', re.IGNORECASE)
    REMOVE_ITEM_BARE = re.compile(r'^remove\s+(.+?)\s+from\s+(?:my\s+)?list$', re.IGNORECASE)

    @staticmethod
    def _split_items(text: str) -> List[str]:
        """Split 'milk, eggs, and bread' -> ['milk', 'eggs', 'bread']."""
        text = re.sub(r'\s*,?\s+and\s+', ', ', text, flags=re.IGNORECASE)
        parts = [p.strip().strip('"\'') for p in text.split(',')]
        return [p for p in parts if p]

    @classmethod
    def parse(cls, command: str) -> Optional[Tuple[str, Dict]]:
        """Try every list pattern. Returns (action, data) or None if nothing matched.
        Actions: list_all, create, add_item, query, remove_item."""
        stripped = command.strip()

        for pattern in cls.LIST_ALL_TRIGGERS:
            if pattern.match(stripped):
                return "list_all", {}

        for pattern in cls.CREATE_TRIGGERS:
            match = pattern.match(stripped)
            if match:
                name = match.group(1).strip().strip('"\'')
                if not name:
                    return "create", {"error": "A list needs a name"}
                return "create", {"name": name}

        # Bare checked first — it's a strict, unambiguous match for "no list name
        # given", so it can't be fooled into swallowing "my" as if it were one.
        match = cls.ADD_ITEM_BARE.match(stripped)
        if match:
            items = cls._split_items(match.group(1))
            if not items:
                return "add_item", {"error": "Needs at least one item"}
            return "add_item", {"items": items, "list_name": DEFAULT_LIST_NAME}

        match = cls.ADD_ITEM_NAMED.match(stripped)
        if match:
            items = cls._split_items(match.group(1))
            list_name = match.group(2).strip()
            if not items:
                return "add_item", {"error": "Needs at least one item"}
            return "add_item", {"items": items, "list_name": list_name}

        for pattern in cls.QUERY_BARE:
            if pattern.match(stripped):
                return "query", {"list_name": DEFAULT_LIST_NAME}
        for pattern in cls.QUERY_NAMED:
            match = pattern.match(stripped)
            if match:
                return "query", {"list_name": match.group(1).strip()}

        match = cls.REMOVE_ITEM_BARE.match(stripped)
        if match:
            return "remove_item", {"item_text": match.group(1).strip(), "list_name": DEFAULT_LIST_NAME}
        match = cls.REMOVE_ITEM_NAMED.match(stripped)
        if match:
            return "remove_item", {"item_text": match.group(1).strip(), "list_name": match.group(2).strip()}

        return None
