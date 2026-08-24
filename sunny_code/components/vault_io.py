"""Shared helpers for reading/writing markdown files with YAML frontmatter in
the Obsidian vault — used by tasks_db.py, lists_db.py, and
scheduled_vault_mirror.py, the three places Sunny writes into
sunny-vault/state/.

Concurrency note: the safety of unsynchronized reads/writes here relies on
every caller staying `async def` (confirmed true today for every FastAPI
route touching tasks/lists — no `run_in_executor`/`to_thread` anywhere in
this codebase), so Starlette never dispatches these calls to a worker
thread. Python's single-threaded cooperative scheduling then guarantees a
sync function body here can't be interrupted mid-write by another
coroutine. If a route handler here ever becomes a plain `def` (dispatched
to a threadpool) or genuine multithreading gets introduced, this guarantee
breaks and real locking would be needed. The one scenario this does NOT
cover — a separate OS process (chat.py) writing at the same instant as the
main server — is handled by atomic_write_text() below: a genuine race there
means "last writer wins for that file," never corruption or a torn read.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n?(.*)\Z", re.DOTALL)


def atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` without ever leaving a partial file behind.

    Writes to a sibling .tmp file, then os.replace() — NOT os.rename(),
    which is not an atomic overwrite on Windows (raises FileExistsError if
    the destination already exists; only POSIX rename() silently replaces).
    Every task/list file gets rewritten repeatedly, not appended once, so
    this distinction matters on the very first update.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def _coerce_datelike(value: Any) -> Any:
    """PyYAML's implicit resolver can parse an unquoted ISO-looking scalar
    into a native date/datetime object on load. Every value we read back
    out (created_at, updated_at, due_date) is meant to stay a plain str —
    convert back defensively so a stray hand-edited file can't turn a
    later `.startswith()` call elsewhere into an AttributeError crash."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def parse_frontmatter(text: str) -> Tuple[Dict, str]:
    """Split a '---\\nYAML\\n---\\nbody' document into (metadata, body).

    Returns ({}, text) unchanged if there's no frontmatter block at all —
    callers decide whether that's an error worth raising for their format.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_yaml, body = match.group(1), match.group(2)
    metadata = yaml.safe_load(raw_yaml) or {}
    metadata = {k: _coerce_datelike(v) for k, v in metadata.items()}
    return metadata, body


def read_body(path: Path) -> Optional[str]:
    """A frontmatter markdown file's body only, frontmatter stripped, or
    None if the file doesn't exist. For callers that only want the content
    (e.g. loading a prompt template) and shouldn't have to parse/discard
    YAML they never use."""
    if not path.exists():
        return None
    _metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return body


def serialize_frontmatter(metadata: Dict, body: str, field_order: List[str]) -> str:
    """Build a '---\\nYAML\\n---\\nbody' document.

    Keys whose value is None are omitted entirely (an absent field reads
    better in Dataview than a written-out `null`). field_order controls
    emission order so repeated writes produce stable, readable diffs —
    any metadata key not listed in field_order is appended after, sorted,
    as a fallback (should not normally happen for our fixed schemas).
    """
    ordered = {k: metadata[k] for k in field_order if k in metadata and metadata[k] is not None}
    remaining = {k: v for k, v in metadata.items() if k not in ordered and v is not None}
    ordered.update(dict(sorted(remaining.items())))

    # Values here are always plain Python str/int/bool — never datetime —
    # so PyYAML's own resolver correctly quotes any ISO-looking string on
    # the way out (it checks whether the plain/unquoted form would parse
    # back to the same type; a str that looks like a date wouldn't, so it
    # gets quoted). This is what makes _coerce_datelike() a pure defensive
    # backstop on read, not something the writer needs to think about.
    yaml_block = yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return f"---\n{yaml_block}---\n{body}"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    """'Finish Physics Homework!' -> 'finish-physics-homework'."""
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    slug = slug[:max_len].rstrip("-")
    return slug or "untitled"
