"""Routes for the Google Sign-In flow: /auth/google/login, /callback, /status, /disconnect.

Kept separate from dashboard/console routes since this is the one place that
talks to Google's OAuth endpoints directly, not Sunny's own data.
"""

import html
import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from sunny_code.components import google_auth

logger = logging.getLogger(__name__)

# Same design tokens as legal/*.html (see sunny_code/components/legal_pages.py)
# so the OAuth callback screen reads as the same product, not a bare string.
_PAGE_STYLE = """
  :root {
    --bg: #f3f1ea; --surface: #ffffff; --border: #e2ddd0;
    --text: #201d16; --text-muted: #6b6455;
    --accent: #b8720f; --accent-strong: #8f5808; --accent-soft: #f6e4c1;
    --ok: #3f7d4a; --ok-soft: #e3efe1;
    --error: #b8460f; --error-soft: #f6e0c1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14131a; --surface: #1c1a24; --border: #2d2b38;
      --text: #ece8dd; --text-muted: #9b96a8;
      --accent: #ffb703; --accent-strong: #ffd166; --accent-soft: #3a2f16;
      --ok: #7cd992; --ok-soft: #1c3324;
      --error: #ff9166; --error-soft: #3a2416;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: var(--bg); color: var(--text);
    font-family: "Public Sans", -apple-system, "Segoe UI", sans-serif; line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--accent-strong); }
  .card {
    max-width: 420px; margin: 1.5rem; padding: 2.2rem 2rem;
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
    text-align: center;
  }
  .brand { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-bottom: 1.4rem; }
  .mark { width: 22px; height: 22px; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, var(--accent-strong), var(--accent) 70%); }
  .word { font-family: "Fraunces", Georgia, serif; font-weight: 600; font-size: 0.95rem; color: var(--text-muted); }
  .badge {
    width: 52px; height: 52px; border-radius: 50%; margin: 0 auto 1.1rem;
    display: flex; align-items: center; justify-content: center; font-size: 1.6rem;
  }
  .badge.ok { background: var(--ok-soft); color: var(--ok); }
  .badge.err { background: var(--error-soft); color: var(--error); }
  h1 {
    font-family: "Fraunces", Georgia, serif; font-weight: 600; font-size: 1.5rem;
    letter-spacing: -0.005em; margin: 0 0 0.6rem; text-wrap: balance;
  }
  p { margin: 0 0 1.4rem; color: var(--text-muted); font-size: 0.98rem; }
  p:last-of-type { margin-bottom: 0; }
  .email { color: var(--text); font-weight: 600; }
  .btn {
    display: inline-block; padding: 0.65rem 1.3rem; border-radius: 8px;
    background: var(--accent); color: #1a1206; font-weight: 600; font-size: 0.92rem;
    text-decoration: none;
  }
  .btn:hover { background: var(--accent-strong); }
  .btn.secondary {
    background: transparent; color: var(--text-muted); border: 1px solid var(--border);
  }
  .detail {
    margin-top: 1rem; font-family: "JetBrains Mono", monospace; font-size: 0.76rem;
    color: var(--text-muted); background: var(--bg); border-radius: 6px; padding: 0.5rem 0.7rem;
    text-align: left; word-break: break-word;
  }
"""

_PAGE_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600'
    '&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">'
)


def _page(body: str, title: str = "Google Sign-In — Project-Sunny") -> str:
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>{_PAGE_HEAD}<style>{_PAGE_STYLE}</style></head>"
        f"<body><div class='card'>"
        f"<div class='brand'><div class='mark' aria-hidden='true'></div><div class='word'>Project-Sunny</div></div>"
        f"{body}</div></body></html>"
    )


def create_google_auth_router() -> APIRouter:
    router = APIRouter(prefix="/auth/google")

    @router.get("/login")
    async def login():
        if not google_auth.is_client_configured():
            return HTMLResponse(
                _page(
                    "<div class='badge err'>!</div>"
                    "<h1>Not set up yet</h1>"
                    "<p><code>GOOGLE_CLIENT_ID</code> / <code>GOOGLE_CLIENT_SECRET</code> are missing from "
                    "<code>.env</code>. See <a href='/legal/home'>sunny-vault/docs/architecture/"
                    "google-integration.md</a> for setup steps.</p>"
                ),
                status_code=503,
            )
        return RedirectResponse(google_auth.build_authorization_url())

    @router.get("/callback")
    async def callback(code: str = None, state: str = None, error: str = None):
        if error:
            logger.warning(f"Google sign-in cancelled/denied: {error}")
            return HTMLResponse(
                _page(
                    "<div class='badge err'>✕</div>"
                    "<h1>Sign-in didn't complete</h1>"
                    f"<p>Google reported: <span class='email'>{html.escape(error)}</span></p>"
                    "<a class='btn' href='/console'>Back to console</a>"
                )
            )
        if not code or not state:
            return HTMLResponse(
                _page(
                    "<div class='badge err'>✕</div>"
                    "<h1>Incomplete callback</h1>"
                    "<p>Google's redirect was missing the expected <code>code</code>/<code>state</code> "
                    "parameters — the link may be stale. Start sign-in again from the console.</p>"
                    "<a class='btn' href='/console'>Back to console</a>"
                ),
                status_code=400,
            )

        try:
            email = google_auth.handle_callback(code, state)
        except Exception as e:
            logger.error(f"Google sign-in failed: {e}", exc_info=True)
            return HTMLResponse(
                _page(
                    "<div class='badge err'>✕</div>"
                    "<h1>Sign-in failed</h1>"
                    "<p>Something went wrong exchanging the sign-in code with Google.</p>"
                    f"<div class='detail'>{html.escape(str(e))}</div><br><br>"
                    "<a class='btn' href='/auth/google/login'>Try again</a>"
                ),
                status_code=400,
            )

        return HTMLResponse(
            _page(
                "<div class='badge ok'>✓</div>"
                "<h1>Connected</h1>"
                f"<p>Signed in as <span class='email'>{html.escape(email)}</span> — Calendar and Gmail "
                "(read-only) are now included in briefings.</p>"
                "<a class='btn' href='/console'>Back to console</a> "
                "<a class='btn secondary' href='/legal/privacy'>What Sunny reads</a>"
            )
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
