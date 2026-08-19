"""Routes for the Google Sign-In flow: /auth/google/login, /callback, /status, /disconnect.

Kept separate from dashboard/console routes since this is the one place that
talks to Google's OAuth endpoints directly, not Sunny's own data.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from sunny_code.components import google_auth

logger = logging.getLogger(__name__)


def create_google_auth_router() -> APIRouter:
    router = APIRouter(prefix="/auth/google")

    @router.get("/login")
    async def login():
        if not google_auth.is_client_configured():
            return HTMLResponse(
                "<p>Google sign-in isn't set up yet — GOOGLE_CLIENT_ID / "
                "GOOGLE_CLIENT_SECRET are missing from .env. See "
                "sunny-vault/docs/architecture/google-integration.md for setup steps.</p>",
                status_code=503,
            )
        return RedirectResponse(google_auth.build_authorization_url())

    @router.get("/callback")
    async def callback(code: str = None, state: str = None, error: str = None):
        if error:
            logger.warning(f"Google sign-in cancelled/denied: {error}")
            return HTMLResponse(
                f"<p>Google sign-in didn't complete: {error}. "
                f'<a href="/console">Back to console</a></p>'
            )
        if not code or not state:
            return HTMLResponse("<p>Missing code/state on callback.</p>", status_code=400)

        try:
            email = google_auth.handle_callback(code, state)
        except Exception as e:
            logger.error(f"Google sign-in failed: {e}", exc_info=True)
            return HTMLResponse(
                f"<p>Google sign-in failed: {e}. "
                f'<a href="/auth/google/login">Try again</a></p>',
                status_code=400,
            )

        return HTMLResponse(
            f"<p>Connected as {email}. You can close this tab — "
            f'<a href="/console">back to console</a>.</p>'
        )

    @router.get("/status")
    async def status():
        connected = google_auth.is_connected()
        return {
            "client_configured": google_auth.is_client_configured(),
            "connected": connected,
            "email": google_auth.connected_email() if connected else None,
            "scopes": google_auth.SCOPES,
        }

    @router.post("/disconnect")
    async def disconnect():
        google_auth.disconnect()
        return {"status": "disconnected"}

    return router
