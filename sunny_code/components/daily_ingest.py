"""The once-a-day job that captures everything time-sensitive.

Owns scheduling so that garmin_client.py does not. That separation is
deliberate: garmin_client talks to an unofficial API authenticated as the
user, and the single most important property of that integration is that
nothing ever polls it. Keeping every loop out of that module makes the
rule structural rather than a comment someone might not read.

WHAT RUNS HERE, AND WHY EACH IS DAILY
-------------------------------------
  - Garmin pull, re-fetching the last few days. Garmin revises yesterday's
    sleep score and readiness for hours after the fact, so a same-day-only
    pull stores whichever provisional number happened to exist at the time.
  - Barometric pressure. The reason this job exists at all on a day when
    Garmin is not yet connected: pressure is the one input to the migraine
    correlation that CANNOT be recovered later. Garmin retains history;
    OpenWeatherMap's free tier does not serve the past. A day missed here
    is a permanent hole in exactly the dataset the nightly check-in is
    being collected to support.

Both are best-effort and independent. Garmin being unconfigured must not
stop pressure being logged, which is the state this will actually be in
until the Garmin credentials are added.
"""

import logging
from typing import Dict

from sunny_code.components import day_boundary, garmin_client, metrics_store, weather

logger = logging.getLogger(__name__)

M_PRESSURE = "weather.pressure_hpa"

# Runs on a slow loop rather than at a fixed clock time so that a restart
# does not skip the day. Twice daily: enough to catch Garmin's revisions
# to the previous night, nowhere near often enough to look like polling.
INTERVAL_HOURS = 12


def capture_pressure() -> int:
    """Log barometric pressure for every location the briefs report on.

    Returns how many locations were stored.

    Three locations, not one. The morning brief already shows weather for
    Home, for campus on class days and for Marietta on Mondays (see
    briefing._weather_locations_for), and you are physically in those
    places -- so a migraine correlation built only on the home reading is
    correlating against pressure somewhere you were not. They are close
    enough that the readings usually agree and far enough that sometimes
    they do not, which is exactly when the correlation matters.

    `weather.pressure_hpa` stays the Home series so existing history is
    unbroken; the others get their own suffixed series rather than being
    averaged, because averaging would hide the disagreement that makes
    them worth capturing.

    Stored against the logging day, so a reading taken at 1am lands on the
    day being lived -- matching how the check-in answer it will be
    correlated against is filed.
    """
    day = day_boundary.day_key()
    stored = 0

    for metric, location in _pressure_locations():
        current = weather.get_current(location) if location else weather.get_current()
        if not current:
            logger.info(f"Pressure capture skipped for {metric} — weather unavailable")
            continue
        pressure = current.get("pressure")
        if pressure is None:
            logger.info(f"Pressure capture skipped for {metric} — none in response")
            continue
        metrics_store.record(metric, float(pressure), ts=day)
        stored += 1

    return stored


def _pressure_locations():
    """[(metric, location_override)] for today.

    Imported lazily from briefing to avoid a circular import -- briefing
    already imports this module's M_PRESSURE indirectly through the
    wellness section.
    """
    from sunny_code.components.briefing import _weather_locations_for
    from datetime import date as _date

    out = [(M_PRESSURE, None)]
    for label, override in _weather_locations_for(_date.today()):
        if override is None:
            continue  # "Home" is the default entry above
        out.append((f"{M_PRESSURE}.{label.lower()}", override))
    return out


def run() -> Dict:
    """Run every daily capture. Returns a summary for the caller to log.
    Never raises: a scheduler calling this must not need a try/except, and
    one failing source must not cost the others."""
    result: Dict = {"pressure": False, "garmin": None}

    try:
        result["pressure"] = capture_pressure()  # locations stored
    except Exception as e:
        logger.error(f"Pressure capture failed: {e}", exc_info=True)

    try:
        result["garmin"] = garmin_client.ingest()
    except Exception as e:
        logger.error(f"Garmin ingest failed: {e}", exc_info=True)
        result["garmin"] = {"ok": False, "reason": "exception", "days": 0, "points": 0}

    # First successful connection pulls the history automatically, once.
    # Garmin retains it server-side, so there's no reason to make someone
    # remember to trigger a one-off endpoint -- and every day it isn't
    # pulled is a day the charts and (later) the readiness weights have
    # less to work with. Guarded by a stored marker rather than a config
    # flag so a restart can't repeat it.
    garmin_ok = (result["garmin"] or {}).get("ok")
    if garmin_ok and not garmin_client.has_backfilled():
        try:
            logger.info("First successful Garmin connection — starting one-time history backfill")
            result["backfill"] = garmin_client.backfill()
        except Exception as e:
            # A failed backfill must not mark itself done, so the next run
            # retries. It also must not cost the routine ingest above,
            # which has already stored today's data by this point.
            logger.error(f"Garmin backfill failed: {e}", exc_info=True)
            result["backfill"] = {"ok": False, "reason": "exception", "points": 0}

    logger.info(f"Daily ingest complete: {result}")
    return result
