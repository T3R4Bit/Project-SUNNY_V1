"""Maps a session_id (see assistant.py) to a human-readable device/interface label.

Session IDs are already prefixed by source ("discord:<channel>:<user>",
"terminal", "pi"), so this is just a thin, consistent way to read that back
out — used to tag records (tasks, list items, alarms, reminders) with which
interface created them. "web" was a valid prefix (the now-retired web
console, see sunny-vault/docs/architecture/dashboard.md) until 2026-09-13 --
nothing produces it anymore, but old vault records already tagged "web" keep
reading back correctly since the label itself was never removed, only the
one thing that used to send it.
"""


def device_from_session(session_id: str) -> str:
    """Return a short device label from a session_id, e.g. 'discord', 'terminal', 'pi', 'api'."""
    if not session_id:
        return "api"
    prefix = session_id.split(":", 1)[0]
    return prefix if prefix in ("web", "discord", "terminal", "pi") else "api"
