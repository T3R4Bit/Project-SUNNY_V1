"""Long-term memory: things worth remembering about Keaton.

THREE TIERS, NOT ONE
--------------------
  1. PROFILE  -- sunny-vault/memory/profile.md. Slow-changing: how he
     thinks, how he plans, his flaws, standing preferences. Human-owned,
     always injected in full. Small enough that retrieval would be more
     machinery than benefit.
  2. FACTS    -- one markdown file per fact in sunny-vault/memory/facts/,
     indexed here for retrieval. Many, specific, dated.
  3. PATTERNS -- derived, not stated. Written weekly by reflecting over
     facts and metrics ("workouts get skipped in weeks with 3+
     deadlines"). Not built yet; facts have to accumulate first.

Flattening these into one store would be wrong in both directions: the
profile is too important to be retrieved-or-not, and facts are too
numerous to inject wholesale.

WHY KEYWORD RETRIEVAL, NOT EMBEDDINGS
-------------------------------------
Embeddings would mean sentence-transformers and a few hundred MB of
torch on a box that also runs Sunny, Warren and a Garmin poller, for a
store that will hold hundreds of facts rather than millions. docs_search
already does keyword scoring over the vault and works well enough to
answer questions about Sunny's own architecture, so this reuses that
shape. If recall turns out to be the limiting factor, embeddings are a
drop-in replacement for score_fact() -- but building that now would be
exactly the "infrastructure with no caller" habit this project already
has three examples of.

OWNERSHIP
---------
profile.md is HUMAN-owned: Sunny reads it and never writes it, same rule
as personality.md. Facts are MACHINE-owned: Sunny writes them, you read
them in Obsidian. Keeping those separate is what stops memory becoming
the vault's worst sync-conflict source, since a file both sides edit is
precisely what file sync cannot merge.
"""

import logging
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components import vault_io
from sunny_code.components.db_connection import closing_transaction
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# What kind of thing a fact is. The type drives how it gets used, not just
# how it is filed: a preference shapes how Sunny answers, a flaw shapes
# what it warns about, a decision is context for why something is the way
# it is.
TYPES = ("preference", "fact", "person", "project", "flaw", "decision", "event")

# Minimum keyword overlap for a fact to be considered relevant. Low,
# because missing a relevant memory is worse than carrying one extra line
# of context -- but not zero, or every query would drag in everything.
_MIN_SCORE = 1

# Most facts injected into a single prompt. A cap rather than a token
# budget because facts are one or two lines each; the point is to stop an
# accumulated store from crowding out the actual question.
_MAX_INJECTED = 8

_WORD_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was",
    "have", "has", "had", "not", "what", "when", "where", "how", "why", "who",
    "can", "will", "would", "should", "could", "about", "from", "they", "them",
    "there", "their", "been", "being", "does", "did", "doing", "just", "like",
    "get", "got", "make", "made", "into", "than", "then", "some", "any", "all",
}


def _words(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower())
            if w not in _STOPWORDS and len(w) > 2}


def _memory_dir() -> Path:
    return get_settings().project_root / "sunny-vault" / "memory"


def _facts_dir() -> Path:
    return _memory_dir() / "facts"


def _profile_path() -> Path:
    return _memory_dir() / "profile.md"


def _db_path() -> Path:
    return get_settings().project_root / "sunny.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """The index. The vault markdown is the source of truth -- this is a
    cache that can be rebuilt from it (see reindex), which is what keeps
    a hand-deleted file from leaving a ghost in search results."""
    with closing_transaction(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_facts (
                id         TEXT PRIMARY KEY,
                type       TEXT NOT NULL,
                text       TEXT NOT NULL,
                source     TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_facts (type)")


# --- profile --------------------------------------------------------------

DEFAULT_PROFILE = """---
id: profile
type: memory
tags: [memory, profile]
---

# Profile

What Sunny should know about me that doesn't change week to week. Edited
by hand — Sunny reads this and never writes it.

Anything Sunny thinks belongs here gets proposed in
`memory/suggestions.md` for me to merge, so this file never has two
writers. That is the same rule as `personality.md`, and it exists because
a vault file edited by both a person and a server process is exactly what
file sync cannot merge cleanly.

## How I work

-

## How I plan

-

## What I'm bad at

-

## Standing preferences

-
"""


def ensure_profile() -> bool:
    """Create the profile scaffold if absent. True if it created one.

    Never overwrites: this is the one memory file Sunny must not author,
    and a scaffold is only useful before anything has been written into
    it.
    """
    path = _profile_path()
    if path.exists():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        vault_io.atomic_write_text(path, DEFAULT_PROFILE)
        logger.info(f"Created memory profile scaffold at {path}")
        return True
    except OSError as e:
        logger.error(f"Could not create profile: {e}")
        return False


def profile_text() -> str:
    """The profile body, or "" if absent or empty.

    Headings with no content under them are stripped: an empty "## What
    I'm bad at" in the prompt is noise that costs tokens and says nothing.
    """
    body = vault_io.read_body(_profile_path())
    if not body:
        return ""

    kept, buffer, has_content, started = [], [], False, False
    for line in body.splitlines():
        if line.startswith("## "):
            if started and has_content:
                kept.extend(buffer)
            buffer, has_content, started = [line], False, True
            continue
        if not started:
            # Everything before the first "## " is the scaffold's own
            # explanation of how the file works -- instructions for the
            # person editing it, not context for the model. Without this,
            # an untouched profile injected three paragraphs about sync
            # conflicts into every single prompt.
            continue
        buffer.append(line)
        stripped = line.strip()
        if stripped and stripped not in ("-", "*"):
            has_content = True

    if started and has_content:
        kept.extend(buffer)
    return "\n".join(kept).strip()


# --- facts ----------------------------------------------------------------

def remember(text: str, kind: str = "fact", source: str = "", confidence: float = 1.0) -> Optional[str]:
    """Store a fact. Returns its id, or None if it was rejected.

    Writes the vault file first and indexes second: the markdown is the
    source of truth, so a crash between the two leaves a real file that
    reindex() will pick up, rather than an index row pointing at nothing.
    """
    text = " ".join((text or "").split())
    if not text:
        return None
    if kind not in TYPES:
        kind = "fact"

    fact_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat(timespec="seconds")

    try:
        _facts_dir().mkdir(parents=True, exist_ok=True)
        slug = vault_io.slugify(text, max_len=48) or fact_id
        path = _facts_dir() / f"{now[:10]}-{slug}-{fact_id[:6]}.md"
        vault_io.atomic_write_text(path, vault_io.serialize_frontmatter(
            {
                "id": fact_id,
                "type": kind,
                "source": source or "manual",
                "confidence": confidence,
                "created": now,
                "tags": ["memory", kind],
            },
            text + "\n",
            ["id", "type", "source", "confidence", "created", "tags"],
        ))
    except OSError as e:
        logger.error(f"Could not write memory fact: {e}", exc_info=True)
        return None

    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_facts
                    (id, type, text, source, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (fact_id, kind, text, source or "manual", confidence, now, now),
            )
    except sqlite3.Error as e:
        logger.error(f"Could not index memory fact: {e}", exc_info=True)

    logger.info(f"Remembered ({kind}): {text[:70]}")
    return fact_id


def forget(fact_id: str) -> bool:
    """Remove a fact from the index and delete its vault file."""
    init_db()
    removed = False
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
        removed = True
    except sqlite3.Error as e:
        logger.error(f"Could not unindex fact: {e}", exc_info=True)

    try:
        for path in _facts_dir().glob(f"*{fact_id[:6]}.md"):
            path.unlink()
    except OSError as e:
        logger.warning(f"Could not delete fact file: {e}")
    return removed


def all_facts(kind: Optional[str] = None) -> List[Dict]:
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM memory_facts WHERE type = ? ORDER BY created_at DESC", (kind,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_facts ORDER BY created_at DESC"
                ).fetchall()
    except sqlite3.Error as e:
        logger.error(f"Could not read facts: {e}", exc_info=True)
        return []
    return [dict(r) for r in rows]


def score_fact(fact_words: set, query_words: set) -> int:
    """Keyword overlap. Swap this for an embedding similarity if recall
    ever becomes the limiting factor -- everything else here is agnostic
    to how relevance is computed."""
    return len(fact_words & query_words)


def recall(query: str, limit: int = _MAX_INJECTED) -> List[Dict]:
    """Facts relevant to `query`, best first.

    Preferences and flaws get a small boost: they shape how an answer
    should be given rather than just supplying a detail, so they are worth
    carrying even when the keyword overlap is thinner.
    """
    query_words = _words(query)
    if not query_words:
        return []

    scored = []
    for fact in all_facts():
        overlap = score_fact(_words(fact["text"]), query_words)
        if overlap < _MIN_SCORE:
            continue
        weight = overlap + (1 if fact["type"] in ("preference", "flaw") else 0)
        scored.append((weight, fact))

    scored.sort(key=lambda pair: -pair[0])
    return [fact for _, fact in scored[:limit]]


def format_for_prompt(query: str = "") -> str:
    """Profile plus any relevant facts, ready to prepend to a prompt.

    Empty string when there is nothing to say, so callers can concatenate
    unconditionally -- the same contract as docs_search.format_for_prompt
    and conversation_memory.format_for_prompt.
    """
    blocks = []

    profile = profile_text()
    if profile:
        blocks.append("WHAT YOU KNOW ABOUT KEATON\n" + profile)

    facts = recall(query) if query else []
    if facts:
        lines = [f"- ({f['type']}) {f['text']}" for f in facts]
        blocks.append("RELEVANT MEMORY\n" + "\n".join(lines))

    return "\n\n".join(blocks) + "\n\n" if blocks else ""


def reindex() -> int:
    """Rebuild the index from the vault files.

    The markdown is the source of truth, so this is how a hand-deleted or
    hand-edited fact gets reflected -- without it, deleting a file in
    Obsidian would leave the fact still being injected into prompts with
    no way to see why.
    """
    init_db()
    facts_dir = _facts_dir()
    if not facts_dir.exists():
        return 0

    found = []
    for path in sorted(facts_dir.glob("*.md")):
        try:
            metadata, body = vault_io.parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning(f"Skipping unreadable fact {path.name}: {e}")
            continue
        text = " ".join((body or "").split())
        if not text:
            continue
        found.append({
            "id": str((metadata or {}).get("id") or path.stem[-6:]),
            "type": str((metadata or {}).get("type") or "fact"),
            "text": text,
            "source": str((metadata or {}).get("source") or "vault"),
            "confidence": float((metadata or {}).get("confidence") or 1.0),
            "created_at": str((metadata or {}).get("created") or ""),
        })

    try:
        with closing_transaction(_connect()) as conn:
            conn.execute("DELETE FROM memory_facts")
            now = datetime.now().isoformat(timespec="seconds")
            conn.executemany(
                """
                INSERT INTO memory_facts
                    (id, type, text, source, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(f["id"], f["type"], f["text"], f["source"], f["confidence"],
                  f["created_at"] or now, now) for f in found],
            )
    except sqlite3.Error as e:
        logger.error(f"Reindex failed: {e}", exc_info=True)
        return 0

    logger.info(f"Memory reindexed: {len(found)} facts")
    return len(found)
