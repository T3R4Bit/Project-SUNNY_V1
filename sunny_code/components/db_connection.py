"""Fixes a real, confirmed file-descriptor leak: `sqlite3.Connection`'s own
context-manager protocol (`with sqlite3.connect(path) as conn:`) only
commits or rolls back the transaction on exit — it does **not** close the
connection (a well-documented but frequently-missed stdlib gotcha; see the
sqlite3 docs' own note that the context manager "neither implicitly opens
a new transaction nor closes the connection"). Every call site using that
plain idiom leaks one file descriptor per call, relying entirely on
whenever the garbage collector eventually gets to it.

Confirmed live, 2026-08-21: scheduled_db.py's get_due_items() is polled
every 30s by discord_bot.py's scheduled_check_loop, and after ~8.7 hours
of uptime had leaked 1012 of the process's 1024 available file
descriptors — exhausting them and breaking DNS resolution for every
outbound connection the whole app made (including Discord's own gateway/
API calls), with "OSError: [Errno 24] Too many open files". dashboard.py
and token_tracker.py use the exact same leaky idiom, just polled less
often, so they leak slower but are the same bug.
"""

import sqlite3
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def closing_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Wraps an already-open connection with the same commit-on-success/
    rollback-on-exception behavior as sqlite3's own `with conn:`, plus a
    guaranteed `conn.close()` afterward — drop-in fix for
    `with sqlite3.connect(path) as conn:` (replace with
    `with closing_transaction(sqlite3.connect(path)) as conn:`)."""
    try:
        with conn:
            yield conn
    finally:
        conn.close()
