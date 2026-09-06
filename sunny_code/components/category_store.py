"""The fixed, user-editable list of task categories a task can be manually
filed under — General/School/Motorsports plus anything added via Discord's
/category command. Set through /category, not .env — same "runtime state,
not a secret" reasoning as location_store.py, and the same live-takes-effect
pattern (no restart needed).

"Projects" is deliberately never a member of this list — it's not a category
tasks get manually tagged into. See sunny-vault/docs/architecture/
task-system.md: the dashboard's Projects section lists real project folders
on disk (sunny_code/components/project_engine.py), unrelated to this store.
"""

import json
import logging
from typing import List, Tuple

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_SEED_CATEGORIES = ["General", "School", "Motorsports"]
_RESERVED = {"projects"}  # case-insensitive; see module docstring


def _path():
    return get_settings().project_root / "categories.json"


def get_categories() -> List[str]:
    """The current category list, in insertion order (General/School/
    Motorsports first, since those seed the file). Creates the file with
    the seed defaults on first call if it doesn't exist yet."""
    path = _path()
    if not path.exists():
        _save(_SEED_CATEGORIES)
        return list(_SEED_CATEGORIES)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        categories = data.get("categories")
        if isinstance(categories, list) and categories:
            return categories
    except (OSError, ValueError) as e:
        logger.error(f"categories.json unreadable: {e}", exc_info=True)

    return list(_SEED_CATEGORIES)


def _save(categories: List[str]) -> None:
    vault_io.atomic_write_text(_path(), json.dumps({"categories": categories}, indent=2))


def add_category(name: str) -> Tuple[bool, str]:
    """Add a new category. Rejects an empty name, a duplicate (case-
    insensitive), or the reserved "Projects" name."""
    name = name.strip()
    if not name:
        return False, "Category name can't be empty."
    if name.lower() in _RESERVED:
        return False, '"Projects" is a reserved section, not a category you can add.'

    categories = get_categories()
    if any(c.lower() == name.lower() for c in categories):
        return False, f'"{name}" is already a category.'

    categories.append(name)
    _save(categories)
    logger.info(f"Category added: {name!r}")
    return True, f'Added category "{name}".'


def remove_category(name: str) -> Tuple[bool, str]:
    """Remove a category. Refuses to remove "General" (the permanent
    fallback). Existing tasks already tagged with a removed category keep
    that tag string as-is — only the offered picker list changes; "show my
    tasks --tag X" still works against whatever's actually stored."""
    name = name.strip()
    if name.lower() == "general":
        return False, '"General" can\'t be removed — it\'s the permanent fallback category.'

    categories = get_categories()
    match = next((c for c in categories if c.lower() == name.lower()), None)
    if match is None:
        return False, f'"{name}" isn\'t a category.'

    categories.remove(match)
    _save(categories)
    logger.info(f"Category removed: {match!r}")
    return True, f'Removed category "{match}".'
