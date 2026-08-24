"""Google Sign-In (OAuth 2.0) — one connected account, token stored on disk.

Sunny is single-user, so there's no per-user token table: a successful sign-in
writes one JSON file (`google_token.json`, gitignored, chmod 600 like `.env`)
holding the refresh token, and every caller reads through `get_credentials()`,
which refreshes silently when the access token has expired.

Scopes are intentionally narrow — Calendar (read + write, since Sunny can
now create/delete events) and Gmail (read-only), nothing else. See
sunny-vault/docs/architecture/google-integration.md for why, and for what a
still-wider scope grant (sending email) would need on top of this.

Widening the calendar scope from read-only to read+write means an existing
google_token.json's refresh token was issued under the *old*, narrower
scope — Google doesn't retroactively expand it. Anyone already connected
needs to reconnect (re-run the sign-in flow from /console) once this
change is deployed; build_authorization_url()'s prompt="consent" already
forces a fresh consent screen (and fresh token) on every sign-in, so this
needs no special-cased re-auth code, just clicking "Connect Google
Account" again.
"""

import json
import logging
import secrets
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",  # read + write -- see calendar_engine.py
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Single-user server: one pending OAuth flow at a time is enough here, no
# need for a session store. Both state (CSRF) and code_verifier (PKCE) must
# survive from build_authorization_url() to handle_callback() — they're two
# separate HTTP requests (the user goes to Google and back in between), so
# a Flow object's own auto-generated code_verifier is lost the moment that
# function returns unless it's captured here first.
_pending_state: Optional[str] = None
_pending_code_verifier: Optional[str] = None


def _client_config() -> dict:
    settings = get_settings()
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_oauth_redirect_uri],
        }
    }


def is_client_configured() -> bool:
    """Whether GOOGLE_CLIENT_ID/SECRET are set — prerequisite for sign-in to even start."""
    settings = get_settings()
    return looks_configured(settings.google_client_id) and looks_configured(settings.google_client_secret)


def build_authorization_url() -> str:
    """Start a sign-in: returns the Google consent screen URL to redirect the user to."""
    global _pending_state, _pending_code_verifier
    settings = get_settings()
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, redirect_uri=settings.google_oauth_redirect_uri
    )
    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # forces a refresh_token even on repeat sign-ins
        state=state,
    )
    # authorization_url() is what auto-generates the PKCE code_verifier on
    # this Flow instance (see google_auth_oauthlib's Flow.authorization_url)
    # — it doesn't exist before this call. Must capture it now: this Flow
    # object is discarded when this function returns, and handle_callback()
    # runs in a separate HTTP request with no way to get it back otherwise.
    _pending_state = state
    _pending_code_verifier = flow.code_verifier
    return auth_url


def handle_callback(code: str, state: str) -> str:
    """Exchange the callback's ?code= for tokens, persist them, return the connected email."""
    global _pending_state, _pending_code_verifier
    if not state or state != _pending_state:
        raise ValueError("OAuth state mismatch — sign-in flow expired or was tampered with")
    _pending_state = None
    code_verifier, _pending_code_verifier = _pending_code_verifier, None

    settings = get_settings()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
        code_verifier=code_verifier,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    email = _fetch_email(creds)
    _save_credentials(creds, email)
    logger.info(f"Google sign-in complete for {email}")
    return email


def _fetch_email(creds: Credentials) -> str:
    """Best-effort account email via the userinfo endpoint (falls back to 'unknown')."""
    try:
        import requests

        resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("email", "unknown")
    except Exception as e:
        logger.warning(f"Could not fetch Google account email: {e}")
        return "unknown"


def _token_path() -> Path:
    return get_settings().google_token_path


def _save_credentials(creds: Credentials, email: Optional[str] = None) -> None:
    path = _token_path()
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    if email is None and path.exists():
        try:
            email = json.loads(path.read_text(encoding="utf-8")).get("email")
        except (OSError, ValueError):
            email = None
    data["email"] = email or "unknown"

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
        logger.error(f"Google token file unreadable: {e}")
        return None


def get_credentials() -> Optional[Credentials]:
    """Load stored credentials, refreshing the access token if it's expired.

    Returns None if never connected, or if the stored refresh token has been
    revoked — callers treat that exactly like "not connected" (see
    sunny_code.components.data_sources), never crash the caller.
    """
    raw = _load_raw()
    if not raw or not raw.get("refresh_token"):
        return None

    creds = Credentials(
        token=raw.get("token"),
        refresh_token=raw.get("refresh_token"),
        token_uri=raw.get("token_uri"),
        client_id=raw.get("client_id"),
        client_secret=raw.get("client_secret"),
        scopes=raw.get("scopes"),
    )

    if not creds.valid:
        try:
            creds.refresh(Request())
            _save_credentials(creds, raw.get("email"))
        except Exception as e:
            logger.warning(f"Google token refresh failed (treating as disconnected): {e}")
            return None

    return creds


def is_connected() -> bool:
    """Whether Sunny currently has a usable Google sign-in (may trigger a token refresh)."""
    return get_credentials() is not None


def connected_email() -> Optional[str]:
    raw = _load_raw()
    if not raw:
        return None
    return raw.get("email")


def disconnect() -> None:
    """Forget the stored token. Does not revoke it on Google's side."""
    path = _token_path()
    if path.exists():
        path.unlink()
