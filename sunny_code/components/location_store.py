"""Where Sunny thinks "here" is, for weather lookups.

Set through the console (/console's LOCATION card), not .env — a location is
runtime state, not a secret, and this way changing it takes effect on the
very next weather call, no restart. `WEATHER_LOCATION` in .env still works
as the initial value if nothing's been saved through the UI yet, so an
existing setup keeps working untouched.

A second, independent location source lives alongside the static one: a GPS
fix reported by OwnTracks (see location_routes.py) — one step toward
sunny-vault/docs/architecture/location.md's "Where This Is Headed" plan of
per-request location instead of one fixed value. get_weather_query_params()
is the one place that decides GPS-vs-static, so weather.py never has to —
same "one call site" principle get_location() already established.
"""

import json
import logging
import time as _time
from pathlib import Path
from typing import Dict, Optional, Tuple

from sunny_code.components import vault_io
from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)


def _path() -> Path:
    return get_settings().project_root / "location.json"


def _gps_path() -> Path:
    return get_settings().project_root / "location_gps.json"


def get_location() -> Optional[str]:
    """The active static location string (e.g. "Detroit,MI,US"), or None if nothing's set anywhere."""
    path = _path()
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8")).get("location", "")
            if looks_configured(saved):
                return saved
        except (OSError, ValueError) as e:
            logger.error(f"location.json unreadable: {e}", exc_info=True)

    settings = get_settings()
    if looks_configured(settings.weather_location):
        return settings.weather_location
    return None


def set_location(value: str) -> None:
    """Save a new static location. Takes effect immediately — nothing else to restart."""
    value = value.strip()
    _path().write_text(json.dumps({"location": value}, indent=2), encoding="utf-8")
    logger.info(f"Location set to {value!r} via console")


def record_gps_fix(lat: float, lon: float, tst: Optional[int] = None) -> None:
    """Save a GPS fix reported by OwnTracks (or anything else posting to
    /api/location/owntracks). Overwrites the previous fix — only the most
    recent position matters here, there's no history."""
    data = {"lat": lat, "lon": lon, "tst": tst, "received_at": _time.time()}
    vault_io.atomic_write_text(_gps_path(), json.dumps(data, indent=2))
    logger.info(f"GPS fix recorded: {lat:.4f}, {lon:.4f}")


def get_coordinates(max_age_minutes: int = 30) -> Optional[Tuple[float, float]]:
    """The most recent GPS fix as (lat, lon), or None if there isn't one or
    it's older than max_age_minutes. Sunny never polls the phone — OwnTracks
    pushes on its own schedule — so staleness here is what implements the
    backlog's "30-minute interval unless deemed immediate" on the receiving
    end: a fix older than the window is treated exactly like no fix at all."""
    path = _gps_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.error(f"location_gps.json unreadable: {e}", exc_info=True)
        return None

    age_seconds = _time.time() - data.get("received_at", 0)
    if age_seconds > max_age_minutes * 60:
        return None
    return data["lat"], data["lon"]


def get_weather_query_params(max_age_minutes: int = 30) -> Dict:
    """OpenWeatherMap query params for wherever "here" currently means:
    a recent GPS fix if one exists, else the static location string, else
    {} if neither is set. The one place the GPS-vs-static decision lives —
    weather.py just merges appid/units on top, it never makes this choice
    itself."""
    coords = get_coordinates(max_age_minutes)
    if coords is not None:
        return {"lat": coords[0], "lon": coords[1]}
    location = get_location()
    if location:
        return {"q": location}
    return {}
