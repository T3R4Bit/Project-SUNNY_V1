"""List storage — one markdown file per list in the Obsidian vault
(sunny-vault/data/state/lists/<slug>.md), using native Obsidian checkbox syntax
for items. Not SQLite. See sunny_code/components/tasks_db.py's module
docstring for the shared concurrency/atomic-write reasoning, and
sunny-vault/docs/architecture/vault-storage.md for the full rationale.

Separate from tasks on purpose (unchanged from before this migration): a
list (groceries, packing, reading) is just checkable items with no
priority/status/due-date, distinct from a task. "To-Do" is the default
list name when none is specified.

List names are already enforced case-insensitive-unique (see
get_or_create_list), so unlike tasks, slugified-name filenames have zero
collision risk here.

Per-item source/created_at (tracked in the old SQLite schema) are dropped:
nothing in lists_engine.py has ever read either field, and file line order
is a free, exact substitute for created_at ordering since items are only
ever appended, never reordered. Item "id" is synthesized from line position
at parse time, not persisted — safe because the only caller pattern
(find_item() -> immediately remove_item() within the same call) never
carries an id across separate calls; nothing wires check_item() to a
command today either.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components import vault_io

logger = logging.getLogger(__name__)

DEFAULT_LIST_NAME = "To-Do"

_FIELD_ORDER = ["id", "name", "source", "created_at"]


class ListDB:
    """Vault-backed list storage."""

    def __init__(self, lists_dir: Path):
        self.lists_dir = lists_dir
        self.lists_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"List vault storage initialized: {self.lists_dir}")

    # ---------- internal: file <-> dict ----------

    def _path_for_slug(self, slug: str) -> Path:
        return self.lists_dir / f"{slug}.md"

    def _unique_slug(self, name: str) -> str:
        base = vault_io.slugify(name)
        slug = base
        n = 2
        while self._path_for_slug(slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    @staticmethod
    def _list_to_document(list_meta: Dict, items: List[Dict]) -> str:
        metadata = {k: list_meta.get(k) for k in _FIELD_ORDER}
        body = f"\n# {list_meta.get('name', '')}\n\n"
        for item in items:
            box = "x" if item.get("checked") else " "
            body += f"- [{box}] {item['text']}\n"
        return vault_io.serialize_frontmatter(metadata, body, _FIELD_ORDER)

    @staticmethod
    def _document_to_list_and_items(text: str) -> Optional[Dict]:
        metadata, body = vault_io.parse_frontmatter(text)
        if not metadata or "id" not in metadata:
            return None
        # Every field always present with a None default for anything omitted
        # from frontmatter — same reasoning as TaskDB._document_to_task().
        metadata = {field: metadata.get(field) for field in _FIELD_ORDER}

        # ID is the item's ordinal position among checkbox lines specifically
        # (not the raw line index in the file) — this has to match how
        # add_item() computes the id for a freshly-appended item (its index
        # in the in-memory items list), so an id returned by one call means
        # the same thing when looked up after a subsequent read.
        items = []
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- [ ]") or stripped.startswith("- [x]") or stripped.startswith("- [X]"):
                checked = stripped[3].lower() == "x"
                item_text = stripped[6:].strip()
                items.append(
                    {
                        "id": f"L{len(items)}",
                        "text": item_text,
                        "checked": checked,
                        "source": None,
                        "created_at": None,
                    }
                )

        return {"list": dict(metadata), "items": items}

    def _iter_lists(self):
        """Yield every parseable (list_meta, items) pair. Skips (and logs)
        any file that fails to parse rather than one bad file breaking a
        directory-wide scan."""
        for path in sorted(self.lists_dir.glob("*.md")):
            try:
                parsed = self._document_to_list_and_items(path.read_text(encoding="utf-8"))
                if parsed is not None:
                    yield path, parsed["list"], parsed["items"]
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Skipping unreadable list file {path}: {e}")
            except Exception as e:
                logger.warning(f"Skipping unparseable list file {path}: {e}")

    def _find_by_id(self, list_id: str):
        """Returns (path, list_meta, items) or None."""
        for path, list_meta, items in self._iter_lists():
            if list_meta.get("id") == list_id:
                return path, list_meta, items
        return None

    # ---------- public API (unchanged from the SQLite version) ----------

    def get_or_create_list(self, name: str, source: str = None) -> str:
        """Find a list by name (case-insensitive), creating it if it doesn't exist. Returns list ID."""
        name = name.strip()
        if not name:
            name = DEFAULT_LIST_NAME

        existing = self.get_list_by_name(name)
        if existing:
            return existing["id"]

        list_id = uuid.uuid4().hex[:8]
        now = datetime.utcnow().isoformat()
        list_meta = {"id": list_id, "name": name, "source": source, "created_at": now}
        slug = self._unique_slug(name)
        vault_io.atomic_write_text(self._path_for_slug(slug), self._list_to_document(list_meta, []))
        logger.info(f"List created: {list_id} - {name}")
        return list_id

    def get_list_by_name(self, name: str) -> Optional[Dict]:
        name_lower = name.strip().lower()
        for _, list_meta, _ in self._iter_lists():
            if list_meta.get("name", "").lower() == name_lower:
                return list_meta
        return None

    def get_all_lists(self) -> List[Dict]:
        lists = [list_meta for _, list_meta, _ in self._iter_lists()]
        lists.sort(key=lambda l: l.get("name", "").lower())
        return lists

    def add_item(self, list_id: str, text: str, source: str = None) -> str:
        text = text.strip()
        if not text:
            raise ValueError("Item text cannot be empty")

        found = self._find_by_id(list_id)
        if found is None:
            raise ValueError(f"No list found with id {list_id}")
        path, list_meta, items = found

        items.append({"id": None, "text": text, "checked": False, "source": source, "created_at": None})
        vault_io.atomic_write_text(path, self._list_to_document(list_meta, items))
        item_id = f"L{len(items) - 1}"
        logger.info(f"List item added: {item_id} - {text} (list {list_id})")
        return item_id

    def get_items(self, list_id: str, include_checked: bool = True) -> List[Dict]:
        found = self._find_by_id(list_id)
        if found is None:
            return []
        _, _, items = found
        if not include_checked:
            items = [i for i in items if not i["checked"]]
        # Stable partition reproduces "ORDER BY checked ASC, created_at ASC" —
        # file line order already IS created_at order (append-only), so a
        # stable sort on just `checked` preserves that within each group.
        return sorted(items, key=lambda i: i["checked"])

    def find_item(self, list_id: str, text: str) -> List[Dict]:
        """Find items in a list matching text (exact match first, else substring)."""
        items = self.get_items(list_id)
        text_lower = text.strip().lower()

        exact = [i for i in items if i["text"].lower() == text_lower]
        if exact:
            return exact

        return [i for i in items if text_lower in i["text"].lower()]

    def check_item(self, item_id: str, checked: bool = True) -> bool:
        for path, list_meta, items in self._iter_lists():
            for item in items:
                if item["id"] == item_id:
                    item["checked"] = checked
                    vault_io.atomic_write_text(path, self._list_to_document(list_meta, items))
                    return True
        return False

    def remove_item(self, item_id: str) -> bool:
        for path, list_meta, items in self._iter_lists():
            new_items = [i for i in items if i["id"] != item_id]
            if len(new_items) != len(items):
                vault_io.atomic_write_text(path, self._list_to_document(list_meta, new_items))
                return True
        return False

    def delete_list(self, list_id: str) -> bool:
        found = self._find_by_id(list_id)
        if found is None:
            return False
        path, _, _ = found
        path.unlink()
        return True

    def import_list(self, list_meta: Dict, items: List[Dict]) -> None:
        """Migration-only: write a list + its items verbatim, preserving the
        original list id/created_at. Used solely by migrate_to_vault.py.

        Idempotent by id, not by slug — see TaskDB.import_task()'s docstring
        for why re-running the migration must overwrite the same file
        rather than asking _unique_slug() for a fresh, already-taken one.
        """
        existing = self._find_by_id(list_meta["id"])
        if existing is not None:
            path = existing[0]
        else:
            path = self._path_for_slug(self._unique_slug(list_meta.get("name", "untitled")))
        vault_io.atomic_write_text(path, self._list_to_document(list_meta, items))
