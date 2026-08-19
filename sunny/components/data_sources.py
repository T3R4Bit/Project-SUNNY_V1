"""Registry of which briefing data sources are backed by a real API vs. not yet connected.

Weather/calendar check actual env-configured API keys. Email/commute/health/news/
motorsports have no integration built yet, so they're always unconfigured. Tasks
are always real — backed directly by tasks.db, no external API needed.
"""

from typing import Optional

from sunny.config import get_settings

_SOURCES = {
    "weather": "OPENWEATHERMAP_API_KEY",
    "calendar": "GOOGLE_CALENDAR_API_KEY",
    "email": None,
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

    settings = get_settings()
    env_var = _SOURCES.get(source)
    if env_var is None:
        return False
    if env_var == "OPENWEATHERMAP_API_KEY":
        return bool(settings.openweathermap_api_key)
    if env_var == "GOOGLE_CALENDAR_API_KEY":
        return bool(settings.google_calendar_api_key)
    return False


def missing_requirement(source: str) -> str:
    """Human-readable description of what's needed to make a source real."""
    env_var = _SOURCES.get(source)
    if env_var:
        return f"needs {env_var} in .env"
    return "no data source integration built yet"
