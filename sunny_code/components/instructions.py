"""Loads per-task LLM system prompts from sunny-vault/docs/instructions/.

One markdown file per known ask_claude() "purpose" (e.g. weekly-health-check.md
for purpose="weekly_health_check" -- underscores in the purpose become
hyphens in the filename). The file's body (frontmatter stripped) is the
system prompt, verbatim -- hand-editable, no redeploy needed.

Deliberately not a keyword-searched/multi-file retrieval system: a purpose
maps to exactly one file by exact name. That's simpler than a search index
and is enough to deliver what actually matters here -- load only the one
small prompt a given call needs, editable straight in the vault. See
sunny-vault/docs/architecture/llm-instructions.md.
"""

from typing import Optional

from sunny_code.components import vault_io
from sunny_code.config import get_settings


def load_instructions(purpose: str) -> Optional[str]:
    """sunny-vault/docs/instructions/{purpose}.md's body, or None if there's no
    file for that purpose. Not cached -- matches get_settings()'s
    deliberate uncached-by-design pattern, so a hand-edit takes effect on
    the very next call, no restart."""
    settings = get_settings()
    filename = purpose.replace("_", "-") + ".md"
    path = settings.project_root / "sunny-vault" / "docs" / "instructions" / filename
    body = vault_io.read_body(path)
    return body.strip() if body else None
