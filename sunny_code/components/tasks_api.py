"""API routes for task management."""

import logging
from fastapi import APIRouter, Query
from pathlib import Path

from sunny_code.config import get_settings
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine

logger = logging.getLogger(__name__)


def create_tasks_router() -> APIRouter:
    """Create task management API routes."""
    router = APIRouter(prefix="/tasks")

    # Initialize database and engine
    settings = get_settings()
    db = TaskDB(settings.project_root / "tasks.db")
    engine = TaskEngine(db)

    @router.post("/command")
    async def execute_command(cmd: str = Query(..., description='Task command, e.g. "add buy milk to my tasks" or "show my tasks"')):
        """Execute a task command."""
        success, message = await engine.execute_command(cmd)
        return {
            "success": success,
            "message": message,
            "command": cmd,
        }

    @router.get("/list")
    async def list_tasks(
        status: str = Query(None, description="Filter by status: open, in_progress, done"),
        tag: str = Query(None, description="Filter by tag"),
        priority: int = Query(None, description="Minimum priority (1-5)"),
    ):
        """List tasks with optional filters."""
        if status:
            tasks = db.get_tasks_by_status(status)
        elif tag:
            tasks = db.get_tasks_by_tag(tag)
        elif priority:
            tasks = db.get_high_priority_tasks(priority)
        else:
            tasks = db.get_open_tasks()

        return {
            "count": len(tasks),
            "tasks": tasks,
        }

    @router.get("/open")
    async def get_open_tasks():
        """Get all open tasks."""
        tasks = db.get_open_tasks()
        return {
            "status": "open",
            "count": len(tasks),
            "tasks": tasks,
        }

    @router.get("/done")
    async def get_done_tasks():
        """Get all completed tasks."""
        tasks = db.get_done_tasks()
        return {
            "status": "done",
            "count": len(tasks),
            "tasks": tasks,
        }

    @router.get("/in-progress")
    async def get_in_progress_tasks():
        """Get all in-progress tasks."""
        tasks = db.get_in_progress_tasks()
        return {
            "status": "in_progress",
            "count": len(tasks),
            "tasks": tasks,
        }

    @router.get("/due-soon")
    async def get_due_soon(days: int = Query(7, description="Days until due")):
        """Get tasks due within N days."""
        tasks = db.get_tasks_due_soon(days)
        return {
            "due_within_days": days,
            "count": len(tasks),
            "tasks": tasks,
        }

    @router.get("/high-priority")
    async def get_high_priority(min_priority: int = Query(4, description="Minimum priority (1-5)")):
        """Get high-priority tasks."""
        tasks = db.get_high_priority_tasks(min_priority)
        return {
            "min_priority": min_priority,
            "count": len(tasks),
            "tasks": tasks,
        }

    @router.get("/stats")
    async def get_stats():
        """Get task statistics."""
        stats = db.get_stats()
        return stats

    @router.get("/dashboard")
    async def get_dashboard():
        """Get formatted task dashboard."""
        dashboard = engine.format_dashboard()
        return {
            "dashboard": dashboard,
        }

    @router.get("/{task_id}")
    async def get_task(task_id: str):
        """Get a specific task by ID."""
        task = db.get_task(task_id)
        if not task:
            return {"error": f"Task not found: {task_id}"}
        return task

    return router
