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


def capture_pressure() -> bool:
    """Log today's barometric pressure. True if a value was stored.

    Stored against the logging day, so a reading taken at 1am lands on the
    day being lived -- matching how the check-in answer it will be
    correlated against is filed.
    """
    current = weather.get_current()
    if not current:
        logger.info("Pressure capture skipped — weather unavailable")
        return False

    pressure = current.get("pressure")
    if pressure is None:
        logger.info("Pressure capture skipped — no pressure in weather response")
        return False

    metrics_store.record(M_PRESSURE, float(pressure), ts=day_boundary.day_key())
    return True


def run() -> Dict:
    """Run every daily capture. Returns a summary for the caller to log.
    Never raises: a scheduler calling this must not need a try/except, and
    one failing source must not cost the others."""
    result: Dict = {"pressure": False, "garmin": None}

    try:
        result["pressure"] = capture_pressure()
    except Exception as e:
        logger.error(f"Pressure capture failed: {e}", exc_info=True)

    try:
        result["garmin"] = garmin_client.ingest()
    except Exception as e:
        logger.error(f"Garmin ingest failed: {e}", exc_info=True)
        result["garmin"] = {"ok": False, "reason": "exception", "days": 0, "points": 0}

    logger.info(f"Daily ingest complete: {result}")
    return result
