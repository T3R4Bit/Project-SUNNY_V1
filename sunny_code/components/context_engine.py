"""Layer 3 context engine -- personal-assistant-vision.md section 10: "a
compact structured state instead of sending full history to an LLM."
build_context() is a pure read-time aggregator over data sources that
already exist (tasks, lists, today's calendar, real project folders) --
no new storage of its own, nothing here is cached or persisted. Call it
right before an LLM call that needs "what's going on right now" cheaply,
instead of that caller re-querying each source itself or (worse) dumping
full history into the prompt.

No real caller yet -- built ahead of the first feature that needs it, same
as vault_permissions.py/suggestion_tracker.py above.
"""

import asyncio
from typing import Dict, List

from sunny_code.components import google_calendar
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.config import get_settings


def _active_project_names() -> List[str]:
    projects_dir = get_settings().project_root / "sunny-vault" / "projects"
    if not projects_dir.exists():
        return []
    return sorted(p.name for p in projects_dir.iterdir() if p.is_dir())


async def build_context(tasks_engine: TaskEngine, list_engine: ListEngine) -> Dict:
    """Assembles the compact state block: open tasks (title/tag/priority
    only, not full descriptions -- this is meant to stay small), every
    list's name and item count, today's calendar events (title/time only),
    and real project folder names. Any source that's unavailable (Calendar
    not connected) contributes an empty list rather than raising -- same
    fail-quiet contract as every other integration in this app, since a
    partial context is still useful, a crashed one isn't."""
    open_tasks = tasks_engine.db.get_all_tasks(status="open")
    lists = list_engine.db.get_all_lists()

    events = await asyncio.to_thread(google_calendar.get_events)
    if events is None:
        events = []

    return {
        "open_tasks": [
            {"title": t["title"], "tag": t["tag"], "priority": t["priority"]} for t in open_tasks
        ],
        "lists": [
            {"name": lst["name"], "item_count": len(list_engine.db.get_items(lst["id"]))} for lst in lists
        ],
        "todays_events": [{"title": e["title"], "time": e["time"]} for e in events],
        "active_projects": _active_project_names(),
    }


def format_context(context: Dict) -> str:
    """A compact plain-text rendering of build_context()'s dict, sized for
    dropping straight into an LLM prompt -- the actual "instead of sending
    full history" payoff. Omits empty sections entirely rather than
    printing "none" for each, to stay as small as possible."""
    lines = []

    if context["open_tasks"]:
        lines.append("Open tasks:")
        for t in context["open_tasks"]:
            lines.append(f"- [{t['tag']}] P{t['priority']}: {t['title']}")

    if context["lists"]:
        lines.append("Lists:")
        for lst in context["lists"]:
            lines.append(f"- {lst['name']} ({lst['item_count']} items)")

    if context["todays_events"]:
        lines.append("Today's calendar:")
        for e in context["todays_events"]:
            lines.append(f"- {e['time']}: {e['title']}")

    if context["active_projects"]:
        lines.append("Active projects: " + ", ".join(context["active_projects"]))

    return "\n".join(lines) if lines else "(nothing active right now)"
