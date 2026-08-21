"""Storage for alarms and reminders — unified as one "scheduled item" table since
they're structurally the same (a label, a trigger time, optional recurrence),
just with different delivery framing (alarm = wake up, reminder = don't forget).

No hardware exists yet to actually sound an alarm, so delivery is a Discord ping
when the bot is connected (see discord_bot.py's scheduled-items loop) — this is
storage + query/cancel only; nothing here "sounds" anything by itself.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

from sunny_code.components.db_connection import closing_transaction

logger = logging.getLogger(__name__)


class ScheduledDB:
    """SQLite database for alarms and reminders."""

    VALID_KINDS = {"alarm", "reminder"}

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_items (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('alarm', 'reminder')),
                    label TEXT NOT NULL,
                    trigger_at DATETIME NOT NULL,
                    recurrence TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    source TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_active ON scheduled_items(active, trigger_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_kind ON scheduled_items(kind)")
            conn.commit()
            logger.info(f"Scheduled-items database initialized: {self.db_path}")

    def create_item(
        self,
        kind: str,
        label: str,
        trigger_at: datetime,
        recurrence: str = None,
        source: str = None,
    ) -> str:
        if kind not in self.VALID_KINDS:
            raise ValueError(f"Invalid kind: {kind}")
        if not label or not label.strip():
            raise ValueError("Label cannot be empty")

        item_id = str(uuid.uuid4())[:8]
        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scheduled_items (id, kind, label, trigger_at, recurrence, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (item_id, kind, label.strip(), trigger_at.isoformat(), recurrence, source),
            )
            conn.commit()
            logger.info(f"{kind.capitalize()} created: {item_id} - {label} at {trigger_at.isoformat()}")
        return item_id

    def get_item(self, item_id: str) -> Optional[Dict]:
        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_active_items(self, kind: str = None) -> List[Dict]:
        query = "SELECT * FROM scheduled_items WHERE active = 1"
        params = []
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY trigger_at ASC"

        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_due_items(self, now: datetime, kind: str = None) -> List[Dict]:
        query = "SELECT * FROM scheduled_items WHERE active = 1 AND trigger_at <= ?"
        params = [now.isoformat()]
        if kind:
            query += " AND kind = ?"
            params.append(kind)

        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def find_active(self, kind: str, label_text: str) -> List[Dict]:
        """Find active items of a kind matching label text (exact match first, else substring)."""
        items = self.get_active_items(kind=kind)
        text_lower = label_text.strip().lower()

        exact = [i for i in items if i["label"].lower() == text_lower]
        if exact:
            return exact
        return [i for i in items if text_lower in i["label"].lower()]

    def reschedule(self, item_id: str, next_trigger_at: datetime) -> bool:
        """Advance a recurring item to its next trigger time (stays active)."""
        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE scheduled_items SET trigger_at = ? WHERE id = ?",
                (next_trigger_at.isoformat(), item_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def deactivate(self, item_id: str) -> bool:
        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE scheduled_items SET active = 0 WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0

    def deactivate_all(self, kind: str) -> int:
        with closing_transaction(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE scheduled_items SET active = 0 WHERE kind = ? AND active = 1", (kind,))
            conn.commit()
            return cursor.rowcount
