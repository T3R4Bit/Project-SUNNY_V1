"""Live weather reads via OpenWeatherMap — needs both OPENWEATHERMAP_API_KEY
and WEATHER_LOCATION (a lat/lon or "City,State,CountryCode" isn't enough on
its own; OpenWeatherMap can't answer without knowing where).

Same fail-quietly contract as google_calendar/google_gmail: any error (bad
key, bad location, network failure) returns None, never raises — callers
treat None exactly like "not connected."
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import requests

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openweathermap.org/data/2.5"
_TIMEOUT = 5


def _params() -> Optional[dict]:
    settings = get_settings()
    if not settings.openweathermap_api_key or not settings.weather_location:
        return None
    return {
        "q": settings.weather_location,
        "appid": settings.openweathermap_api_key,
        "units": "imperial",
    }


def get_current() -> Optional[Dict]:
    """Today's conditions, or None if weather isn't usable right now."""
    params = _params()
    if params is None:
        return None
    try:
        resp = requests.get(f"{_BASE_URL}/weather", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"OpenWeatherMap current-weather call failed: {e}")
        return None

    try:
        return {
            "temp": round(data["main"]["temp"]),
            "condition": data["weather"][0]["description"].capitalize(),
            "humidity": data["main"]["humidity"],
        }
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Unexpected OpenWeatherMap response shape: {e}")
        return None


def get_tomorrow() -> Optional[Dict]:
    """Forecast for roughly midday tomorrow, or None if unavailable."""
    params = _params()
    if params is None:
        return None
    try:
        resp = requests.get(f"{_BASE_URL}/forecast", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"OpenWeatherMap forecast call failed: {e}")
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
        logger.error(f"Unexpected OpenWeatherMap forecast shape: {e}")
        return None
