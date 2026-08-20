"""List/list-item database management and CRUD operations.

Separate from tasks.db's tasks table on purpose: a list (groceries, packing,
reading) is just checkable items with no priority/status/due-date, distinct
from a task. "To-Do" is the default list name when none is specified.
"""

import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_LIST_NAME = "To-Do"


class ListDB:
    """SQLite database for lists and their items."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS lists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    source TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS list_items (
                    id TEXT PRIMARY KEY,
                    list_id TEXT NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    checked INTEGER NOT NULL DEFAULT 0,
                    source TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_list_items_list_id ON list_items(list_id)")
            conn.commit()
            logger.info(f"List database initialized: {self.db_path}")

    def get_or_create_list(self, name: str, source: str = None) -> str:
        """Find a list by name (case-insensitive), creating it if it doesn't exist. Returns list ID."""
        name = name.strip()
        if not name:
            name = DEFAULT_LIST_NAME

        existing = self.get_list_by_name(name)
        if existing:
            return existing["id"]

        list_id = str(uuid.uuid4())[:8]
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO lists (id, name, source) VALUES (?, ?, ?)",
                (list_id, name, source),
            )
            conn.commit()
            logger.info(f"List created: {list_id} - {name}")
        return list_id

    def get_list_by_name(self, name: str) -> Optional[Dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lists WHERE name = ? COLLATE NOCASE", (name.strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_lists(self) -> List[Dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lists ORDER BY name COLLATE NOCASE")
            return [dict(row) for row in cursor.fetchall()]

    def add_item(self, list_id: str, text: str, source: str = None) -> str:
        text = text.strip()
        if not text:
            raise ValueError("Item text cannot be empty")

        item_id = str(uuid.uuid4())[:8]
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO list_items (id, list_id, text, source) VALUES (?, ?, ?, ?)",
                (item_id, list_id, text, source),
            )
            conn.commit()
            logger.info(f"List item added: {item_id} - {text} (list {list_id})")
        return item_id

    def get_items(self, list_id: str, include_checked: bool = True) -> List[Dict]:
        query = "SELECT * FROM list_items WHERE list_id = ?"
        params = [list_id]
        if not include_checked:
            query += " AND checked = 0"
        query += " ORDER BY checked ASC, created_at ASC"

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def find_item(self, list_id: str, text: str) -> List[Dict]:
        """Find items in a list matching text (exact match first, else substring)."""
        items = self.get_items(list_id)
        text_lower = text.strip().lower()

        exact = [i for i in items if i["text"].lower() == text_lower]
        if exact:
            return exact

        return [i for i in items if text_lower in i["text"].lower()]

    def check_item(self, item_id: str, checked: bool = True) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE list_items SET checked = ? WHERE id = ?",
                (1 if checked else 0, item_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def remove_item(self, item_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM list_items WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_list(self, list_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM lists WHERE id = ?", (list_id,))
            conn.commit()
            return cursor.rowcount > 0
