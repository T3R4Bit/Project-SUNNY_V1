"""Task management engine — combines DB, parsing, and formatting."""

import logging
import re
from typing import Dict, List, Optional, Tuple

from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_parser import TaskCommandParser
from sunny_code.components.request_log import log_unfulfilled

logger = logging.getLogger(__name__)


class TaskEngine:
    """High-level task management with command execution."""

    def __init__(self, db: TaskDB):
        self.db = db
        self.parser = TaskCommandParser()
        # Optional async callable(message: str), invoked after a successful
        # add/update/delete with that command's result text — lets other
        # interfaces react to a change regardless of which interface made it.
        # The Discord bot uses this for both the dashboard refresh (ignores
        # the message) and the #task-updates channel log (uses it). Not
        # set = no-op.
        self.on_change = None

    async def execute_command(self, command: str, source: str = None) -> Tuple[bool, str]:
        """Execute a task command and return (success, message). `source` (web/discord/api)
        is only used for "add" — it's recorded on the created task for future reference."""
        try:
            cmd_type, success, data = self.parser.parse_command(command)

            if not success:
                error = data.get("error", "Invalid command")
                log_unfulfilled("task_command", f'"{command}" — {error}')
                return False, f"❌ {error}"

            if cmd_type == "add":
                result = await self._execute_add(data, source=source)
            elif cmd_type == "update":
                result = await self._execute_update(data)
            elif cmd_type == "delete":
                result = await self._execute_delete(data)
            elif cmd_type == "list":
                result = await self._execute_list(data)
            else:
                result = (False, "❌ Unknown command type")

            success, message = result
            if not success:
                log_unfulfilled("task_command", f'"{command}" — {message}')
            elif cmd_type in ("add", "update", "delete") and self.on_change:
                try:
                    await self.on_change(message)
                except Exception as e:
                    logger.error(f"on_change callback failed: {e}")
            return result

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            log_unfulfilled("task_command", f'"{command}" — {e}')
            return False, f"❌ Error: {str(e)}"

    def _match_by_title(self, identifier: str) -> Optional[Tuple[Optional[str], Optional[str]]]:
        """Try to resolve an identifier against task titles. Returns (task_id, None) on
        a clean match, (None, error) if it's ambiguous, or plain None if nothing matched
        at all (so the caller can retry with a different identifier)."""
        identifier_lower = identifier.lower()
        all_tasks = self.db.get_all_tasks()

        exact = [t for t in all_tasks if t["title"].lower() == identifier_lower]
        if len(exact) == 1:
            return exact[0]["id"], None
        if len(exact) > 1:
            return None, f'You have {len(exact)} tasks titled "{identifier}" — rename one so they\'re not identical, then try again'

        partial = [t for t in all_tasks if identifier_lower in t["title"].lower()]
        if len(partial) == 1:
            return partial[0]["id"], None
        if len(partial) > 1:
            titles = ", ".join(f'"{t["title"]}"' for t in partial[:5])
            return None, f'That matches multiple tasks: {titles} — try the exact title'

        return None

    def _resolve_task_id(self, identifier: str) -> Tuple[Optional[str], Optional[str]]:
        """Resolve a task ID or a title (natural-language commands don't require an
        exact ID) to a real task ID. Returns (task_id, error_message)."""
        identifier = identifier.strip().strip('"\'')

        # Try as a literal ID first — this is what legacy !task commands always pass.
        if self.db.get_task(identifier):
            return identifier, None

        result = self._match_by_title(identifier)
        if result is not None:
            return result

        # Retry with a leading "task"/"the task"/"my task" filler word stripped —
        # handles phrasing like "finish task make pizza" meaning the task "make pizza".
        filler_stripped = re.sub(r'^(?:the\s+|my\s+)?task\s+', '', identifier, flags=re.IGNORECASE).strip()
        if filler_stripped and filler_stripped != identifier:
            result = self._match_by_title(filler_stripped)
            if result is not None:
                return result

        return None, f'No task found matching "{identifier}"'

    async def _execute_add(self, data: Dict, source: str = None) -> Tuple[bool, str]:
        """Create a new task."""
        try:
            self.db.create_task(
                title=data["title"],
                tag=data.get("tag", "General"),
                priority=data.get("priority", 3),
                description=data.get("description"),
                due_date=data.get("due_date"),
                source=source,
            )

            message = f"""✅ Task created: {data['title']}
Category: {data.get('tag', 'General')}
Priority: {data.get('priority', 3)}/5"""

            if data.get("due_date"):
                message += f"\nDue: {data['due_date']}"

            return True, message

        except ValueError as e:
            return False, f"❌ {str(e)}"

    async def _execute_update(self, data: Dict) -> Tuple[bool, str]:
        """Update a task field."""
        try:
            task_id, error = self._resolve_task_id(data["task_id"])
            if error:
                return False, f"❌ {error}"

            field = data["field"]
            value = data["value"]

            # Map field names for database
            field_map = {
                "status": "status",
                "priority": "priority",
                "tag": "tag",
                "title": "title",
                "describe": "description",
                "due": "due_date",
            }

            db_field = field_map.get(field, field)

            success = self.db.update_task(task_id, **{db_field: value})

            if not success:
                return False, "❌ Task not found"

            task = self.db.get_task(task_id)
            title = task["title"] if task else value
            field_label = "category" if field == "tag" else field
            return True, f'✅ Updated "{title}" — {field_label} → {value}'

        except ValueError as e:
            return False, f"❌ {str(e)}"

    async def _execute_delete(self, data: Dict) -> Tuple[bool, str]:
        """Delete a task."""
        task_id, error = self._resolve_task_id(data["task_id"])
        if error:
            return False, f"❌ {error}"

        task = self.db.get_task(task_id)
        if not task:
            return False, "❌ Task not found"

        self.db.delete_task(task_id)
        return True, f'✅ Deleted "{task["title"]}"'

    async def _execute_list(self, data: Dict) -> Tuple[bool, str]:
        """List tasks with optional filtering."""
        # Determine which tasks to show
        if data.get("due_soon"):
            tasks = self.db.get_tasks_due_soon(days=7)
            title = "📌 DUE SOON (next 7 days)"
        elif "status" in data:
            tasks = self.db.get_tasks_by_status(data["status"])
            status_names = {"open": "OPEN", "done": "DONE", "in_progress": "IN PROGRESS"}
            title = f"📋 {status_names.get(data['status'], data['status'].upper())}"
        elif "tag" in data:
            tasks = self.db.get_tasks_by_tag(data["tag"])
            title = f"📋 {data['tag'].upper()}"
        elif "min_priority" in data:
            tasks = self.db.get_high_priority_tasks(data["min_priority"])
            title = f"🔴 PRIORITY {data['min_priority']}+"
        else:
            tasks = self.db.get_open_tasks()
            title = "📋 OPEN TASKS"

        if not tasks:
            return True, f"{title}\n(None)"

        # Format tasks
        message = f"{title}\n"
        for task in tasks:
            priority_indicator = "🔴" * task["priority"]
            status_icon = {
                "open": "◯",
                "in_progress": "→",
                "done": "✓",
            }.get(task["status"], "•")

            line = f"{status_icon} [{priority_indicator}] {task['title']} ({task['tag']})"

            if task["due_date"]:
                line += f" (due {task['due_date']})"

            message += f"{line}\n"

        stats = self.db.get_stats()
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Open: {stats['open']} | In Progress: {stats['in_progress']} | Done: {stats['done']}"

        return True, message

    # Known categories get a nice icon; anything else (any custom category the
    # user makes up) falls back to a generic tag icon — no fixed category list.
    _CATEGORY_ICONS = {"School": "🎓", "Motorsports": "🏍️ ", "General": "📝", "Project Ideas": "💡"}

    def format_dashboard(self) -> str:
        """Format complete task dashboard for Discord embed."""
        dashboard = "📋 YOUR TASKS\n"
        dashboard += "━" * 50 + "\n\n"

        # Open tasks grouped by whatever categories actually exist right now —
        # known ones first (stable, familiar order), then custom ones alphabetically.
        all_open = self.db.get_open_tasks()
        tags_dict: Dict[str, List[Dict]] = {}
        for task in all_open:
            tags_dict.setdefault(task["tag"], []).append(task)

        known_order = [t for t in self._CATEGORY_ICONS if t in tags_dict]
        custom_order = sorted(t for t in tags_dict if t not in self._CATEGORY_ICONS)

        for tag in known_order + custom_order:
            tasks = tags_dict[tag]
            emoji = self._CATEGORY_ICONS.get(tag, "🏷️")
            dashboard += f"{emoji} {tag} ({len(tasks)})\n"

            for task in tasks[:3]:  # Show top 3
                priority_bar = "▰" * task["priority"] + "▱" * (5 - task["priority"])
                due_str = f" (due {task['due_date']})" if task["due_date"] else ""
                dashboard += f"  [{priority_bar}] {task['title']}{due_str}\n"

            if len(tasks) > 3:
                dashboard += f"  ... and {len(tasks) - 3} more\n"
            dashboard += "\n"

        # Stats
        stats = self.db.get_stats()
        dashboard += "━" * 50 + "\n"
        dashboard += f"✅ Done: {stats['done']} | ⏳ In Progress: {stats['in_progress']} | 📌 Open: {stats['open']}\n"

        # Due soon
        due_soon = self.db.get_tasks_due_soon(days=7)
        if due_soon:
            dashboard += f"\n⚠️  {len(due_soon)} tasks due this week\n"

        return dashboard
