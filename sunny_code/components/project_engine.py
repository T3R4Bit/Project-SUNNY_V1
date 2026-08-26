"""Creates a new project folder from a short, fixed wizard.

assistant.py collects three answers (name, description, optional starting
sections) using its existing pending-followup mechanism — the same one
"what should the task be called?" uses — then calls scaffold() here once,
with everything already known. This module owns exactly one LLM call (one
round trip, not an open-ended conversation) that drafts a multi-file plan
for the project, and writes it to sunny-vault/projects/<slug>/.

Structured output via a JSON response (not Claude's tool-use/tool-runner
machinery) — this is a single one-shot "give me a files plan" call with no
back-and-forth tool execution needed, so a JSON-shaped prompt is enough
without adding a new tool-calling code path to llm_client.py.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Tuple

from sunny_code.components import instructions, vault_io
from sunny_code.components.llm_client import ask_claude
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# A real content-authoring call, not a quick conversational judgment call —
# worth spending more than the app's default Haiku/short-response budget on,
# unlike the general-chat fallback (see llm_client.py's MODELS/general-chat.md).
# 4096 wasn't enough headroom: a real multi-file plan with "real, useful
# starting content" per project-scaffold.md routinely runs past it and gets
# cut off mid-JSON, which _parse_file_plan then reports as "malformed"
# instead of what actually happened (a length cutoff). Seen in practice on
# a 6-file plan that got cut off mid-file-6 at the old limit.
_SCAFFOLD_MODEL = "sonnet"
_SCAFFOLD_MAX_TOKENS = 8192

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _projects_dir() -> Path:
    return get_settings().project_root / "sunny-vault" / "projects"


def _unique_project_slug(name: str) -> str:
    """Same collision-avoidance idea as tasks_db._unique_slug/lists_db, extended
    from a single file to a directory."""
    base = vault_io.slugify(name)
    slug = base
    n = 2
    while (_projects_dir() / slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _parse_file_plan(raw: str) -> List[dict]:
    """Claude is asked for bare JSON but sometimes wraps it in a markdown
    code fence despite instructions not to — strip that defensively before
    parsing rather than failing on a cosmetic wrapper."""
    cleaned = _JSON_FENCE_RE.sub("", raw.strip()).strip()
    data = json.loads(cleaned)
    files = data["files"]
    if not isinstance(files, list) or not files:
        raise ValueError("empty or invalid files list")
    for f in files:
        if not f.get("filename") or not isinstance(f.get("content"), str):
            raise ValueError(f"malformed file entry: {f}")
    return files


class ProjectEngine:
    """Stateless — assistant.py owns the wizard's conversation state (which
    question is pending, what's been answered so far), same as it does for
    the task-creation follow-ups. This class only does the final scaffold."""

    async def scaffold(self, name: str, description: str, sections: str = "") -> Tuple[bool, str]:
        """Drafts a multi-file project plan via one LLM call and writes it
        to sunny-vault/projects/<slug>/. Returns (success, message) —
        never raises; a malformed LLM response or a write failure is
        reported back as a plain failure, same contract as TaskEngine's
        execute methods."""
        name = name.strip()
        if not name:
            return False, "A project needs a name."

        sections_line = (
            f'The user specifically wants these sections/files covered: {sections}.'
            if sections.strip()
            else "The user had no specific sections in mind — decide what's useful based on the description."
        )
        prompt = (
            f"Project name: {name}\n"
            f"Description: {description or '(none given)'}\n"
            f"{sections_line}"
        )

        system = instructions.load_instructions("project_scaffold")
        raw = await ask_claude(
            prompt,
            model=_SCAFFOLD_MODEL,
            max_tokens=_SCAFFOLD_MAX_TOKENS,
            system=system,
            purpose="project_scaffold",
        )
        if raw is None:
            return False, "Couldn't reach Claude to draft the project — try again in a moment."

        try:
            files = _parse_file_plan(raw)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.error(f"project_engine: malformed scaffold response: {e}")
            return False, "Claude's project plan came back malformed — try again."

        slug = _unique_project_slug(name)
        project_dir = _projects_dir() / slug
        try:
            for file_entry in files:
                filename = file_entry["filename"]
                if not filename.endswith(".md"):
                    filename += ".md"
                # Guard against a path-like filename escaping project_dir
                # (e.g. "../x.md") -- Claude is asked for bare filenames,
                # but nothing here should trust that blindly.
                safe_name = Path(filename).name
                vault_io.atomic_write_text(project_dir / safe_name, file_entry["content"])
        except OSError as e:
            logger.error(f"project_engine: failed writing project files: {e}")
            return False, f'Started writing "{name}" but hit a disk error partway through: {e}'

        logger.info(f"Project scaffolded: {name!r} -> {project_dir} ({len(files)} files)")
        file_list = ", ".join(Path(f["filename"]).name for f in files)
        return True, f'Created project "{name}" — {len(files)} files ({file_list})'
