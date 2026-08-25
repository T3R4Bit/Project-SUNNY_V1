"""Lets the general-chat LLM fallback (briefing.py's custom_briefing)
answer questions about Sunny itself accurately -- grounded in Sunny's own
current documentation, instead of whatever the model happens to recall
about a codebase it's never actually seen. Plain keyword scoring over the
real doc files, not an embedding search or a real tool-use loop -- same
"deterministic routing, LLM only for judgment" shape as everything else
in this codebase, and a personal single-user tool doesn't need more than
that. Cheap enough (one directory walk, no LLM call) to run on every
general-chat question unconditionally; a genuinely unrelated question
(small talk, math, a question about something else entirely) just scores
0 everywhere and changes nothing about the prompt -- same "additive,
invisible when unused" contract as conversation_memory.format_for_prompt().
"""

import logging
import re
from pathlib import Path
from typing import Dict, List

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Just the per-component docs -- one topic each, so a raw word-overlap
# score stays meaningful. Deliberately excludes the broader meta docs in
# sunny-vault/docs/ directly (BACKLOG, CHANGELOG, DESIGN, phases, ABOUT,
# system-state, ...) and Mind-Map.md -- those are large, deliberately
# broad-vocabulary documents (a running history, a single-page overview
# of every component) that would out-score a specific, topical doc on
# raw word overlap alone regardless of actual relevance. Not
# sunny-vault/instructions/ (system prompts, not reference docs) or
# sunny-vault/KSU/ (the user's own data, unrelated to "how does Sunny
# work").
_DOC_DIRS = ("sunny-vault/docs/architecture",)
_EXCLUDE_FILENAMES = {"Mind-Map.md"}
_MAX_DOC_CHARS = 4000  # per matched doc, keeps the prompt bounded
_MAX_MATCHES = 2
_MIN_SCORE = 3  # at least 3 distinct query words must hit a doc before it counts
_FILENAME_MATCH_WEIGHT = 5  # a query word matching the doc's own filename is a much stronger signal than an incidental body mention
_WORD_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "do", "does", "did", "how", "what", "why", "when",
    "where", "your", "you", "of", "to", "in", "on", "for", "and", "or", "i", "my", "me", "it", "this",
    "that", "with", "have", "has", "can", "sunny",  # "sunny" is in nearly every doc -- not discriminating
}


def _words(text: str) -> set:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _doc_files() -> List[Path]:
    root = get_settings().project_root
    files = []
    for rel in _DOC_DIRS:
        d = root / rel
        if d.exists():
            files.extend(p for p in sorted(d.glob("*.md")) if p.name not in _EXCLUDE_FILENAMES)
    return files


def search(query: str, max_matches: int = _MAX_MATCHES) -> List[Dict]:
    """Best-matching docs for `query`, ranked by distinct query-word hits
    -- a hit against the doc's own filename counts _FILENAME_MATCH_WEIGHT
    times as much as one in the body, since "class setup" matching
    class-setup.md's title is a far stronger signal than it happening to
    share a few incidental words with some other doc's body text. []
    if nothing clears _MIN_SCORE -- the deliberate gate against stuffing
    irrelevant doc content into an unrelated question's prompt."""
    query_words = _words(query)
    if not query_words:
        return []

    scored = []
    for path in _doc_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.debug(f"docs_search: couldn't read {path}: {e}")
            continue
        body_hits = len(query_words & _words(text))
        filename_hits = len(query_words & _words(path.stem.replace("-", " ").replace("_", " ")))
        score = body_hits + filename_hits * _FILENAME_MATCH_WEIGHT
        if score >= _MIN_SCORE:
            scored.append((score, path, text))

    scored.sort(key=lambda x: x[0], reverse=True)
    root = get_settings().project_root
    return [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "content": text[:_MAX_DOC_CHARS]}
        for _, path, text in scored[:max_matches]
    ]


def format_for_prompt(matches: List[Dict]) -> str:
    """Rendered as prompt-prefix context, empty string if no matches --
    same shape as conversation_memory.format_for_prompt(), so callers can
    prepend this unconditionally without a branch."""
    if not matches:
        return ""
    sections = [f"## {m['path']}\n{m['content']}" for m in matches]
    return (
        "Sunny's own documentation (context for the question below, if relevant -- "
        "ignore it if the question isn't actually about how Sunny works):\n\n"
        + "\n\n".join(sections) + "\n\n---\n\n"
    )
