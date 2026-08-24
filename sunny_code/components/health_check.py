"""Weekly system health check — gathers a compact summary of the past
week's errors, unfulfilled requests, and LLM calls, asks Claude to write it
up, and logs/posts the result. Triggered every Sunday at 4am by a standalone
scheduling loop in main.py (not tied to the Discord bot's lifecycle — this
must run and log even when Discord isn't configured; posting the report to
Discord is optional, not a requirement for the check itself to happen).

See sunny-vault/docs/BACKLOG.md and sunny-vault/docs/architecture/health-check.md.
"""

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

from sunny_code.components import key_status, vault_io
from sunny_code.components.llm_client import ask_claude
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_STATE_FIELD_ORDER = ["id", "type", "status", "updated_at"]
_TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
_REQUEST_LINE_RE = re.compile(r"\*\*[\d\-T:]+Z?\*\*\s*\[(\w+)\]")
_LLM_HEADER_RE = re.compile(r"^## [\d\-T:]+Z? — (\S+) \([^)]+\) — (\w+)")


def _count_log_errors() -> int:
    """ERROR lines in the current (unrotated) app log only — not a precise
    7-day window, a stated simplification that's fine at this log's volume."""
    settings = get_settings()
    log_path = settings.logs_dir / "sunny.log"
    if not log_path.exists():
        return 0
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if "ERROR" in line)


def _recent_request_categories(days: int = 7) -> Counter:
    """Category -> count, from requests.md entries in the last `days` days."""
    settings = get_settings()
    path = settings.project_root / "sunny-vault" / "log" / "requests.md"
    counts = Counter()
    if not path.exists():
        return counts
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for line in path.read_text(encoding="utf-8").splitlines():
        ts_match = _TIMESTAMP_RE.search(line)
        cat_match = _REQUEST_LINE_RE.search(line)
        if not ts_match or not cat_match:
            continue
        try:
            ts = datetime.fromisoformat(ts_match.group(1)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts >= cutoff:
            counts[cat_match.group(1)] += 1
    return counts


def _recent_llm_calls(days: int = 7) -> Counter:
    """(purpose, status) -> count, from llm-usage.md entries in the last
    `days` days."""
    settings = get_settings()
    path = settings.project_root / "sunny-vault" / "log" / "llm-usage.md"
    counts = Counter()
    if not path.exists():
        return counts
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("## "):
            continue
        ts_match = _TIMESTAMP_RE.search(line)
        header_match = _LLM_HEADER_RE.match(line)
        if not ts_match or not header_match:
            continue
        try:
            ts = datetime.fromisoformat(ts_match.group(1)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts >= cutoff:
            counts[header_match.groups()] += 1
    return counts


# Knowledge health check -- personal-assistant-vision.md section 8,
# extends this same weekly report rather than being a parallel system,
# per that section's own framing ("Extend the existing weekly system
# health check"). Wikilinks only (Obsidian's actual convention throughout
# this vault, confirmed by every architecture doc's own [[cross-links]]),
# not markdown-style [text](path.md) links -- not used here.
_KNOWLEDGE_EXCLUDED_DIRS = {".obsidian", "archive", "log", "state", "instructions"}
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_STALE_DAYS = 180


def _iter_vault_notes() -> List[Path]:
    vault_root = get_settings().project_root / "sunny-vault"
    if not vault_root.exists():
        return []
    return [
        p for p in vault_root.rglob("*.md")
        if not any(part in _KNOWLEDGE_EXCLUDED_DIRS for part in p.relative_to(vault_root).parts)
    ]


def knowledge_health_summary() -> str:
    """Broken wikilinks, orphaned/untagged/stale notes -- same "compact,
    pre-counted, not a raw dump" reasoning as _build_summary() below.
    Caveat worth knowing: "orphaned" (no incoming links) will always flag
    real entry-point docs like README.md/Mind-Map.md, which are meant to
    be linked FROM, not TO -- there's no attempt here to distinguish those
    from a genuinely forgotten note, so a nonzero orphan count isn't
    automatically something to fix. True duplicate-CONTENT detection
    (semantic, not just a filename collision) is out of scope entirely --
    flagged as future work, not attempted."""
    notes = _iter_vault_notes()
    if not notes:
        return "Knowledge health: no vault notes found."

    notes_by_stem: Dict[str, Path] = {}
    for p in notes:
        notes_by_stem.setdefault(p.stem.lower(), p)

    broken_links = []
    linked_targets = set()
    untagged = []
    stale = []
    cutoff = datetime.now(timezone.utc).timestamp() - (_STALE_DAYS * 86400)

    for note in notes:
        try:
            text = note.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for match in _WIKILINK_RE.finditer(text):
            target = match.group(1).strip().lower()
            if target.endswith(".md"):
                target = target[:-3]
            resolved = notes_by_stem.get(target)
            if resolved is None:
                broken_links.append((note, match.group(1).strip()))
            else:
                linked_targets.add(resolved)

        metadata, _body = vault_io.parse_frontmatter(text)
        if not metadata.get("tags"):
            untagged.append(note)

        try:
            if note.stat().st_mtime < cutoff:
                stale.append(note)
        except OSError:
            pass

    orphaned = [n for n in notes if n not in linked_targets]

    lines = [f"Vault notes scanned: {len(notes)}"]
    if broken_links:
        examples = ", ".join(f'{n.name}->"{t}"' for n, t in broken_links[:5])
        more = "..." if len(broken_links) > 5 else ""
        lines.append(f"- Broken wikilinks: {len(broken_links)} ({examples}{more})")
    else:
        lines.append("- Broken wikilinks: none")
    if orphaned:
        names = ", ".join(n.name for n in orphaned[:5])
        more = "..." if len(orphaned) > 5 else ""
        lines.append(f"- Orphaned notes (no incoming links, entry-point docs expected here too): {len(orphaned)} ({names}{more})")
    else:
        lines.append("- Orphaned notes: none")
    lines.append(f"- Untagged notes: {len(untagged)}" if untagged else "- Untagged notes: none")
    lines.append(
        f"- Stale notes (untouched {_STALE_DAYS}+ days): {len(stale)}" if stale else "- Stale notes: none"
    )

    return "\n".join(lines)


def _build_summary(days: int = 7) -> str:
    """A compact, pre-counted text summary — not raw log dumps — so the
    prompt sent to Claude stays small. This is where the token-minimization
    goal actually applies: the LLM never sees the raw logs, only counts."""
    error_count = _count_log_errors()
    request_counts = _recent_request_categories(days)
    llm_counts = _recent_llm_calls(days)
    expiring = key_status.expiring_within(7)

    lines = [f"Past {days} days:", f"- App log errors: {error_count}"]

    if request_counts:
        cats = ", ".join(f"{cat}: {n}" for cat, n in request_counts.most_common())
        lines.append(f"- Unfulfilled requests by category: {cats}")
    else:
        lines.append("- Unfulfilled requests: none")

    if llm_counts:
        parts = ", ".join(f"{purpose}/{status}: {n}" for (purpose, status), n in llm_counts.most_common())
        lines.append(f"- LLM calls by purpose/status: {parts}")
    else:
        lines.append("- LLM calls: none")

    if expiring:
        exp = ", ".join(f"{label} ({expiry})" for label, expiry in expiring)
        lines.append(f"- Keys expiring within 7 days: {exp}")
    else:
        lines.append("- Keys expiring within 7 days: none")

    lines.append("")
    lines.append(knowledge_health_summary())

    return "\n".join(lines)


def short_summary(days: int = 7) -> str:
    """A one-line, TTS-friendly health summary — same underlying counts as
    _build_summary(), phrased as a spoken sentence instead of a labeled
    text block. Built for a voice-triggered "run health check" (see
    assistant.py's _run_health_check_now) — no LLM call, so it's fast and
    free, and short enough to actually say out loud instead of reading
    the full written report a text interface gets."""
    error_count = _count_log_errors()
    unfulfilled_total = sum(_recent_request_categories(days).values())
    llm_total = sum(_recent_llm_calls(days).values())
    expiring = key_status.expiring_within(7)

    parts = [
        f"{error_count} app error{'s' if error_count != 1 else ''}",
        f"{unfulfilled_total} unfulfilled request{'s' if unfulfilled_total != 1 else ''}",
        f"{llm_total} LLM call{'s' if llm_total != 1 else ''}",
    ]
    if expiring:
        parts.append(f"{len(expiring)} key{'s' if len(expiring) != 1 else ''} expiring soon")

    broken_link_count = _count_broken_wikilinks()
    if broken_link_count:
        parts.append(f"{broken_link_count} broken vault link{'s' if broken_link_count != 1 else ''}")

    return f"This week: {', '.join(parts)}."


def _count_broken_wikilinks() -> int:
    """Just the number, for short_summary()'s one-liner -- re-derives from
    the same scan as knowledge_health_summary() rather than parsing that
    function's rendered text for a count."""
    notes = _iter_vault_notes()
    notes_by_stem = {p.stem.lower(): p for p in notes}
    count = 0
    for note in notes:
        try:
            text = note.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _WIKILINK_RE.finditer(text):
            target = match.group(1).strip().lower()
            if target.endswith(".md"):
                target = target[:-3]
            if target not in notes_by_stem:
                count += 1
    return count


def _log_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "log" / "health-checks.md"


def _append_report(report: str) -> None:
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(report + "\n\n---\n\n")
    except OSError as e:
        logger.error(f"Failed to write health check log: {e}")


def _marker_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "state" / "health-check.md"


def _write_marker(status: str) -> None:
    metadata = {
        "id": "health-check-marker",
        "type": "marker",
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    body = "\n# Health Check\n\nRead-only marker — the real report lives in sunny-vault/log/health-checks.md.\n"
    content = vault_io.serialize_frontmatter(metadata, body, _STATE_FIELD_ORDER)
    vault_io.atomic_write_text(_marker_path(), content)


_post_fn: Optional[Callable[[str], Awaitable[None]]] = None


def set_post_fn(fn: Optional[Callable[[str], Awaitable[None]]]) -> None:
    """Registered once at startup (see main.py, right after the Discord bot
    is built) so run_weekly_health_check() posts the same way whether it
    was triggered by the scheduled Sunday loop or an on-demand "run health
    check" from assistant.py -- one registration instead of threading a
    Discord-specific callback through assistant.py's otherwise interface-
    agnostic routing (the same trade already made for TaskEngine.on_change)."""
    global _post_fn
    _post_fn = fn


async def run_weekly_health_check() -> str:
    """Gathers the week's summary, asks Claude to write it up, appends it to
    the vault log, flips the marker to unacknowledged, and posts it via
    the registered post fn (see set_post_fn), if any. Always logs locally
    even if nothing's registered or posting fails (e.g. Discord isn't
    configured) — the check itself doesn't depend on Discord being
    available."""
    summary = _build_summary()
    llm_report = await ask_claude(prompt=summary, model="haiku", purpose="weekly_health_check")

    header = f"# Weekly Health Check — {date.today().isoformat()}\n\n"
    report = header + (llm_report if llm_report else f"(LLM unavailable this week — raw summary below)\n\n{summary}")

    _append_report(report)
    _write_marker("unacknowledged")

    if _post_fn is not None:
        try:
            await _post_fn(report)
        except Exception as e:
            logger.error(f"Failed to post health check report: {e}")

    return report


def pending_notice() -> Optional[str]:
    """A one-line nudge for the morning briefing if there's an
    unacknowledged report, else None. Persists across days on purpose —
    morning briefings are manual-trigger-only in this app, so a same-day
    check would silently lose the reminder if "morning" isn't said on the
    Sunday the check ran."""
    path = _marker_path()
    if not path.exists():
        return None
    try:
        metadata, _body = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if metadata.get("status") == "unacknowledged":
        return 'There\'s a health check report waiting — say "health check" to see it.'
    return None


def latest_report() -> Optional[str]:
    """The most recent health check report, or None if none exists yet.
    Flips the marker to acknowledged — this is the "check it" action the
    briefing nudge points at."""
    path = _log_path()
    if not path.exists():
        return None
    entries = [e.strip() for e in path.read_text(encoding="utf-8").split("---") if e.strip()]
    if not entries:
        return None

    if _marker_path().exists():
        _write_marker("acknowledged")

    return entries[-1]
