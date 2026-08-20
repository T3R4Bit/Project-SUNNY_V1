"""Registry of which briefing data sources are backed by a real API vs. not yet connected.

Weather needs both an env-configured API key AND a location — the location
comes from sunny_code.components.location_store (set via /console, falls
back to .env's WEATHER_LOCATION), not straight from settings, since it's
meant to be changeable without a restart. Calendar/email check whether
Google Sign-In is connected (sunny_code.components.google_auth) — see
sunny-vault/docs/architecture/google-integration.md for what that does and
doesn't cover. Commute/health/news/motorsports have no integration built yet
(and commute/health aren't part of Google Sign-In even once other sources
are wired up — see that doc). Tasks are always real — stored directly in
the vault, no external API needed.
"""

from sunny_code.components import google_auth, location_store
from sunny_code.config import get_settings, looks_configured

_SOURCES = {
    "weather": "OPENWEATHERMAP_API_KEY",
    "calendar": "GOOGLE_SIGN_IN",
    "email": "GOOGLE_SIGN_IN",
    "commute": None,
    "health": None,
    "news": None,
    "motorsports": None,
    "tasks": None,  # always configured, see is_configured()
}


def is_configured(source: str) -> bool:
    """Whether a data source has a real backend wired up."""
    if source == "tasks":
        return True

    requirement = _SOURCES.get(source)
    if requirement is None:
        return False
    if requirement == "GOOGLE_SIGN_IN":
        return google_auth.is_connected()
    if requirement == "OPENWEATHERMAP_API_KEY":
        settings = get_settings()
        return looks_configured(settings.openweathermap_api_key) and bool(location_store.get_location())
    return False


def missing_requirement(source: str) -> str:
    """Human-readable description of what's needed to make a source real."""
    requirement = _SOURCES.get(source)
    if requirement == "GOOGLE_SIGN_IN":
        return "needs Google sign-in — connect at /auth/google/login"
    if requirement == "OPENWEATHERMAP_API_KEY":
        settings = get_settings()
        missing = []
        if not looks_configured(settings.openweathermap_api_key):
            missing.append("OPENWEATHERMAP_API_KEY in .env")
        if not location_store.get_location():
            missing.append("a location — open /console and enter it in the LOCATION card (right sidebar)")
        return f"needs {' and '.join(missing)}"
    if requirement:
        return f"needs {requirement} in .env"
    return "no data source integration built yet"
