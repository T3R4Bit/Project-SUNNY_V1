"""Read-only HTTP access to Sunny's logs.

WHY THIS EXISTS
---------------
Sunny writes six logs into the vault and a routing trace into logs/, and
until now none of them were reachable over HTTP. The old `/console` had a
Logs tab; when the console was retired on 2026-09-13 the trace machinery
survived (trace.py still writes traces.jsonl and still supports SSE
subscribers) but lost every caller. So the data was being produced and
nothing could read it.

That is the worst state for a log: costing writes, answering nothing.

WHITELIST, NOT A PATH PARAMETER
-------------------------------
Log names map through SOURCES to fixed paths. The name from the URL is
never joined onto a directory, so there is no traversal to defend
against -- an unknown name is a 404 rather than a sanitised read. This
matters more than usual because the vault sits next to .env and the
Google token.

TAIL, NEVER READ
----------------
suggestions.md is 4MB and requests.md is 388KB, both growing. Reading one
into memory to show the last 50 lines would be slow on a box that is also
running the assistant, and the interesting end is always the recent one.
_tail_lines seeks from the end and reads backwards in blocks.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from sunny_code.components import trace
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Default tail size. Enough to see the last hour of most of these without
# being enough to stall a phone on a bad connection.
DEFAULT_LINES = 200
MAX_LINES = 2000

_READ_BLOCK = 64 * 1024


def _vault_log(name: str) -> Path:
    return get_settings().project_root / "sunny-vault" / "log" / name


def _sources() -> Dict[str, Dict]:
    """The whitelist. Every readable log, with what it is FOR -- a log
    viewer that just lists filenames makes you open each one to find out
    which is which."""
    settings = get_settings()
    return {
        "requests": {
            "label": "Requests",
            "description": "Every message routed, and which feature answered it",
            "path": _vault_log("requests.md"),
        },
        "llm-usage": {
            "label": "LLM usage",
            "description": "Every Claude call attempted — including ones refused before a request was made",
            "path": _vault_log("llm-usage.md"),
        },
        "rules-engine": {
            "label": "Rules engine",
            "description": "Proactive rules that fired, and why",
            "path": _vault_log("rules-engine.md"),
        },
        "checkins": {
            "label": "Check-ins",
            "description": "Daily check-in answers",
            "path": _vault_log("checkins.md"),
        },
        "health-checks": {
            "label": "Health checks",
            "description": "Weekly system health reports",
            "path": _vault_log("health-checks.md"),
        },
        "suggestions": {
            "label": "Suggestions",
            "description": "Things Sunny proposed — including changes to files it may not edit itself",
            "path": _vault_log("suggestions.md"),
        },
        "app": {
            "label": "Application log",
            "description": "The running service's own log",
            "path": settings.logs_dir / "sunny.log",
        },
    }


def _tail_lines(path: Path, limit: int) -> List[str]:
    """Last `limit` lines, read backwards from the end.

    Deliberately not `path.read_text().splitlines()[-limit:]` -- these
    files reach megabytes and this runs on a box that is also answering
    messages.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []

    chunks: List[bytes] = []
    newlines = 0
    with open(path, "rb") as f:
        position = size
        while position > 0 and newlines <= limit:
            read_size = min(_READ_BLOCK, position)
            position -= read_size
            f.seek(position)
            block = f.read(read_size)
            chunks.append(block)
            newlines += block.count(b"\n")

    data = b"".join(reversed(chunks))
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-limit:]


def _describe(name: str, source: Dict) -> Dict:
    path: Path = source["path"]
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "name": name,
        "label": source["label"],
        "description": source["description"],
        "exists": exists,
        "bytes": stat.st_size if stat else 0,
        # ISO rather than a formatted string: the client decides how to
        # show "3 minutes ago", and a server-rendered relative time is
        # wrong the moment it is cached.
        "modified": (datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                     if stat else None),
    }


def create_logs_router() -> APIRouter:
    router = APIRouter()

    @router.get("/logs")
    async def list_logs() -> dict:
        """Every log source, whether it exists, and how big it is.

        Non-existent sources are returned with `exists: false` rather than
        omitted -- "this log is empty because the feature never ran" is
        useful, and silently dropping it looks like the viewer is broken.
        """
        sources = _sources()
        return {"sources": [_describe(name, source) for name, source in sources.items()]}

    @router.get("/logs/{name}")
    async def read_log(
        name: str,
        lines: int = Query(DEFAULT_LINES, ge=1, le=MAX_LINES),
    ) -> dict:
        sources = _sources()
        source = sources.get(name)
        if source is None:
            raise HTTPException(status_code=404, detail=f"Unknown log {name!r}")

        path: Path = source["path"]
        if not path.exists():
            return {**_describe(name, source), "lines": [], "truncated": False}

        tail = _tail_lines(path, lines)
        described = _describe(name, source)
        return {
            **described,
            "lines": tail,
            # True when there is more above what was returned, so the UI
            # can say so instead of implying this is the whole file.
            "truncated": described["bytes"] > 0 and len(tail) >= lines,
        }

    @router.get("/traces/recent")
    async def recent_traces(limit: int = Query(100, ge=1, le=1000)) -> dict:
        """Routing traces: which feature answered a message, how confident
        the match was, and which function ran.

        This restores a capability that has been writing to disk with no
        reader since the console was retired on 2026-09-13.
        """
        return {"traces": trace.recent_traces(limit=limit)}

    return router
