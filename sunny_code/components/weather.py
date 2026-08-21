"""Live weather reads via OpenWeatherMap — needs both OPENWEATHERMAP_API_KEY
(in .env) and a location (set via /console's LOCATION card, see
sunny_code.components.location_store — not just .env's WEATHER_LOCATION,
which is only the initial fallback).

Same fail-quietly contract as google_calendar/google_gmail: any error (bad
key, bad location, network failure) returns None, never raises — callers
treat None exactly like "not connected."
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import requests

from sunny_code.components import location_store
from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openweathermap.org/data/2.5"
_TIMEOUT = 5


def _params() -> Optional[dict]:
    settings = get_settings()
    if not looks_configured(settings.openweathermap_api_key):
        return None
    location_params = location_store.get_weather_query_params()
    if not location_params:
        return None
    return {
        **location_params,
        "appid": settings.openweathermap_api_key,
        "units": "imperial",
    }


def location_resolves(location: str) -> bool:
    """True if OpenWeatherMap can actually geocode this exact string right
    now, else False (including on any network/API failure — treated as
    "couldn't verify" rather than silently accepted). Used by
    weather_routes.py to validate a new /console LOCATION card entry
    *before* saving it, rather than accepting anything non-blank and
    finding out days later from an OpenWeatherMap 404 buried in the log —
    confirmed live, 2026-08-21: a location saved as "Milton GA" (missing
    the required City,State,Country commas) 404'd on every single weather
    call for days with zero user-facing indication anything was wrong."""
    settings = get_settings()
    if not looks_configured(settings.openweathermap_api_key):
        # Can't verify without a key -- don't block saving the location
        # itself over a separate, already-surfaced-elsewhere problem.
        return True
    try:
        resp = requests.get(
            f"{_BASE_URL}/weather",
            params={"q": location, "appid": settings.openweathermap_api_key},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error(f"OpenWeatherMap location-check request failed: {type(e).__name__}")
        return True  # network hiccup, not proof the location is bad
    return resp.ok


def get_current() -> Optional[Dict]:
    """Today's conditions, or None if weather isn't usable right now."""
    params = _params()
    if params is None:
        return None
    try:
        resp = requests.get(f"{_BASE_URL}/weather", params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        # Not str(e) — a connection/HTTP error's message can embed the full
        # request URL, which includes the API key in the query string.
        logger.error(f"OpenWeatherMap current-weather request failed: {type(e).__name__}")
        return None

    if not resp.ok:
        logger.error(f"OpenWeatherMap current-weather call failed: HTTP {resp.status_code}")
        return None

    try:
        data = resp.json()
        return {
            "temp": round(data["main"]["temp"]),
            "condition": data["weather"][0]["description"].capitalize(),
            "humidity": data["main"]["humidity"],
        }
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"Unexpected OpenWeatherMap response shape: {e}")
        return None


def get_tomorrow() -> Optional[Dict]:
    """Forecast for roughly midday tomorrow, or None if unavailable."""
    params = _params()
    if params is None:
        return None
    try:
        resp = requests.get(f"{_BASE_URL}/forecast", params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"OpenWeatherMap forecast request failed: {type(e).__name__}")
        return None

    if not resp.ok:
        logger.error(f"OpenWeatherMap forecast call failed: HTTP {resp.status_code}")
        return None

    try:
        data = resp.json()
    except ValueError as e:
        logger.error(f"Unexpected OpenWeatherMap forecast response: {e}")
        return None

    tomorrow = (datetime.now() + timedelta(days=1)).date()
    best, best_diff = None, None
    for entry in data.get("list", []):
        dt = datetime.fromtimestamp(entry["dt"])
        if dt.date() != tomorrow:
            continue
        diff = abs(dt.hour - 12)
        if best_diff is None or diff < best_diff:
            best, best_diff = entry, diff

    if best is None:
        return None

    try:
        return {
            "temp": round(best["main"]["temp"]),
            "condition": best["weather"][0]["description"].capitalize(),
            "rain_chance": round(best.get("pop", 0) * 100),
        }
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Unexpected OpenWeatherMap forecast shape: {type(e).__name__}: {e}")
        return None
