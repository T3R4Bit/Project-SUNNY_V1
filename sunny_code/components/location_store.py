"""Where Sunny thinks "here" is, for weather lookups.

Set through the console (/console's LOCATION card), not .env — a location is
runtime state, not a secret, and this way changing it takes effect on the
very next weather call, no restart. `WEATHER_LOCATION` in .env still works
as the initial value if nothing's been saved through the UI yet, so an
existing setup keeps working untouched.

This is intentionally one static "home" location for now. See
sunny-vault/docs/architecture/location.md for where this is headed —
per-request location (wherever the question is actually being asked from)
instead of one fixed value.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)


def _path() -> Path:
    return get_settings().project_root / "location.json"


def get_location() -> Optional[str]:
    """The active location string (e.g. "Detroit,MI,US"), or None if nothing's set anywhere."""
    path = _path()
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8")).get("location", "")
            if looks_configured(saved):
                return saved
        except (OSError, ValueError) as e:
            logger.error(f"location.json unreadable: {e}")

    settings = get_settings()
    if looks_configured(settings.weather_location):
        return settings.weather_location
    return None


def set_location(value: str) -> None:
    """Save a new location. Takes effect immediately — nothing else to restart."""
    value = value.strip()
    _path().write_text(json.dumps({"location": value}, indent=2), encoding="utf-8")
    logger.info(f"Location set to {value!r} via console")
