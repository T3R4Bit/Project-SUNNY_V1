"""Spotify Sign-In (OAuth 2.0, Authorization Code + PKCE) — one connected
account, token stored on disk.

Mirrors sunny_code/components/google_auth.py's shape (single-user, one JSON
token file, refresh-on-read), but hand-rolled with `requests` instead of a
client library: unlike Google, there's no first-party OAuth client for
Spotify already in this codebase, and Spotify's flow is simple enough
(standard PKCE Authorization Code grant) not to need one.

Scopes are limited to what playback control actually needs — nothing about
library, playlists, or listening history.
"""

import base64
import hashlib
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Optional

import requests

from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
ME_URL = "https://api.spotify.com/v1/me"

SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing"

# Single-user server: one pending OAuth flow at a time is enough here, no
# need for a session store. Both state (CSRF) and code_verifier (PKCE) must
# survive from build_authorization_url() to handle_callback() — they're two
# separate HTTP requests (the user goes to Spotify and back in between).
_pending_state: Optional[str] = None
_pending_code_verifier: Optional[str] = None


def is_client_configured() -> bool:
    """Whether SPOTIFY_CLIENT_ID/SECRET are set — prerequisite for sign-in to even start."""
    settings = get_settings()
    return looks_configured(settings.spotify_client_id) and looks_configured(settings.spotify_client_secret)


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorization_url() -> str:
    """Start a sign-in: returns the Spotify consent screen URL to redirect the user to."""
    global _pending_state, _pending_code_verifier
    settings = get_settings()

    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    _pending_state = state
    _pending_code_verifier = code_verifier

    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_oauth_redirect_uri,
        "state": state,
        "scope": SCOPES,
        "code_challenge_method": "S256",
        "code_challenge": _code_challenge(code_verifier),
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def handle_callback(code: str, state: str) -> str:
    """Exchange the callback's ?code= for tokens, persist them, return the connected username."""
    global _pending_state, _pending_code_verifier
    if not state or state != _pending_state:
        raise ValueError("OAuth state mismatch — sign-in flow expired or was tampered with")
    _pending_state = None
    code_verifier, _pending_code_verifier = _pending_code_verifier, None

    settings = get_settings()
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.spotify_oauth_redirect_uri,
            "client_id": settings.spotify_client_id,
            "code_verifier": code_verifier,
        },
        auth=(settings.spotify_client_id, settings.spotify_client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    token_data = resp.json()

    username = _fetch_username(token_data["access_token"])
    _save_tokens(token_data, username)
    logger.info(f"Spotify sign-in complete for {username}")
    return username


def _fetch_username(access_token: str) -> str:
    """Best-effort account display name/id via the /me endpoint (falls back to 'unknown')."""
    try:
        resp = requests.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data.get("display_name") or data.get("id") or "unknown"
    except Exception as e:
        logger.warning(f"Could not fetch Spotify account name: {e}")
        return "unknown"


def _token_path() -> Path:
    return get_settings().spotify_token_path


def _save_tokens(token_data: dict, username: Optional[str] = None) -> None:
    path = _token_path()
    existing = _load_raw() or {}

    data = {
        "access_token": token_data["access_token"],
        # Spotify's refresh response sometimes omits refresh_token entirely
        # (it stays valid) — keep the old one rather than losing it.
        "refresh_token": token_data.get("refresh_token") or existing.get("refresh_token"),
        "expires_at": time.time() + token_data.get("expires_in", 3600),
        "scope": token_data.get("scope", SCOPES),
        "username": username if username is not None else existing.get("username", "unknown"),
    }

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # best-effort — not all filesystems (e.g. some Windows setups) support chmod


def _load_raw() -> Optional[dict]:
    path = _token_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.error(f"Spotify token file unreadable: {e}", exc_info=True)
        return None


def _refresh(raw: dict) -> Optional[dict]:
    settings = get_settings()
    try:
        resp = requests.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": raw["refresh_token"]},
            auth=(settings.spotify_client_id, settings.spotify_client_secret),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Spotify token refresh failed (treating as disconnected): {e}")
        return None

    token_data = resp.json()
    _save_tokens(token_data, raw.get("username"))
    return _load_raw()


def get_credentials() -> Optional[str]:
    """Load the stored access token, refreshing it first if expired.

    Returns None if never connected, or if the stored refresh token has been
    revoked — callers treat that exactly like "not connected," never crash.
    """
    raw = _load_raw()
    if not raw or not raw.get("refresh_token"):
        return None

    if time.time() >= raw.get("expires_at", 0) - 30:  # 30s safety margin
        raw = _refresh(raw)
        if raw is None:
            return None

    return raw.get("access_token")


def is_connected() -> bool:
    """Whether Sunny currently has a usable Spotify sign-in (may trigger a token refresh)."""
    return get_credentials() is not None


def connected_username() -> Optional[str]:
    raw = _load_raw()
    if not raw:
        return None
    return raw.get("username")


def disconnect() -> None:
    """Forget the stored token. Does not revoke it on Spotify's side."""
    path = _token_path()
    if path.exists():
        path.unlink()
