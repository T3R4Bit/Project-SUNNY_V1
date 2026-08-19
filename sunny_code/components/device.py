"""Maps a session_id (see assistant.py) to a human-readable device/interface label.

Session IDs are already prefixed by source ("web:<uuid>", "discord:<channel>:<user>",
"terminal"), so this is just a thin, consistent way to read that back out — used to
tag records (tasks, list items, alarms, reminders) with which interface created them.
"""


def device_from_session(session_id: str) -> str:
    """Return a short device label from a session_id, e.g. 'web', 'discord', 'terminal', 'api'."""
    if not session_id:
        return "api"
    prefix = session_id.split(":", 1)[0]
    return prefix if prefix in ("web", "discord", "terminal") else "api"
