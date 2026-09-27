"""HTTP access to the project container.

Projects have been chat-only since they were built: `projects`, `project
<name>`, `plan`, `critique`. That works when you are already talking to
Sunny and is useless when you want to glance at what is live, or read a
critique properly rather than as a chat message that scrolled away.

READ-MOSTLY, ON PURPOSE
-----------------------
The write surface here is deliberately small: status, phase, archive,
unarchive. Those are the things you change while *looking* at a list --
"that's not active any more" is a judgement you make when you see the
list, not something you open a page to do.

Creating projects, planning and critiquing stay in chat. They need a
conversation (a description, notes, a question) and a form would be a
worse version of the thing that already works. `plan` and `critique` also
take tens of seconds against the LLM, which is a bad fit for a page
request and a good fit for a chat message.

FILES ARE SERVED RENDERED, NOT RAW
----------------------------------
A project folder is markdown by design, so the detail endpoint returns
each file's text and lets the client render it. No HTML is generated
here -- the dashboard already has markdown handling, and generating
markup server-side would mean two renderers to keep in step.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sunny_code.components import project_store

logger = logging.getLogger(__name__)

# Per-file cap for the detail view. A research folder can grow without
# bound and a page does not need the whole of it to be useful; the
# response says when it truncated so the UI can point at the vault.
MAX_FILE_CHARS = 40000


class StatusChange(BaseModel):
    status: Optional[str] = None
    phase: Optional[str] = None


class ArchiveRequest(BaseModel):
    # done = shipped, parked = stopped on purpose. Kept distinct because a
    # year later that is the distinction worth having.
    reason: str = "done"


def _summary(project: Dict) -> Dict:
    """List-view shape. Deliberately does NOT include file contents --
    the list renders 10+ projects and reading every folder to draw it
    would make the page cost proportional to everything ever filed."""
    slug = project["slug"]
    files = [f.name for f in project_store.files(slug)
             if f.name != project_store.PROJECT_FILE]
    return {
        "slug": slug,
        "name": project["name"],
        "status": project["status"],
        "phase": project["phase"],
        "created": project["created"],
        "updated": project["updated"],
        "archived": project_store.is_archived(slug),
        # What exists in the folder, so the list can show "has a plan,
        # has a critique" without reading either.
        "has_plan": project_store.PLAN_FILE in files,
        "has_critique": project_store.CRITIQUE_FILE in files,
        "has_instructions": project_store.INSTRUCTIONS_FILE in files,
        "file_count": len(files),
    }


def _tasks_for(slug: str) -> List[Dict]:
    """Open tasks belonging to this project, soonest due first.

    Built here rather than passed in because the router has no engine
    handle -- and reading the vault directly is what tasks_db does
    anyway, so there is no state to be out of step with.

    Detail only. The list view does NOT call this: it renders every
    project, and scanning the whole task tree per card would make the
    page cost proportional to everything ever filed.
    """
    from sunny_code.components.tasks_db import TaskDB
    from sunny_code.config import get_settings

    try:
        db = TaskDB(get_settings().project_root / "sunny-vault" / "data" / "state" / "tasks")
        return [
            {"id": t["id"], "title": t["title"], "due_date": t.get("due_date"),
             "tag": t.get("tag")}
            for t in db.get_tasks_by_project(slug, status="open")
        ]
    except Exception as e:
        # A project page is still worth showing without its task list.
        logger.warning(f"Could not read tasks for {slug}: {e}")
        return []


def create_project_router() -> APIRouter:
    router = APIRouter()

    @router.get("/projects")
    async def list_projects(include_archived: bool = False) -> dict:
        """Live projects grouped by status, plus an archive count.

        Grouped server-side because the grouping IS the model -- three
        statuses in a fixed order. A client sorting a flat list would have
        to re-encode that order and could disagree with the chat view.
        """
        groups = []
        for status in project_store.STATUSES:
            projects = project_store.all_projects(status=status)
            if not projects and not include_archived:
                # Empty groups are still returned, so the UI can show
                # "nothing active" rather than silently omitting the row.
                pass
            groups.append({
                "status": status,
                "help": project_store.STATUS_HELP[status],
                "projects": [_summary(p) for p in projects],
            })

        archived = project_store.archived_projects()
        return {
            "groups": groups,
            "archived_count": len(archived),
            "archived": [_summary(p) for p in archived] if include_archived else [],
            "statuses": project_store.STATUSES,
            "phases": project_store.PHASES,
            "phase_help": project_store.PHASE_HELP,
        }

    @router.get("/projects/{slug}")
    async def project_detail(slug: str) -> dict:
        """One project with every readable file in its folder.

        Includes archived projects: archiving hides something from the
        list, it does not make it unreadable, and a finished project is
        exactly what you want to read back later.
        """
        project = project_store.get(slug)
        if project is None:
            raise HTTPException(status_code=404, detail=f"No project {slug!r}")

        files: List[Dict] = []
        for path in project_store.files(slug):
            if path.name == project_store.PROJECT_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning(f"Could not read {path}: {e}")
                continue
            truncated = len(text) > MAX_FILE_CHARS
            files.append({
                "path": str(path.relative_to(project_store._dir_for(slug))).replace("\\", "/"),
                "name": path.name,
                "text": text[:MAX_FILE_CHARS],
                "truncated": truncated,
                "bytes": path.stat().st_size,
            })

        return {
            **_summary(project),
            "description": project["description"],
            "path": project["path"],
            "files": files,
            "tasks": _tasks_for(slug),
        }

    @router.post("/projects/{slug}/status")
    async def set_status(slug: str, body: StatusChange) -> dict:
        """Change status and/or phase.

        project_store.update() validates both against STATUSES/PHASES and
        returns False rather than writing something off-list, so a bad
        value is a 400 here instead of a phantom status in the vault.
        """
        if project_store.get(slug) is None:
            raise HTTPException(status_code=404, detail=f"No project {slug!r}")

        changes = {}
        if body.status is not None:
            changes["status"] = body.status
        if body.phase is not None:
            changes["phase"] = body.phase
        if not changes:
            raise HTTPException(status_code=400, detail="Nothing to change")

        if not project_store.update(slug, **changes):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value. status must be one of {project_store.STATUSES}, "
                       f"phase one of {project_store.PHASES}",
            )
        return {"ok": True, **_summary(project_store.get(slug))}

    @router.post("/projects/{slug}/archive")
    async def archive(slug: str, body: ArchiveRequest) -> dict:
        if project_store.get(slug) is None:
            raise HTTPException(status_code=404, detail=f"No project {slug!r}")
        if not project_store.archive(slug, body.reason):
            raise HTTPException(status_code=409,
                                detail="Already archived, or the folder could not be moved")
        return {"ok": True, **_summary(project_store.get(slug))}

    @router.post("/projects/{slug}/unarchive")
    async def unarchive(slug: str, body: StatusChange) -> dict:
        if not project_store.is_archived(slug):
            raise HTTPException(status_code=409, detail="Not archived")
        if not project_store.unarchive(slug, body.status or project_store.ACTIVE):
            raise HTTPException(status_code=409,
                                detail="A live project already has that name")
        return {"ok": True, **_summary(project_store.get(slug))}

    return router
