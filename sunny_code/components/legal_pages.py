"""Self-hosted home/privacy/terms pages for Google OAuth verification.

Google's OAuth consent screen requires a home page, privacy policy, and
terms of service that (a) are reachable without logging into anything, and
(b) live on a domain the app owner actually controls. Static HTML files in
legal/ at the project root, served plain — no templating needed for three
pages that change rarely. See sunny-vault/docs/architecture/
google-integration.md for why these exist and what replaced them (Claude
Artifacts, which fail Google's "not behind a login" check).
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from sunny_code.config import get_settings


def create_legal_router() -> APIRouter:
    router = APIRouter(prefix="/legal")
    legal_dir = get_settings().project_root / "legal"

    def _serve(filename: str) -> HTMLResponse:
        return HTMLResponse(content=(legal_dir / filename).read_text(encoding="utf-8"))

    @router.get("/home")
    async def home():
        return _serve("home.html")

    @router.get("/privacy")
    async def privacy():
        return _serve("privacy.html")

    @router.get("/terms")
    async def terms():
        return _serve("terms.html")

    return router
