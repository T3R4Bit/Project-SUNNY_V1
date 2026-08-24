"""Spotify playback engine — combines the command parser with real calls to
Spotify's Web API (`/v1/me/player/*`). Same (handled, success, message)
contract as lists_engine.py/scheduled_engine.py, async like scheduled_engine
since every action here is a real network call.

No device-targeting concept: every command acts on whatever Spotify itself
considers the "active device" (the same behavior Siri/the Spotify app use),
not a device Sunny tracks or chooses.
"""

import asyncio
import logging
from typing import Dict, Optional, Tuple

import requests

from sunny_code.components import spotify_auth
from sunny_code.components.request_log import log_unfulfilled
from sunny_code.components.spotify_parser import SpotifyCommandParser

logger = logging.getLogger(__name__)

API_BASE = "https://api.spotify.com/v1"
NOT_CONNECTED_MESSAGE = "Spotify isn't connected — say \"setup spotify\" for how."
NO_DEVICE_MESSAGE = "Open Spotify on a device first — nothing's active right now."
PREMIUM_REQUIRED_MESSAGE = "That needs Spotify Premium — playback control isn't available on a Free account."


class SpotifyEngine:
    """High-level Spotify playback control with command execution."""

    async def try_execute(self, command: str, source: str = None) -> Tuple[bool, bool, Optional[str]]:
        """Try to parse and execute as a Spotify playback command.

        Returns (handled, success, message). handled=False means this wasn't
        recognized as a Spotify command at all — the caller should try
        something else.
        """
        parsed = SpotifyCommandParser.parse(command)
        if parsed is None:
            return False, False, None

        action, data = parsed

        if not spotify_auth.is_connected():
            log_unfulfilled("spotify_command", f'"{command}" — not connected')
            return True, False, NOT_CONNECTED_MESSAGE

        if action == "play":
            success, message = await self._play(data.get("query"))
        elif action == "pause":
            success, message = await self._transport("PUT", "/me/player/pause", ok_message="Paused.")
        elif action == "resume":
            success, message = await self._transport("PUT", "/me/player/play", ok_message="Resumed.")
        elif action == "next":
            success, message = await self._transport("POST", "/me/player/next", ok_message="Skipped.")
        elif action == "previous":
            success, message = await self._transport("POST", "/me/player/previous", ok_message="Went back a track.")
        elif action == "volume":
            success, message = await self._volume(data)
        elif action == "now_playing":
            success, message = await self._now_playing()
        else:
            return False, False, None

        if not success:
            log_unfulfilled("spotify_command", f'"{command}" — {message}')
        return True, success, message

    async def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        token = await asyncio.to_thread(spotify_auth.get_credentials)
        if token is None:
            raise ConnectionError("not connected")
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        return await asyncio.to_thread(
            requests.request, method, f"{API_BASE}{path}", headers=headers, timeout=10, **kwargs
        )

    def _error_message(self, resp: requests.Response) -> Optional[str]:
        """None if resp represents success; a user-facing message otherwise."""
        if resp.status_code in (200, 202, 204):
            return None
        if resp.status_code == 404:
            return NO_DEVICE_MESSAGE
        if resp.status_code == 403:
            try:
                reason = resp.json().get("error", {}).get("reason", "")
            except ValueError:
                reason = ""
            if reason == "PREMIUM_REQUIRED":
                return PREMIUM_REQUIRED_MESSAGE
            return NO_DEVICE_MESSAGE
        logger.warning(f"Spotify API {resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text[:200]}")
        return "Spotify's API didn't like that — try again in a moment."

    async def _transport(self, method: str, path: str, ok_message: str) -> Tuple[bool, str]:
        try:
            resp = await self._request(method, path)
        except ConnectionError:
            return False, NOT_CONNECTED_MESSAGE
        except Exception as e:
            logger.error(f"Spotify transport command failed: {e}")
            return False, "Couldn't reach Spotify — try again in a moment."

        error = self._error_message(resp)
        if error:
            return False, error
        return True, ok_message

    async def _play(self, query: Optional[str]) -> Tuple[bool, str]:
        if not query:
            return await self._transport("PUT", "/me/player/play", ok_message="Resumed.")

        try:
            track_uri, label = await self._search_track(query)
        except ConnectionError:
            return False, NOT_CONNECTED_MESSAGE
        except Exception as e:
            logger.error(f"Spotify search failed: {e}")
            return False, "Couldn't reach Spotify — try again in a moment."

        if track_uri is None:
            return False, f"Couldn't find anything on Spotify matching \"{query}\"."

        try:
            resp = await self._request("PUT", "/me/player/play", json={"uris": [track_uri]})
        except ConnectionError:
            return False, NOT_CONNECTED_MESSAGE
        except Exception as e:
            logger.error(f"Spotify play failed: {e}")
            return False, "Couldn't reach Spotify — try again in a moment."

        error = self._error_message(resp)
        if error:
            return False, error
        return True, f"Playing {label}."

    async def _search_track(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """"X by Y" biases the search toward that artist; either way, returns
        (track_uri, "Track by Artist") for the first hit, or (None, None)."""
        search_query = query
        if " by " in query.lower():
            title, _, artist = query.rpartition(" by ")
            search_query = f"{title.strip()} artist:{artist.strip()}"

        resp = await self._request("GET", "/search", params={"q": search_query, "type": "track", "limit": 1})
        if resp.status_code != 200:
            return None, None

        items = resp.json().get("tracks", {}).get("items", [])
        if not items:
            return None, None

        track = items[0]
        artists = ", ".join(a["name"] for a in track.get("artists", []))
        label = f"{track['name']} by {artists}" if artists else track["name"]
        return track["uri"], label

    async def _volume(self, data: Dict) -> Tuple[bool, str]:
        percent = data.get("percent")
        if percent is None:
            try:
                current = await self._request("GET", "/me/player")
            except ConnectionError:
                return False, NOT_CONNECTED_MESSAGE
            except Exception as e:
                logger.error(f"Spotify volume lookup failed: {e}")
                return False, "Couldn't reach Spotify — try again in a moment."

            if current.status_code == 204 or current.status_code == 404:
                return False, NO_DEVICE_MESSAGE
            if current.status_code != 200:
                error = self._error_message(current)
                return False, error or "Couldn't check the current volume."

            current_percent = (current.json() or {}).get("device", {}).get("volume_percent")
            if current_percent is None:
                return False, NO_DEVICE_MESSAGE
            percent = max(0, min(100, current_percent + data.get("delta", 0)))

        try:
            resp = await self._request("PUT", "/me/player/volume", params={"volume_percent": percent})
        except ConnectionError:
            return False, NOT_CONNECTED_MESSAGE
        except Exception as e:
            logger.error(f"Spotify set-volume failed: {e}")
            return False, "Couldn't reach Spotify — try again in a moment."

        error = self._error_message(resp)
        if error:
            return False, error
        return True, f"Volume set to {percent}%."

    async def _now_playing(self) -> Tuple[bool, str]:
        try:
            resp = await self._request("GET", "/me/player/currently-playing")
        except ConnectionError:
            return False, NOT_CONNECTED_MESSAGE
        except Exception as e:
            logger.error(f"Spotify now-playing check failed: {e}")
            return False, "Couldn't reach Spotify — try again in a moment."

        if resp.status_code == 204 or not resp.content:
            return True, "Nothing's playing right now."
        if resp.status_code != 200:
            error = self._error_message(resp)
            return False, error or "Couldn't check what's playing."

        item = resp.json().get("item")
        if not item:
            return True, "Nothing's playing right now."
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        label = f"{item['name']} by {artists}" if artists else item["name"]
        return True, f"Now playing: {label}."
