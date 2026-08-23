"""Natural-language command parser for Spotify playback (no LLM, regex only).

Same shape as lists_parser.py's ListCommandParser: a pure text-in,
(action, data)-out parser with no side effects — sunny_code.components.
spotify_engine is what actually calls the Spotify Web API.

Deliberately narrow scope: transport controls (play/pause/resume/skip/
previous/volume) plus catalog search-and-play by name. No queue
management, playlist creation, or library browsing.
"""

import re
from typing import Dict, Optional, Tuple

VOLUME_STEP = 15


class SpotifyCommandParser:
    """Parse Spotify playback commands: play, pause, resume, next, previous,
    volume, now_playing."""

    # Checked before RESUME_TRIGGERS' bare "play" — "play" alone resumes,
    # "play <something>" searches and starts that. "put on" is a common
    # spoken alternative ("put on some Bowie").
    PLAY_QUERY = re.compile(r'^(?:play|put on)\s+(.+)$', re.IGNORECASE)

    # Deliberately NOT including bare "stop" — that word is already
    # overloaded as a general conversation-cancel word elsewhere in
    # assistant.py's pending-followup flows, and "stop" alone outside a
    # music context is genuinely ambiguous. "stop the music"/"stop playing"
    # are unambiguous enough to keep.
    PAUSE_TRIGGERS = ("pause", "pause the music", "pause music", "stop the music", "stop music", "stop playing")

    RESUME_TRIGGERS = (
        "play", "resume", "unpause", "resume the music", "resume music", "resume playing", "keep playing",
    )

    NEXT_TRIGGERS = ("skip", "skip this", "skip song", "skip track", "next song", "next track", "next")

    PREVIOUS_TRIGGERS = (
        "previous song", "previous track", "go back", "last song",
        "play the previous song", "play the last song", "back a song",
    )

    NOW_PLAYING_TRIGGERS = (
        "what's playing", "whats playing", "what is playing",
        "what song is this", "what's this song", "whats this song",
        "what song is playing", "what's playing right now",
    )

    VOLUME_ABSOLUTE = re.compile(r'^(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})%?$', re.IGNORECASE)
    VOLUME_UP = ("volume up", "turn it up", "turn the volume up", "louder", "turn up the volume")
    VOLUME_DOWN = ("volume down", "turn it down", "turn the volume down", "quieter", "turn down the volume")

    @classmethod
    def parse(cls, command: str) -> Optional[Tuple[str, Dict]]:
        """Try every Spotify pattern. Returns (action, data) or None if
        nothing matched. Actions: play ({"query": str|None}), pause, resume,
        next, previous, now_playing, volume ({"percent": int} or {"delta": int})."""
        stripped = command.strip()
        lowered = stripped.lower().strip("? ")

        if lowered in cls.NOW_PLAYING_TRIGGERS:
            return "now_playing", {}

        if lowered in cls.PAUSE_TRIGGERS:
            return "pause", {}

        match = cls.VOLUME_ABSOLUTE.match(stripped)
        if match:
            percent = max(0, min(100, int(match.group(1))))
            return "volume", {"percent": percent}
        if lowered in cls.VOLUME_UP:
            return "volume", {"delta": VOLUME_STEP}
        if lowered in cls.VOLUME_DOWN:
            return "volume", {"delta": -VOLUME_STEP}

        if lowered in cls.NEXT_TRIGGERS:
            return "next", {}

        if lowered in cls.PREVIOUS_TRIGGERS:
            return "previous", {}

        # Bare resume checked before the query pattern's own bare "play"
        # match (both would match "play" verbatim -- lowered-exact-match
        # wins so a genuine "play" with nothing else never gets treated as
        # a query).
        if lowered in cls.RESUME_TRIGGERS:
            return "resume", {}

        match = cls.PLAY_QUERY.match(stripped)
        if match:
            query = match.group(1).strip().strip('"\'')
            if not query:
                return "play", {"query": None}
            return "play", {"query": query}

        return None
