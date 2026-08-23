"""Task storage — one markdown file per task in the Obsidian vault
(sunny-vault/state/tasks/<slug>.md), not SQLite. See
sunny-vault/docs/architecture/vault-storage.md for the migration rationale.

Sunny is the sole writer — these files are meant to be browsed in Obsidian,
not hand-edited (see that doc for what happens if you do anyway). Every
public method here keeps the exact name/signature/return-dict-shape the old
SQLite-backed TaskDB had, since sunny_code/components/tasks_api.py calls
most of them directly, bypassing TaskEngine entirely.
"""

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Literal, Optional

from sunny_code.components import vault_io

logger = logging.getLogger(__name__)

# Field order in the YAML frontmatter block — purely cosmetic (stable, readable
# diffs) but kept consistent across every write.
_FIELD_ORDER = ["id", "tag", "status", "priority", "due_date", "source", "created_at", "updated_at"]


class TaskDB:
    """Vault-backed task storage."""

    # Categories are free-form (any non-empty string) — these are just the
    # originally-shipped defaults, not an enforced list.
    DEFAULT_TAGS = {"School", "Motorsports", "General", "Project Ideas"}
    VALID_STATUSES = {"open", "in_progress", "done"}
    VALID_PRIORITIES = {1, 2, 3, 4, 5}

    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Task vault storage initialized: {self.tasks_dir}")

    # ---------- internal: file <-> dict ----------

    def _path_for_slug(self, slug: str) -> Path:
        return self.tasks_dir / f"{slug}.md"

    def _unique_slug(self, title: str) -> str:
        base = vault_io.slugify(title)
        slug = base
        n = 2
        while self._path_for_slug(slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    @staticmethod
    def _task_to_document(task: Dict) -> str:
        metadata = {k: task.get(k) for k in _FIELD_ORDER}
        title = task.get("title", "")
        description = task.get("description")
        body = f"\n# {title}\n"
        if description:
            body += f"\n{description}\n"
        return vault_io.serialize_frontmatter(metadata, body, _FIELD_ORDER)

    @staticmethod
    def _document_to_task(text: str) -> Optional[Dict]:
        metadata, body = vault_io.parse_frontmatter(text)
        if not metadata or "id" not in metadata:
            return None
        lines = body.strip("\n").split("\n")
        title = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else ""
        description_lines = [l for l in lines[1:] if l.strip()]
        description = "\n".join(description_lines).strip() or None

        # Every field always present with a None default for anything
        # omitted from frontmatter (see serialize_frontmatter — None-valued
        # fields are dropped from what's written, for cleaner Dataview
        # output). SQLite always returned a full row with NULL for any
        # unset column; callers like TaskEngine.format_dashboard() use
        # bracket access (task["due_date"]) expecting that same guarantee —
        # a key simply missing from the dict would be a KeyError there.
        task = {field: metadata.get(field) for field in _FIELD_ORDER}
        task["title"] = title
        task["description"] = description
        return task

    def _iter_dir(self, directory: Path):
        """Yield every parseable task dict in one directory (non-recursive).
        Skips (and logs) any file that fails to parse rather than letting
        one bad file break every caller that scans the whole directory —
        a risk SQLite's single-table-read never had."""
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
                task = self._document_to_task(text)
                if task is not None:
                    yield task
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Skipping unreadable task file {path}: {e}")
            except Exception as e:
                logger.warning(f"Skipping unparseable task file {path}: {e}")

    def _iter_tasks(self):
        """Yield every parseable ACTIVE task dict -- never archived
        (deleted or finished) ones. See get_stats() for the one place
        archived tasks are read at all."""
        yield from self._iter_dir(self.tasks_dir)

    def _find_path_by_id(self, task_id: str) -> Optional[Path]:
        for path in self.tasks_dir.glob("*.md"):
            try:
                metadata, _ = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if metadata.get("id") == task_id:
                return path
        return None

    # ---------- public API (unchanged from the SQLite version) ----------

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
        if not tag or not tag.strip():
            raise ValueError("Category cannot be empty")
        if priority not in self.VALID_PRIORITIES:
            raise ValueError(f"Priority must be 1-5, got {priority}")
        if not title or not title.strip():
            raise ValueError("Title cannot be empty")

        tag = tag.strip()

        # Collision guard: SQLite would loudly reject a duplicate id via its
        # PRIMARY KEY constraint; a naive markdown write instead would
        # silently overwrite an unrelated task. Regenerate on the
        # astronomically unlikely chance of a real uuid4 collision.
        task_id = str(uuid.uuid4())[:8]
        while self._find_path_by_id(task_id) is not None:
            task_id = str(uuid.uuid4())[:8]

        now = datetime.utcnow().isoformat()
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "tag": tag,
            "status": "open",
            "priority": priority,
            "created_at": now,
            "updated_at": now,
            "due_date": due_date,
            "source": source,
        }

        slug = self._unique_slug(title)
        vault_io.atomic_write_text(self._path_for_slug(slug), self._task_to_document(task))
        logger.info(f"Task created: {task_id} - {title} (source: {source})")
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a single task by ID."""
        path = self._find_path_by_id(task_id)
        if path is None:
            return None
        return self._document_to_task(path.read_text(encoding="utf-8"))

    def get_all_tasks(self, status: str = None, tag: str = None) -> List[Dict]:
        """Get tasks with optional filtering."""
        tasks = list(self._iter_tasks())
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if tag:
            tasks = [t for t in tasks if t.get("tag") == tag]
        tasks.sort(key=lambda t: (-t.get("priority", 3), t.get("created_at") or ""))
        return tasks

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
        """Get tasks due within N days.

        Preserves the old SQLite version's exact comparison semantics: a
        bare "YYYY-MM-DD" due_date compared as a plain string against a
        full ISO timestamp cutoff — SQLite did this as a TEXT comparison,
        and Python's string `<=` reproduces it identically (a date-only
        prefix always sorts before/equal to a same-day full timestamp).
        Deliberately not "fixed" to parse real dates — that would change
        behavior, not just implementation.
        """
        cutoff = (datetime.utcnow() + timedelta(days=days)).isoformat()
        tasks = [
            t
            for t in self._iter_tasks()
            if t.get("status") != "done" and t.get("due_date") is not None and t["due_date"] <= cutoff
        ]
        tasks.sort(key=lambda t: (t["due_date"], -t.get("priority", 3)))
        return tasks

    def get_high_priority_tasks(self, min_priority: int = 4) -> List[Dict]:
        """Get high-priority tasks."""
        tasks = [
            t
            for t in self._iter_tasks()
            if t.get("status") != "done" and t.get("priority", 3) >= min_priority
        ]
        tasks.sort(key=lambda t: (-t.get("priority", 3), t.get("created_at") or ""))
        return tasks

    def update_task(self, task_id: str, **kwargs) -> bool:
        """Update a task. Valid keys: title, description, tag, status, priority, due_date."""
        valid_keys = {"title", "description", "tag", "status", "priority", "due_date"}
        keys = set(kwargs.keys())

        if not keys.issubset(valid_keys):
            raise ValueError(f"Invalid keys: {keys - valid_keys}")

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

        path = self._find_path_by_id(task_id)
        if path is None:
            return False

        task = self._document_to_task(path.read_text(encoding="utf-8"))
        if task is None:
            return False

        task.update(kwargs)
        task["updated_at"] = datetime.utcnow().isoformat()
        vault_io.atomic_write_text(path, self._task_to_document(task))
        logger.info(f"Task updated: {task_id} - {kwargs}")
        return True

    def delete_task(self, task_id: str) -> bool:
        """Delete a task. Deprecated in favor of archive_task(task_id,
        "deleted") — kept for any caller that genuinely wants the file
        gone, but nothing in this app calls it anymore (see
        tasks_engine.py's _execute_delete)."""
        path = self._find_path_by_id(task_id)
        if path is None:
            return False
        path.unlink()
        logger.info(f"Task deleted: {task_id}")
        return True

    def archive_task(self, task_id: str, reason: Literal["deleted", "finished"]) -> bool:
        """Move a task's file into archive/<reason>/ instead of removing
        it — no data is rewritten or dropped, just relocated, so "deleted"
        and "finished" tasks are always still there to find later. Used by
        tasks_engine.py for both the delete command and for a status
        update that resolves to "done"."""
        path = self._find_path_by_id(task_id)
        if path is None:
            return False

        archive_dir = self.tasks_dir / "archive" / reason
        archive_dir.mkdir(parents=True, exist_ok=True)

        dest = archive_dir / path.name
        if dest.exists():
            # A same-slug task was already archived before -- keep both,
            # same collision handling as _unique_slug.
            stem, suffix = path.stem, path.suffix
            n = 2
            while dest.exists():
                dest = archive_dir / f"{stem}-{n}{suffix}"
                n += 1

        path.rename(dest)
        logger.info(f"Task archived ({reason}): {task_id}")
        return True

    def get_stats(self) -> Dict:
        """Get task statistics. "done" and "total" include archived/
        finished tasks, so they reflect everything that ever finished even
        though archive_task() moves them out of the active listing
        everything else here uses. Archived/deleted tasks are never
        counted anywhere, regardless of whatever status they happened to
        have at the moment they were deleted -- deleting a task shouldn't
        move any stat."""
        tasks = list(self._iter_tasks())
        finished_archived = list(self._iter_dir(self.tasks_dir / "archive" / "finished"))

        open_tasks = [t for t in tasks if t.get("status") == "open"]
        by_tag: Dict[str, int] = {}
        for t in open_tasks:
            by_tag[t.get("tag", "General")] = by_tag.get(t.get("tag", "General"), 0) + 1

        done_count = sum(1 for t in tasks if t.get("status") == "done") + len(finished_archived)

        return {
            "open": len(open_tasks),
            "done": done_count,
            "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
            "total": len(tasks) + len(finished_archived),
            "by_tag": by_tag,
        }

    def import_task(self, task: Dict) -> None:
        """Migration-only: write a task dict verbatim, preserving its original
        id/status/created_at/updated_at exactly (unlike create_task(), which
        always mints fresh ones). Used solely by migrate_to_vault.py.

        Idempotent by id, not by slug: re-running the migration must
        overwrite this same task's file rather than create a second one —
        if a file already exists for this exact id, reuse its path/slug
        instead of asking _unique_slug() for a fresh one (which would only
        ever see "a file with this slug exists" and increment past it).
        """
        existing_path = self._find_path_by_id(task["id"])
        if existing_path is not None:
            path = existing_path
        else:
            path = self._path_for_slug(self._unique_slug(task.get("title", "untitled")))
        vault_io.atomic_write_text(path, self._task_to_document(task))
