"""List management engine — combines DB, parsing, and formatting."""

import logging
from typing import Optional, Tuple

from sunny_code.components.lists_db import ListDB
from sunny_code.components.lists_parser import ListCommandParser
from sunny_code.components.request_log import log_unfulfilled

logger = logging.getLogger(__name__)


class ListEngine:
    """High-level list management with command execution."""

    def __init__(self, db: ListDB):
        self.db = db

    def try_execute(self, command: str, source: str = None) -> Tuple[bool, bool, Optional[str]]:
        """Try to parse and execute as a list command.

        Returns (handled, success, message). handled=False means this wasn't
        recognized as a list command at all — the caller should try something else.
        """
        parsed = ListCommandParser.parse(command)
        if parsed is None:
            return False, False, None

        action, data = parsed

        if "error" in data:
            log_unfulfilled("list_command", f'"{command}" — {data["error"]}')
            return True, False, f"{data['error']}"

        if action == "list_all":
            return True, True, self._list_all()
        if action == "create":
            return True, True, self._create(data, source)
        if action == "add_item":
            return True, True, self._add_item(data, source)
        if action == "query":
            return True, True, self._query(data)
        if action == "remove_item":
            success, msg = self._remove_item(data)
            if not success:
                log_unfulfilled("list_command", f'"{command}" — {msg}')
            return True, success, msg

        return True, False, "Unknown list action"

    def _list_all(self) -> str:
        lists = self.db.get_all_lists()
        if not lists:
            return 'You don\'t have any lists yet. Try "create a list called Groceries".'
        lines = []
        for lst in lists:
            items = self.db.get_items(lst["id"])
            unchecked = [i for i in items if not i["checked"]]
            lines.append(f"• {lst['name']} ({len(unchecked)} open, {len(items)} total)")
        return "YOUR LISTS\n" + "\n".join(lines)

    def _create(self, data: dict, source: Optional[str]) -> str:
        existing = self.db.get_list_by_name(data["name"])
        if existing:
            return f'You already have a list called "{existing["name"]}".'
        self.db.get_or_create_list(data["name"], source=source)
        return f'Created list "{data["name"]}"'

    def _add_item(self, data: dict, source: Optional[str]) -> str:
        list_id = self.db.get_or_create_list(data["list_name"], source=source)
        list_row = self.db.get_list_by_name(data["list_name"]) or {"name": data["list_name"]}

        for item in data["items"]:
            self.db.add_item(list_id, item, source=source)

        items = data["items"]
        if len(items) == 1:
            return f'Added "{items[0]}" to {list_row["name"]}'
        joined = ", ".join(items)
        return f'Added {len(items)} items to {list_row["name"]}: {joined}'

    def _query(self, data: dict) -> str:
        list_row = self.db.get_list_by_name(data["list_name"])
        if not list_row:
            return f'No list called "{data["list_name"]}" yet — add something to it to create it.'

        items = self.db.get_items(list_row["id"])
        if not items:
            return f"{list_row['name']} (empty)"

        lines = [f"{'' if i['checked'] else ''} {i['text']}" for i in items]
        open_count = sum(1 for i in items if not i["checked"])
        return f"{list_row['name']} ({open_count} open, {len(items)} total)\n" + "\n".join(lines)

    def _remove_item(self, data: dict) -> Tuple[bool, str]:
        list_row = self.db.get_list_by_name(data["list_name"])
        if not list_row:
            return False, f'No list called "{data["list_name"]}"'

        matches = self.db.find_item(list_row["id"], data["item_text"])
        if not matches:
            return False, f'"{data["item_text"]}" isn\'t on {list_row["name"]}'
        if len(matches) > 1:
            texts = ", ".join(f'"{m["text"]}"' for m in matches[:5])
            return False, f'That matches multiple items: {texts} — try the exact text'

        self.db.remove_item(matches[0]["id"])
        return True, f'Removed "{matches[0]["text"]}" from {list_row["name"]}'
