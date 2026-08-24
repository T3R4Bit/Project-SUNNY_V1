#!/usr/bin/env python
"""One-time migration: copy existing tasks.db/lists.db (SQLite) into the
Obsidian vault as markdown, via sunny_code.components.tasks_db.TaskDB /
lists_db.ListDB's vault-backed implementations.

Reads the OLD SQLite files directly with raw sqlite3 (not through TaskDB/
ListDB, which by the time this runs are already the markdown-backed
classes and can no longer read the old file format).

Never touches or deletes tasks.db/lists.db — they're left in place
untouched as a manual-delete-later safety net. Idempotent: re-running
overwrites the same vault files (keyed by original id/slug) rather than
duplicating anything, so it's safe to run more than once.

Usage:
    python migrate_to_vault.py            # migrate for real
    python migrate_to_vault.py --dry-run  # report counts, write nothing
"""

import sqlite3
import sys
from pathlib import Path

from sunny_code.components.lists_db import ListDB
from sunny_code.components.tasks_db import TaskDB
from sunny_code.config import get_settings


def _read_tasks(db_path: Path):
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM tasks")
        return [dict(row) for row in cursor.fetchall()]


def _read_lists_and_items(db_path: Path):
    if not db_path.exists():
        return [], {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        lists = [dict(row) for row in conn.execute("SELECT * FROM lists").fetchall()]
        items_by_list = {}
        for row in conn.execute("SELECT * FROM list_items ORDER BY list_id, checked ASC, created_at ASC"):
            item = dict(row)
            items_by_list.setdefault(item["list_id"], []).append(item)
    return lists, items_by_list


def main():
    dry_run = "--dry-run" in sys.argv
    settings = get_settings()

    old_tasks_db = settings.project_root / "tasks.db"
    old_lists_db = settings.project_root / "lists.db"
    vault_state_dir = settings.project_root / "sunny-vault" / "state"

    tasks = _read_tasks(old_tasks_db)
    lists, items_by_list = _read_lists_and_items(old_lists_db)
    total_items = sum(len(v) for v in items_by_list.values())

    print(f"Found {len(tasks)} task(s) in {old_tasks_db}")
    print(f"Found {len(lists)} list(s) and {total_items} item(s) in {old_lists_db}")

    if dry_run:
        print("\n--dry-run: nothing written. Re-run without --dry-run to migrate for real.")
        return

    if tasks:
        task_db = TaskDB(vault_state_dir / "tasks")
        for task in tasks:
            task_db.import_task(task)
        print(f"Wrote {len(tasks)} task file(s) to {vault_state_dir / 'tasks'}")

    if lists:
        list_db = ListDB(vault_state_dir / "lists")
        for list_row in lists:
            items = items_by_list.get(list_row["id"], [])
            list_db.import_list(list_row, items)
        print(f"Wrote {len(lists)} list file(s) to {vault_state_dir / 'lists'}")

    print("\nDone. The original tasks.db/lists.db files were not touched or deleted.")


if __name__ == "__main__":
    main()
