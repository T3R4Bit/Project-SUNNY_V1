"""Durable chat conversations -- the transcript behind the web/PWA chat.

WHY THIS EXISTS SEPARATELY FROM conversation_memory
---------------------------------------------------
conversation_memory holds the last few turns in RAM so a follow-up ("why?",
"the second one") resolves. It is deliberately small, ephemeral and shared
by every interface, and that is the right shape for what it does: prompt
context, not a record.

This is the record. Someone reloading the page expects to see what they
said an hour ago, and expects it to still be there tomorrow. Those are
different requirements -- one bounded and disposable, the other complete
and durable -- so they are separate stores rather than one store trying to
be both. conversation_memory is hydrated FROM this on resume (see
hydrate_memory), which is what makes a follow-up survive a restart.

WHY SQLITE RATHER THAN THE VAULT
--------------------------------
Tasks and lists live in the vault as markdown because they are things you
edit by hand in Obsidian. A chat transcript is not: it is append-only,
high-volume, and wants querying by recency. One markdown file per
conversation would put hundreds of machine-owned files into a tree that is
already fighting sync conflicts, for no benefit -- nobody hand-edits a
transcript.

TITLES
------
Derived from the first user message, truncated at a word boundary. Not
LLM-generated: that would cost an API call per conversation, and a
truncated first line is both free and more predictable. Renaming exists
for when it reads badly.
"""

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components.db_connection import closing_transaction
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# How many past turns are replayed into the prompt on resume. Matches
# conversation_memory.MAX_TURNS -- hydrating more than that store holds
# would just be discarded, and hydrating fewer would make a resumed
# conversation dumber than a live one.
HYDRATE_TURNS = 6

# Longest stored title: recognisable in a sidebar, short enough not to wrap.
TITLE_MAX = 60

DEFAULT_TITLE = "New conversation"


def _db_path() -> Path:
    return get_settings().project_root / "sunny.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the tables if absent. Safe to call repeatedly."""
    with closing_transaction(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT NOT NULL
            )
            """
        )
        # Every read is either "this conversation, in order" or "latest
        # conversations", so those are the two indexes worth having.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_conv ON chat_messages (conversation_id, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_conv_updated ON chat_conversations (updated_at DESC)"
        )


def _now() -> str:
    """Microsecond precision, not seconds.

    updated_at is the sidebar's sort key, and two conversations touched in
    the same second would tie and order arbitrarily -- which looks like
    the list shuffling itself for no reason. Microseconds make a tie
    effectively impossible; the ORDER BY below still carries a tie-break
    for the case where it somehow is not.
    """
    return datetime.now().isoformat(timespec="microseconds")


def make_title(text: str) -> str:
    """A sidebar title from the first user message.

    Truncates at a word boundary rather than mid-word: a title cut to
    "what should I do about my tr" reads as a bug.
    """
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return DEFAULT_TITLE
    if len(cleaned) <= TITLE_MAX:
        return cleaned
    clipped = cleaned[:TITLE_MAX].rsplit(" ", 1)[0]
    return (clipped or cleaned[:TITLE_MAX]) + "…"


def create_conversation(title: Optional[str] = None) -> str:
    """Start a conversation and return its id."""
    init_db()
    conversation_id = uuid.uuid4().hex[:16]
    now = _now()
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute(
                "INSERT INTO chat_conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title or DEFAULT_TITLE, now, now),
            )
    except sqlite3.Error as e:
        logger.error(f"Could not create conversation: {e}", exc_info=True)
    return conversation_id


def ensure_conversation(conversation_id: Optional[str]) -> str:
    """Return a usable conversation id, creating a row if needed.

    An unknown id is adopted rather than rejected: the client keeps the id
    in localStorage, so it can outlive the database (a restore from
    backup, a cleared table). Rejecting would strand the user in a
    conversation that can never be written to, with no way out but
    clearing site data.
    """
    init_db()
    if not conversation_id:
        return create_conversation()

    try:
        with closing_transaction(_connect()) as conn:
            row = conn.execute(
                "SELECT id FROM chat_conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if row:
                return conversation_id
            now = _now()
            conn.execute(
                "INSERT INTO chat_conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, DEFAULT_TITLE, now, now),
            )
        return conversation_id
    except sqlite3.Error as e:
        logger.error(f"Could not ensure conversation {conversation_id!r}: {e}", exc_info=True)
        return conversation_id


def add_message(conversation_id: str, role: str, content: str) -> None:
    """Append a message and bump the conversation's updated_at.

    Also names the conversation from its first user message, so it is
    recognisable in the sidebar without anyone titling it by hand.
    """
    if not content:
        return
    init_db()
    now = _now()
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute(
                "INSERT INTO chat_messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, now),
            )
            conn.execute(
                "UPDATE chat_conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
            if role == "user":
                # Only while still untitled -- a later message must never
                # rename a conversation out from under you.
                conn.execute(
                    "UPDATE chat_conversations SET title = ? WHERE id = ? AND title = ?",
                    (make_title(content), conversation_id, DEFAULT_TITLE),
                )
    except sqlite3.Error as e:
        # Never raises into the chat path: failing to persist a message is
        # bad, losing the reply the user is waiting on is worse.
        logger.error(f"Could not store message: {e}", exc_info=True)


def list_conversations(limit: int = 50) -> List[Dict]:
    """Conversations newest-first, with a preview of the last message."""
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id) AS message_count,
                       (SELECT m.content FROM chat_messages m
                          WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) AS last_message
                FROM chat_conversations c
                ORDER BY c.updated_at DESC,
                         (SELECT MAX(m.id) FROM chat_messages m WHERE m.conversation_id = c.id) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.Error as e:
        logger.error(f"Could not list conversations: {e}", exc_info=True)
        return []

    out = []
    for r in rows:
        preview = " ".join((r["last_message"] or "").split())
        out.append({
            "id": r["id"],
            "title": r["title"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "message_count": r["message_count"],
            "preview": preview[:90] + ("…" if len(preview) > 90 else ""),
        })
    return out


def get_messages(conversation_id: str, limit: int = 500) -> List[Dict]:
    """Full transcript in order. `limit` guards against a runaway
    conversation making the page unusable; it keeps the most recent."""
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at FROM chat_messages
                WHERE conversation_id = ? ORDER BY id DESC LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
    except sqlite3.Error as e:
        logger.error(f"Could not read conversation {conversation_id!r}: {e}", exc_info=True)
        return []
    return [
        {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
        for r in reversed(rows)
    ]


def rename_conversation(conversation_id: str, title: str) -> bool:
    init_db()
    clean = " ".join((title or "").split())[:TITLE_MAX]
    if not clean:
        return False
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute(
                "UPDATE chat_conversations SET title = ? WHERE id = ?", (clean, conversation_id)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Could not rename conversation: {e}", exc_info=True)
        return False


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation and its messages.

    A real delete, not an archive flag. A finished task archives because
    it is still a record of something done; a deleted chat is just
    deleted, and keeping it around would be a surprise.
    """
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conversation_id,))
        return True
    except sqlite3.Error as e:
        logger.error(f"Could not delete conversation: {e}", exc_info=True)
        return False


def hydrate_memory(conversation_id: str, session_id: str) -> int:
    """Replay a conversation's recent turns into conversation_memory.

    This is what makes a resumed conversation actually resume. Without it,
    reloading the page would show the full transcript while Sunny had no
    idea any of it happened -- the next follow-up would land with no
    context, which is worse than showing no history at all, because the
    UI promises otherwise.

    No-ops when memory already holds this session, so an ordinary
    back-and-forth doesn't re-seed on every message.
    """
    from sunny_code.components import conversation_memory

    if conversation_memory.format_for_prompt(session_id):
        return 0

    turns = get_messages(conversation_id, limit=HYDRATE_TURNS)
    for turn in turns:
        conversation_memory.record_turn(session_id, turn["role"], turn["content"])
    return len(turns)
