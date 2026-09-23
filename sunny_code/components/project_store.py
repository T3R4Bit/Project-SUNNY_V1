"""Projects as containers, not scaffolded documents.

WHAT WAS HERE BEFORE
--------------------
project_engine.py asked three questions, made one LLM call, wrote a
single overview file and was finished. Nothing referred to a project
again: no status, no phase, no tasks, no context, no way to ask "what am
I actually working on". It generated a document and called that a
project system.

WHAT A PROJECT IS NOW
---------------------
A folder with a status, a phase, and everything in it readable as one
body of context -- closer to how Claude's own projects work, where you
pick a project and the conversation already knows what it is about.

  data/projects/<slug>/
    project.md       frontmatter (status, phase, dates) + description
    instructions.md  human-owned; how Sunny should behave on THIS project
    plan.md          milestones and timeline
    critique.md      the red-team pass over the plan
    research/*.md    comparisons and findings
    <anything else>  dropped in by hand, still picked up as context

Every readable file in the folder is cross-referenced into the prompt by
context(), so a note filed by hand in Obsidian is available to Sunny in
the next message without any import step. That property is the whole
point: the vault is the interface.

THREE STATUSES, ONE FIELD
-------------------------
active / long-term / someday, chosen deliberately over a two-dimensional
horizon-x-state model. Two fields describe reality more precisely -- an
ongoing project can also be the one you are on today -- but every item
then needs two decisions to file and two to find, and the filing gets
skipped. One field that is occasionally imprecise beats two fields that
go stale. When a long-term project is what you are on right now, it is
`active`; when you step off it, it goes back to `long-term`.

PHASES ARE NOT STATUSES
-----------------------
Status is "do I care about this right now". Phase is "how far along is
the thinking". They move independently: a `someday` project can sit at
`refined` with a finished plan waiting for time, and an `active` one can
still be at `idea`. Collapsing them would mean starting work on
something forced it to look planned.

ARCHIVING
---------
A finished project should leave the list, not sit in it at `done`
forever. archive() moves the folder to data/projects/archive/ and records
`archived` as the status -- the same move-the-folder convention tasks_db
uses, which keeps the projects directory readable when browsing the vault
in Obsidian.

It stays fully readable: get(), context() and resolve() all fall back to
the archive, so asking about something finished still works. Archiving
removes it from the list, it does not hide it. The phase records WHY it
left -- `done` for shipped, `parked` for abandoned -- because a year
later that is the distinction you actually want.
"""

import logging
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Do I care about this right now?
ACTIVE = "active"
LONG_TERM = "long-term"
SOMEDAY = "someday"
STATUSES = [ACTIVE, LONG_TERM, SOMEDAY]

STATUS_HELP = {
    ACTIVE: "on it now",
    LONG_TERM: "ongoing, no end date",
    SOMEDAY: "later, not started",
}

# Deliberately NOT in STATUSES. Archived is not a fourth kind of live
# project competing with the other three -- it is "no longer in the list
# at all". Putting it in STATUSES would make it appear in every filter
# dropdown and every summary, which is the opposite of what archiving is
# for. It is recorded in the file AND expressed by the folder's location,
# so the two can be checked against each other.
ARCHIVED = "archived"
ARCHIVE_DIR = "archive"

# How far along is the thinking? Ordered, and the order is the framework:
# nothing reaches `building` without having been attacked at `critique`
# first, which is the point of having a phase list at all rather than a
# free-text field.
IDEA = "idea"
PLANNING = "planning"
CRITIQUE = "critique"
REFINED = "refined"
BUILDING = "building"
DONE = "done"
PARKED = "parked"
PHASES = [IDEA, PLANNING, CRITIQUE, REFINED, BUILDING, DONE, PARKED]

PHASE_HELP = {
    IDEA: "captured, not planned yet",
    PLANNING: "first plan drafted",
    CRITIQUE: "plan attacked, risks found",
    REFINED: "plan revised against the critique",
    BUILDING: "being worked on",
    DONE: "finished",
    PARKED: "stopped on purpose",
}

# Files with reserved meaning. Everything else in the folder is treated
# as free context.
PROJECT_FILE = "project.md"
INSTRUCTIONS_FILE = "instructions.md"
PLAN_FILE = "plan.md"
CRITIQUE_FILE = "critique.md"

# Ceiling on how much project context is injected into one prompt. A
# project folder grows without bound -- a year of research notes would
# silently push the actual question out of the useful part of the
# context window, and the failure would look like Sunny ignoring you
# rather than like a budget being hit.
CONTEXT_BUDGET_CHARS = 12000

_READABLE_SUFFIXES = {".md", ".txt", ".markdown"}


def _projects_dir() -> Path:
    return get_settings().project_root / "sunny-vault" / "data" / "projects"


def _archive_dir() -> Path:
    return _projects_dir() / ARCHIVE_DIR


def _dir_for(slug: str) -> Path:
    """Where this project lives, live or archived.

    Checks the live folder first and falls back to the archive, so get(),
    context() and resolve() keep working on an archived project. Archiving
    hides something from the list; it does not make it unreadable, and
    "where did my finished project go" is a worse outcome than a slightly
    longer lookup.
    """
    live = _projects_dir() / slug
    if live.exists():
        return live
    archived = _archive_dir() / slug
    if archived.exists():
        return archived
    return live  # the path a new project would take


def is_archived(slug: str) -> bool:
    return (_archive_dir() / slug).exists()


def _unique_slug(name: str) -> str:
    base = vault_io.slugify(name) or "project"
    slug, n = base, 2
    # _dir_for checks the archive too, so a new project cannot reuse the
    # slug of an archived one -- unarchiving it later would otherwise
    # collide with a live folder of the same name.
    while _dir_for(slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create(name: str, description: str = "", status: str = ACTIVE,
           phase: str = IDEA) -> Optional[str]:
    """Make a project. Returns its slug, or None if the name was empty."""
    name = (name or "").strip()
    if not name:
        return None

    status = status if status in STATUSES else ACTIVE
    phase = phase if phase in PHASES else IDEA

    slug = _unique_slug(name)
    # Explicitly the live directory: _dir_for falls back to the archive,
    # which is right for reads and wrong for creating something new.
    folder = _projects_dir() / slug
    folder.mkdir(parents=True, exist_ok=True)

    vault_io.atomic_write_text(
        folder / PROJECT_FILE,
        vault_io.serialize_frontmatter(
            {
                "id": slug,
                "name": name,
                "type": "project",
                "status": status,
                "phase": phase,
                "created": date.today().isoformat(),
                "updated": _now(),
            },
            f"# {name}\n\n{description.strip()}\n" if description.strip()
            else f"# {name}\n\n_No description yet._\n",
            ["id", "name", "type", "status", "phase", "created", "updated"],
        ),
    )
    logger.info(f"Project created: {slug} ({status}/{phase})")
    return slug


def get(slug: str) -> Optional[Dict]:
    """One project's metadata plus its description body, or None."""
    path = _dir_for(slug) / PROJECT_FILE
    if not path.exists():
        return None
    try:
        meta, body = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Project {slug} unreadable: {e}")
        return None

    meta = meta or {}
    return {
        "slug": slug,
        "name": meta.get("name", slug),
        "status": meta.get("status", ACTIVE),
        "phase": meta.get("phase", IDEA),
        "created": str(meta.get("created", "")),
        "updated": str(meta.get("updated", "")),
        "description": (body or "").strip(),
        "path": str(_dir_for(slug)),
    }


def all_projects(status: Optional[str] = None,
                 phase: Optional[str] = None,
                 include_archived: bool = False) -> List[Dict]:
    """Every project, newest-updated first, optionally filtered.

    Reads the folder rather than an index, for the same reason
    memory_store does: the vault is the source of truth, so a project
    folder deleted or renamed by hand in Obsidian is immediately correct
    here instead of lingering in a database nobody thought to update.
    """
    root = _projects_dir()
    if not root.exists():
        return []

    folders = [f for f in root.iterdir() if f.is_dir() and f.name != ARCHIVE_DIR]
    if include_archived and _archive_dir().exists():
        folders += [f for f in _archive_dir().iterdir() if f.is_dir()]

    out = []
    for folder in folders:
        project = get(folder.name)
        if project is None:
            continue
        if status and project["status"] != status:
            continue
        if phase and project["phase"] != phase:
            continue
        out.append(project)

    out.sort(key=lambda p: p.get("updated") or "", reverse=True)
    return out


def archived_projects() -> List[Dict]:
    """Finished and abandoned projects, newest first."""
    root = _archive_dir()
    if not root.exists():
        return []
    out = [get(f.name) for f in root.iterdir() if f.is_dir()]
    out = [p for p in out if p is not None]
    out.sort(key=lambda p: p.get("updated") or "", reverse=True)
    return out


def archive(slug: str, reason: str = DONE) -> bool:
    """Move a project out of the active list. True if it moved.

    `reason` is the phase to record -- `done` for finished, `parked` for
    stopped on purpose. The distinction is kept because "I shipped it" and
    "I gave up on it" are different facts about a project, and a year later
    that is exactly what you want to know when looking back.

    The folder moves rather than the project merely being flagged, so the
    projects directory stays readable in Obsidian. Same convention as
    tasks_db's archive/.
    """
    if is_archived(slug):
        return False
    source = _projects_dir() / slug
    if not source.exists():
        return False

    if reason not in (DONE, PARKED):
        reason = DONE
    # Record the state BEFORE moving: update() resolves the path itself,
    # and doing it in this order means a failed move leaves a project
    # that is merely mislabelled rather than one that has vanished.
    update(slug, phase=reason)

    destination = _archive_dir() / slug
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        logger.error(f"Archive collision for {slug}, refusing to overwrite")
        return False

    shutil.move(str(source), str(destination))
    _set_status_raw(slug, ARCHIVED)
    logger.info(f"Project archived: {slug} ({reason})")
    return True


def unarchive(slug: str, status: str = ACTIVE) -> bool:
    """Bring an archived project back to the live list."""
    if not is_archived(slug):
        return False
    if status not in STATUSES:
        status = ACTIVE

    source = _archive_dir() / slug
    destination = _projects_dir() / slug
    if destination.exists():
        logger.error(f"Cannot unarchive {slug}: a live project already has that name")
        return False

    shutil.move(str(source), str(destination))
    _set_status_raw(slug, status)
    logger.info(f"Project unarchived: {slug} -> {status}")
    return True


def _set_status_raw(slug: str, status: str) -> None:
    """Write `status` without the STATUSES validation update() applies.

    Needed because ARCHIVED is deliberately not a member of STATUSES, so
    update() rejects it -- which is the correct behaviour for a caller
    passing user input, and the wrong behaviour for archive() itself.
    """
    path = _dir_for(slug) / PROJECT_FILE
    if not path.exists():
        return
    try:
        meta, body = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not set status on {slug}: {e}")
        return
    meta = dict(meta or {})
    meta["status"] = status
    meta["updated"] = _now()
    vault_io.atomic_write_text(path, vault_io.serialize_frontmatter(
        meta, body or "",
        ["id", "name", "type", "status", "phase", "created", "updated"]))


def update(slug: str, **fields) -> bool:
    """Change metadata and/or the description body. True if written."""
    path = _dir_for(slug) / PROJECT_FILE
    if not path.exists():
        return False
    try:
        meta, body = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Project {slug} unreadable, not updating: {e}")
        return False

    meta = dict(meta or {})
    if "status" in fields:
        if fields["status"] not in STATUSES:
            return False
        meta["status"] = fields["status"]
    if "phase" in fields:
        if fields["phase"] not in PHASES:
            return False
        meta["phase"] = fields["phase"]
    if "name" in fields and fields["name"]:
        meta["name"] = fields["name"]
    if "description" in fields:
        name = meta.get("name", slug)
        body = f"# {name}\n\n{fields['description'].strip()}\n"

    meta["updated"] = _now()
    vault_io.atomic_write_text(
        path,
        vault_io.serialize_frontmatter(
            meta, body or "",
            ["id", "name", "type", "status", "phase", "created", "updated"],
        ),
    )
    return True


def write_file(slug: str, filename: str, content: str) -> Optional[Path]:
    """Write a file into the project folder. Returns the path, or None
    when the project doesn't exist or the name escapes the folder."""
    folder = _dir_for(slug)
    if not folder.exists():
        return None

    # A filename from an LLM or a chat message must not be able to write
    # outside the project -- "../../.env" is the obvious case and it costs
    # one line to make impossible.
    safe = re.sub(r"[^A-Za-z0-9._/-]", "-", filename).lstrip("/")
    target = (folder / safe).resolve()
    try:
        target.relative_to(folder.resolve())
    except ValueError:
        logger.error(f"Refusing to write outside project {slug}: {filename!r}")
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    vault_io.atomic_write_text(target, content)
    update(slug)  # touch `updated` so the project sorts to the top
    return target


def read_file(slug: str, filename: str) -> Optional[str]:
    path = _dir_for(slug) / filename
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def files(slug: str) -> List[Path]:
    """Every readable file in the project, shallowest first.

    Ordering matters because context() truncates at a budget: the files
    at the top of the folder are the ones a person put there on purpose,
    and research notes nested a level down are the ones that can be cut
    without losing the thread.
    """
    folder = _dir_for(slug)
    if not folder.exists():
        return []
    found = [p for p in folder.rglob("*")
             if p.is_file() and p.suffix.lower() in _READABLE_SUFFIXES]
    found.sort(key=lambda p: (len(p.relative_to(folder).parts), p.name))
    return found


def context(slug: str, budget: int = CONTEXT_BUDGET_CHARS) -> str:
    """Everything in the project folder, as one prompt section.

    This is what makes a project a container rather than a label: ask
    about it and Sunny has read the description, the plan, the critique
    and whatever notes are sitting in the folder -- including ones added
    by hand in Obsidian, with no import step, because the folder IS the
    database.

    Returns "" when there is nothing, so callers can concatenate
    unconditionally.
    """
    project = get(slug)
    if project is None:
        return ""

    parts = [
        f"PROJECT: {project['name']}",
        f"Status: {project['status']} ({STATUS_HELP.get(project['status'], '')})  ·  "
        f"Phase: {project['phase']} ({PHASE_HELP.get(project['phase'], '')})",
    ]

    used = sum(len(p) for p in parts)
    skipped = []
    for path in files(slug):
        if path.name == PROJECT_FILE:
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue

        rel = path.relative_to(_dir_for(slug))
        block = f"\n--- {rel} ---\n{text}"
        if used + len(block) > budget:
            skipped.append(str(rel))
            continue
        parts.append(block)
        used += len(block)

    if project["description"]:
        parts.insert(2, f"\n{project['description']}")

    if skipped:
        # Named rather than silently dropped: "Sunny didn't know about the
        # research note" is a bug report, and this turns it into a visible
        # budget decision instead.
        parts.append(f"\n[not included, context budget: {', '.join(skipped)}]")

    return "\n".join(parts) + "\n\n"


def instructions(slug: str) -> str:
    """Per-project custom instructions, or "".

    Human-owned, exactly like personality.md -- Sunny reads this and
    never writes it, so it can't become a file that both a person and a
    server process edit. That rule is what keeps the vault out of the
    sync-conflict class.
    """
    text = read_file(slug, INSTRUCTIONS_FILE)
    return (text or "").strip()


def resolve(query: str) -> Optional[Dict]:
    """Find a project by slug, exact name, or unambiguous prefix.

    Returns None when nothing matches OR when several do -- guessing
    between two projects is worse than asking, because the wrong guess
    silently files work under the wrong thing.
    """
    query = (query or "").strip().lower()
    if not query:
        return None

    # Live projects first, archived second. Archived ones have to be
    # findable at all -- "unarchive <name>" cannot work otherwise, and
    # asking about finished work is a normal thing to do -- but a live
    # project always wins a tie, because that is far more likely to be
    # what was meant.
    projects = all_projects() + archived_projects()
    for project in projects:
        if project["slug"] == query or project["name"].lower() == query:
            return project

    hits = [p for p in projects
            if p["slug"].startswith(query) or p["name"].lower().startswith(query)]
    if len(hits) == 1:
        return hits[0]

    hits = [p for p in projects if query in p["name"].lower()]
    return hits[0] if len(hits) == 1 else None


# Which project each chat session is scoped to. In memory, not on disk:
# focus is a property of a conversation, not of the project, and it should
# not survive a restart -- coming back to Sunny hours later and silently
# still being "inside" a project is a worse failure than having to say
# which one again.
_focus: Dict[str, str] = {}


def set_focus(session_id: str, slug: Optional[str]) -> bool:
    """Scope a session to a project, or clear it with slug=None."""
    if slug is None:
        _focus.pop(session_id, None)
        return True
    if get(slug) is None:
        return False
    _focus[session_id] = slug
    return True


def get_focus(session_id: str) -> Optional[Dict]:
    """The project this session is scoped to, if any.

    Re-reads the project rather than returning a cached copy, so a folder
    deleted in Obsidian mid-conversation stops being injected instead of
    lingering until restart.
    """
    slug = _focus.get(session_id)
    if slug is None:
        return None
    project = get(slug)
    if project is None:
        _focus.pop(session_id, None)
        return None
    return project


def focus_context(session_id: str) -> str:
    """Project context for this session's prompt, or "".

    Callers concatenate unconditionally, same contract as
    memory_store.format_for_prompt.
    """
    project = get_focus(session_id)
    if project is None:
        return ""
    parts = [context(project["slug"])]
    custom = instructions(project["slug"])
    if custom:
        parts.append(f"PROJECT INSTRUCTIONS (follow these):\n{custom}\n\n")
    return "".join(parts)


def summary_lines(show_archived_count: bool = True) -> List[str]:
    """One line per live project, grouped by status, for chat and briefings.

    Archived projects are counted but not listed. The count exists so the
    archive is discoverable -- an archive nobody remembers is the same as
    having deleted the work.
    """
    out = []
    for status in STATUSES:
        group = all_projects(status=status)
        if not group:
            continue
        out.append(f"{status.upper()} ({STATUS_HELP[status]})")
        for project in group:
            out.append(f"  · {project['name']} — {project['phase']}")

    if show_archived_count:
        archived = archived_projects()
        if archived:
            done = sum(1 for p in archived if p["phase"] == DONE)
            parked = len(archived) - done
            bits = []
            if done:
                bits.append(f"{done} finished")
            if parked:
                bits.append(f"{parked} parked")
            out.append("")
            out.append(f"ARCHIVED — {', '.join(bits)} "
                       '(say "archived" to see them)')
    return out
