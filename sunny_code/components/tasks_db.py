"""Task database management and CRUD operations."""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class TaskDB:
    """SQLite database for task storage."""

    # Categories are free-form (any non-empty string) — these are just the
    # originally-shipped defaults, not an enforced list.
    DEFAULT_TAGS = {"School", "Motorsports", "General", "Project Ideas"}
    VALID_STATUSES = {"open", "in_progress", "done"}
    VALID_PRIORITIES = {1, 2, 3, 4, 5}

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Tasks table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    tag TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open', 'in_progress', 'done')) DEFAULT 'open',
                    priority INTEGER CHECK(priority BETWEEN 1 AND 5) DEFAULT 3,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    due_date DATETIME,
                    source TEXT
                )
                """
            )

            # Older databases have a CHECK(tag IN (...)) constraint from when
            # categories were a fixed list. SQLite can't ALTER a CHECK away, so
            # rebuild the table without it. Safe to run every startup — no-op
            # once migrated, and a no-op on fresh installs (no constraint to find).
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
            row = cursor.fetchone()
            if row and row[0] and "CHECK(tag IN" in row[0]:
                logger.info("Migrating tasks table: removing fixed-category constraint")
                cursor.execute("ALTER TABLE tasks RENAME TO tasks_old")
                cursor.execute(
                    """
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT,
                        tag TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('open', 'in_progress', 'done')) DEFAULT 'open',
                        priority INTEGER CHECK(priority BETWEEN 1 AND 5) DEFAULT 3,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        due_date DATETIME
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO tasks (id, title, description, tag, status, priority, created_at, updated_at, due_date)
                    SELECT id, title, description, tag, status, priority, created_at, updated_at, due_date FROM tasks_old
                    """
                )
                cursor.execute("DROP TABLE tasks_old")

            # Older databases predate the "source" column (which device created
            # the task — web/discord/api). Additive, so a plain ALTER is enough.
            cursor.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in cursor.fetchall()}
            if "source" not in columns:
                logger.info("Migrating tasks table: adding source column")
                cursor.execute("ALTER TABLE tasks ADD COLUMN source TEXT")

            # Indexes for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag ON tasks(tag)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_priority ON tasks(priority)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_due_date ON tasks(due_date)")

            conn.commit()
            logger.info(f"Task database initialized: {self.db_path}")

    def create_task(
        self,
        title: str,
        tag: str,
        priority: int = 3,
        description: str = None,
        due_date: str = None,
        source: str = None,
    ) -> str:
        """Create a new task. Returns task ID."""
        # Validate inputs
        if not tag or not tag.strip():
            raise ValueError("Category cannot be empty")
        if priority not in self.VALID_PRIORITIES:
            raise ValueError(f"Priority must be 1-5, got {priority}")
        if not title or not title.strip():
            raise ValueError("Title cannot be empty")

        tag = tag.strip()
        task_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (id, title, description, tag, priority, created_at, updated_at, due_date, status, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (task_id, title, description, tag, priority, now, now, due_date, source),
            )
            conn.commit()
            logger.info(f"Task created: {task_id} - {title} (source: {source})")

        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a single task by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_tasks(self, status: str = None, tag: str = None) -> List[Dict]:
        """Get tasks with optional filtering."""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if tag:
            query += " AND tag = ?"
            params.append(tag)

        query += " ORDER BY priority DESC, created_at ASC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_tasks_by_status(self, status: str) -> List[Dict]:
        """Get all tasks with a specific status."""
        return self.get_all_tasks(status=status)

    def get_tasks_by_tag(self, tag: str) -> List[Dict]:
        """Get all tasks with a specific tag."""
        return self.get_all_tasks(tag=tag)

    def get_open_tasks(self) -> List[Dict]:
        """Get all open tasks."""
        return self.get_all_tasks(status="open")

    def get_done_tasks(self) -> List[Dict]:
        """Get all completed tasks."""
        return self.get_all_tasks(status="done")

    def get_in_progress_tasks(self) -> List[Dict]:
        """Get all in-progress tasks."""
        return self.get_all_tasks(status="in_progress")

    def get_tasks_due_soon(self, days: int = 7) -> List[Dict]:
        """Get tasks due within N days."""
        cutoff = (datetime.utcnow() + timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE status != 'done' AND due_date IS NOT NULL AND due_date <= ?
                ORDER BY due_date ASC, priority DESC
                """,
                (cutoff,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_high_priority_tasks(self, min_priority: int = 4) -> List[Dict]:
        """Get high-priority tasks."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE status != 'done' AND priority >= ?
                ORDER BY priority DESC, created_at ASC
                """,
                (min_priority,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_task(self, task_id: str, **kwargs) -> bool:
        """Update a task. Valid keys: title, description, tag, status, priority, due_date."""
        valid_keys = {"title", "description", "tag", "status", "priority", "due_date"}
        keys = set(kwargs.keys())

        if not keys.issubset(valid_keys):
            raise ValueError(f"Invalid keys: {keys - valid_keys}")

        # Validate values
        if "tag" in kwargs and (not kwargs["tag"] or not kwargs["tag"].strip()):
            raise ValueError("Category cannot be empty")
        if "status" in kwargs and kwargs["status"] not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {kwargs['status']}")
        if "priority" in kwargs and kwargs["priority"] not in self.VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {kwargs['priority']}")

        if "tag" in kwargs:
            kwargs["tag"] = kwargs["tag"].strip()

        if not kwargs:
            return False

        now = datetime.utcnow().isoformat()
        updates = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [now, task_id]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE tasks SET {updates}, updated_at = ? WHERE id = ?",
                values,
            )
            conn.commit()
            logger.info(f"Task updated: {task_id} - {kwargs}")

        return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            logger.info(f"Task deleted: {task_id}")

        return cursor.rowcount > 0

    def get_stats(self) -> Dict:
        """Get task statistics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status = 'open'")
            open_count = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status = 'done'")
            done_count = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status = 'in_progress'")
            in_progress_count = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) as count FROM tasks")
            total_count = cursor.fetchone()["count"]

            # Tasks by tag
            cursor.execute("SELECT tag, COUNT(*) as count FROM tasks WHERE status = 'open' GROUP BY tag")
            by_tag = {row["tag"]: row["count"] for row in cursor.fetchall()}

            return {
                "open": open_count,
                "done": done_count,
                "in_progress": in_progress_count,
                "total": total_count,
                "by_tag": by_tag,
            }
