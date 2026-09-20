"""Garmin Connect ingest -- sleep, resting HR, HRV, Body Battery, stress,
steps, training readiness and training load.

UNOFFICIAL API, DELIBERATELY
---------------------------
This uses the `garminconnect` library, not Garmin's official Health API. The official one requires a Garmin
Connect Developer / wellness-partner agreement -- an application and
approval process on Garmin's side, not an API key you can sign up for --
which is why this sat blocked in BACKLOG.md.

The consequences of that choice, stated plainly:

  - It can break without warning when Garmin changes their endpoints.
    Every call here is wrapped and returns None on failure, same
    fail-quiet contract as google_calendar/google_gmail/weather. A broken
    Garmin must degrade the brief's fitness section, never take down the
    brief.
  - It authenticates as you, so it is rate-limit-sensitive in a way a
    partner API is not. Pull ONCE OR TWICE A DAY. Do not poll. There is no
    loop in this module for that reason -- daily_ingest.py owns scheduling.
  - login(tokenstore=path) caches an OAuth session under
    .garmin_tokens/ after the first login and reuses it thereafter, so
    credentials are exchanged once rather than per call. MFA is
    reported and skipped rather than prompted for -- see _client().

METRIC NAMING
-------------
Everything lands in metrics_store under `garmin.*`. Names are stable
because they become chart series and, later, inputs to the composite
readiness score -- renaming one orphans its history.

"STRAIN" DOES NOT EXIST HERE
----------------------------
Garmin has no strain metric; that is Whoop's. The closest equivalents are
training load (acute), intensity minutes, and training readiness. The
composite score that blends these is deliberately NOT in this module --
this file only ingests what the watch actually reports, so that the score's
weights can be changed later without re-pulling anything.
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sunny_code.components import metrics_store
from sunny_code.config import get_settings, looks_configured

logger = logging.getLogger(__name__)

# Series names. `garmin.` prefix groups them in the dashboard and keeps
# them distinct from check-in answers (`health.*`) and server stats.
M_SLEEP_SCORE = "garmin.sleep_score"
M_SLEEP_HOURS = "garmin.sleep_hours"
M_RESTING_HR = "garmin.resting_hr"
M_HRV = "garmin.hrv_overnight"
M_BODY_BATTERY_WAKE = "garmin.body_battery_wake"
M_STRESS_AVG = "garmin.stress_avg"
M_STEPS = "garmin.steps"
M_TRAINING_READINESS = "garmin.training_readiness"
M_ACUTE_LOAD = "garmin.acute_load"
M_RESPIRATION = "garmin.respiration_avg"
M_SPO2 = "garmin.spo2_avg"
# Not a health metric -- records that a historical backfill completed, so
# the automatic first-run one happens once rather than on every restart.
M_BACKFILL_MARKER = "garmin.backfill_completed"

# How many recent days a routine pull re-fetches. Not 1: Garmin revises
# yesterday's sleep score and training readiness for hours after the fact,
# so pulling only "today" permanently stores whichever provisional value
# happened to exist at pull time. metrics_store upserts, so overlapping
# re-pulls are free.
ROUTINE_LOOKBACK_DAYS = 3


def _client():
    """An authenticated Garmin client, or None if unavailable.

    None covers every "cannot do this right now" case -- library missing,
    credentials unset, login rejected -- because every caller treats them
    identically: skip the fitness data, say so honestly, carry on.
    """
    settings = get_settings()
    email = getattr(settings, "garmin_email", "")
    password = getattr(settings, "garmin_password", "")
    if not looks_configured(email) or not looks_configured(password):
        return None

    try:
        from garminconnect import Garmin
    except ImportError:
        logger.warning("garminconnect not installed — Garmin ingest unavailable")
        return None

    try:
        token_dir = settings.project_root / ".garmin_tokens"
        # return_on_mfa is load-bearing in a daemon. Without it the library
        # calls its prompt_mfa callback, which reads a code from stdin --
        # and this runs under systemd with no stdin, so an MFA challenge
        # would hang the ingest thread indefinitely rather than failing.
        # Returning instead lets it be reported and skipped.
        try:
            client = Garmin(email, password, return_on_mfa=True)
        except TypeError:
            # Older garminconnect without the flag. Accepted rather than
            # hard-failed, but an MFA-protected account on such a version
            # is the hang described above.
            client = Garmin(email, password)

        # One call does everything: login(tokenstore) loads a cached
        # session when one exists, and after a fresh login dumps the new
        # tokens back to that path itself. An earlier version of this
        # called client.garth.dump() by hand -- garminconnect 0.3.x has no
        # `garth` attribute at all, so that silently failed and forced a
        # full SSO login on every single pull, which is exactly the
        # behavior this module's docstring says to avoid.
        result = client.login(str(token_dir))

        # (mfa_status, _) on modern versions; older ones return a bool or
        # None, hence the shape check rather than a bare truthiness test.
        mfa_status = result[0] if isinstance(result, tuple) and result else None
        if mfa_status:
            logger.error(
                "Garmin login needs an MFA code and this runs headless — "
                "run one interactive login on the server to cache a token: "
                "venv/bin/python -c \"from garminconnect import Garmin; "
                "g=Garmin(EMAIL,PASSWORD); g.login('.garmin_tokens')\""
            )
            return None

        return client
    except Exception as e:
        # Deliberately broad: the library raises its own exception types,
        # and a new one appearing after a Garmin-side change must not
        # escape into the caller.
        logger.error(f"Garmin login failed: {type(e).__name__}: {e}")
        return None


def _num(value) -> Optional[float]:
    """Coerce a Garmin field to a float, or None. Garmin returns nulls,
    empty strings and occasionally strings-that-are-numbers depending on
    which endpoint a field came from."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe(fn, label: str):
    """Call one Garmin endpoint, swallowing failures. Each endpoint is
    fetched independently so one unavailable metric (Pulse Ox off, a watch
    that does not report HRV) does not cost every other metric for that
    day."""
    try:
        return fn()
    except Exception as e:
        logger.warning(f"Garmin {label} unavailable: {type(e).__name__}: {e}")
        return None


def fetch_day(client, day: date) -> Dict[str, Optional[float]]:
    """Every supported metric for one date, as {series_name: value}.

    Missing metrics are simply absent rather than zero -- metrics_store's
    record_many() skips None, because "the watch did not report this" and
    "this was zero" are different facts and only one of them should be
    chartable.
    """
    iso = day.isoformat()
    out: Dict[str, Optional[float]] = {}

    sleep = _safe(lambda: client.get_sleep_data(iso), "sleep")
    if isinstance(sleep, dict):
        daily = sleep.get("dailySleepDTO") or {}
        out[M_SLEEP_SCORE] = _num((daily.get("sleepScores") or {}).get("overall", {}).get("value")) \
            if isinstance(daily.get("sleepScores"), dict) else None
        seconds = _num(daily.get("sleepTimeSeconds"))
        out[M_SLEEP_HOURS] = round(seconds / 3600, 2) if seconds else None
        out[M_RESPIRATION] = _num(daily.get("averageRespirationValue"))
        out[M_SPO2] = _num(daily.get("averageSpO2Value"))

    stats = _safe(lambda: client.get_stats(iso), "daily stats")
    if isinstance(stats, dict):
        out[M_RESTING_HR] = _num(stats.get("restingHeartRate"))
        out[M_STEPS] = _num(stats.get("totalSteps"))
        out[M_STRESS_AVG] = _num(stats.get("averageStressLevel"))

    hrv = _safe(lambda: client.get_hrv_data(iso), "HRV")
    if isinstance(hrv, dict):
        summary = hrv.get("hrvSummary") or {}
        out[M_HRV] = _num(summary.get("lastNightAvg"))

    battery = _safe(lambda: client.get_body_battery(iso, iso), "body battery")
    if isinstance(battery, list) and battery:
        entry = battery[0] if isinstance(battery[0], dict) else {}
        # Wake-time reading, not the current one: Body Battery drains
        # through the day, so "what did I start with" is the figure worth
        # a daily row. The max over the day is the closest proxy the API
        # exposes without walking the per-minute series.
        out[M_BODY_BATTERY_WAKE] = _num(entry.get("charged")) or _num(entry.get("maxBodyBattery"))

    readiness = _safe(lambda: client.get_training_readiness(iso), "training readiness")
    if isinstance(readiness, list) and readiness and isinstance(readiness[0], dict):
        out[M_TRAINING_READINESS] = _num(readiness[0].get("score"))

    load = _safe(lambda: client.get_training_status(iso), "training status")
    if isinstance(load, dict):
        acute = load.get("acuteTrainingLoadDTO") or {}
        out[M_ACUTE_LOAD] = _num(acute.get("acuteTrainingLoad"))

    return out


def ingest(days: int = ROUTINE_LOOKBACK_DAYS) -> Dict:
    """Pull the last `days` days and store them. Returns a small result
    summary rather than raising, so a scheduler can log it and move on.

    Not scheduled here -- see daily_ingest.py. This module deliberately
    owns no loop, so nothing can accidentally start polling an unofficial
    API as you.
    """
    client = _client()
    if client is None:
        return {"ok": False, "reason": "not_configured", "days": 0, "points": 0}

    today = date.today()
    stored_days, stored_points = 0, 0
    for offset in range(days):
        day = today - timedelta(days=offset)
        metrics = fetch_day(client, day)
        written = metrics_store.record_many(metrics, ts=day.isoformat())
        if written:
            stored_days += 1
            stored_points += written

    logger.info(f"Garmin ingest: {stored_points} points across {stored_days} days")
    return {"ok": True, "reason": None, "days": stored_days, "points": stored_points}


def _row_date(row: Dict) -> Optional[str]:
    """The calendar date out of a bulk-endpoint row.

    Key names differ per endpoint and have changed across library
    versions, so this tries the known spellings rather than assuming one.
    Returns an ISO date string or None.
    """
    for key in ("calendarDate", "calendar_date", "date", "statisticsStartDate"):
        value = row.get(key)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    # Some rows carry only a timestamp.
    for key in ("startTimestampLocal", "startTimestampGMT", "timestamp"):
        value = row.get(key)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    return None


def _row_value(row: Dict, *keys: str) -> Optional[float]:
    """The first present numeric field among `keys`, checking both the row
    itself and a nested `values` dict (several Garmin bulk endpoints wrap
    their payload that way)."""
    nested = row.get("values") if isinstance(row.get("values"), dict) else {}
    for key in keys:
        for source in (row, nested):
            if key in source:
                number = _num(source.get(key))
                if number is not None:
                    return number
    return None


# Bulk endpoints: (metric name, client method, arg style, value key candidates).
# Every one of these replaces a per-day call, which is what makes a long
# backfill viable -- see backfill()'s docstring.
_BULK_SOURCES = [
    (M_SLEEP_SCORE, "get_sleep_daily", ("sleepScore", "overallScore", "score", "value")),
    (M_RESTING_HR, "get_rhr_daily", ("restingHeartRate", "value", "restingHR")),
    (M_STEPS, "get_daily_steps", ("totalSteps", "steps", "value")),
    (M_HRV, "get_hrv_data_range", ("lastNightAvg", "weeklyAvg", "value")),
]

# Days per range request. Garmin rejects or truncates very wide windows on
# some endpoints, and a smaller chunk also means a failure costs less work.
_CHUNK_DAYS = 28

# Pause between API calls. An unofficial endpoint authenticated as the user
# is exactly the wrong place to hammer, and a backfill is the only code
# path here that makes many calls in a row.
_THROTTLE_SECONDS = 1.5

# Training readiness and training status have no range endpoint, so they
# cost one call per day. They're also only produced by newer watches and
# only meaningful recently, so a full-history per-day sweep for them would
# be thousands of calls for mostly-empty results. Recent window only.
_PER_DAY_RECENT_WINDOW = 60

# How far back an automatic first-run backfill reaches. A year covers a
# full seasonal cycle (which is what makes the barometric-pressure and
# sleep correlations interesting) without the call volume of "everything".
DEFAULT_BACKFILL_DAYS = 365


def _backfill_bulk(client, start: date, end: date) -> int:
    """Range-endpoint pass. Returns points stored."""
    stored = 0
    for metric, method_name, value_keys in _BULK_SOURCES:
        method = getattr(client, method_name, None)
        if method is None:
            logger.warning(f"garminconnect has no {method_name} — skipping {metric}")
            continue

        window_start = start
        logged_shape = False
        while window_start <= end:
            window_end = min(window_start + timedelta(days=_CHUNK_DAYS - 1), end)
            rows = _safe(
                lambda: method(window_start.isoformat(), window_end.isoformat()),
                f"{method_name} {window_start}..{window_end}",
            )
            time.sleep(_THROTTLE_SECONDS)

            # Endpoints vary: some return a list, some a dict wrapping one.
            if isinstance(rows, dict):
                for key in ("hrvSummaries", "dailySleepDTO", "values", "items"):
                    if isinstance(rows.get(key), list):
                        rows = rows[key]
                        break
                else:
                    rows = [rows]
            if not isinstance(rows, list):
                window_start = window_end + timedelta(days=1)
                continue

            # Log the real shape once per metric. Without this, a changed
            # field name stores nothing and looks identical to "no data" --
            # this turns that into one greppable log line.
            if rows and not logged_shape:
                sample = rows[0] if isinstance(rows[0], dict) else {}
                logger.info(f"Garmin {method_name} row keys: {sorted(sample.keys())[:12]}")
                logged_shape = True

            batch: Dict[str, float] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                day_key = _row_date(row)
                value = _row_value(row, *value_keys)
                if day_key and value is not None:
                    batch[day_key] = value

            for day_key, value in batch.items():
                metrics_store.record(metric, value, ts=day_key)
            stored += len(batch)

            window_start = window_end + timedelta(days=1)

    return stored


def _backfill_per_day(client, start: date, end: date) -> int:
    """Per-day pass for metrics with no range endpoint. Deliberately
    limited to the recent window -- see _PER_DAY_RECENT_WINDOW."""
    stored = 0
    day = max(start, end - timedelta(days=_PER_DAY_RECENT_WINDOW - 1))
    while day <= end:
        metrics: Dict[str, Optional[float]] = {}

        readiness = _safe(lambda: client.get_training_readiness(day.isoformat()), "training readiness")
        if isinstance(readiness, list) and readiness and isinstance(readiness[0], dict):
            metrics[M_TRAINING_READINESS] = _num(readiness[0].get("score"))
        time.sleep(_THROTTLE_SECONDS)

        status = _safe(lambda: client.get_training_status(day.isoformat()), "training status")
        if isinstance(status, dict):
            acute = status.get("acuteTrainingLoadDTO") or {}
            metrics[M_ACUTE_LOAD] = _num(acute.get("acuteTrainingLoad"))
        time.sleep(_THROTTLE_SECONDS)

        stored += metrics_store.record_many(metrics, ts=day.isoformat())
        day += timedelta(days=1)

    return stored


def backfill(start: Optional[date] = None, end: Optional[date] = None) -> Dict:
    """Historical pull from `start` (default: DEFAULT_BACKFILL_DAYS ago) to
    `end` (default today).

    Garmin retains this history server-side, which is why most of the
    health dataset can be recovered after the fact and check-in answers
    cannot.

    Two passes, for a reason worth stating. Most metrics have a bulk range
    endpoint (get_sleep_daily, get_rhr_daily, get_daily_steps,
    get_hrv_data_range), so a year of those costs roughly 65 calls in
    28-day chunks rather than one call per metric per day. Training
    readiness and acute load have no range variant, so they'd cost a call
    each per day -- and they only exist on newer watches and only matter
    recently, so those are fetched for the last 60 days only. Sweeping a
    year per-day for them would be thousands of calls against an
    unofficial endpoint for mostly-empty rows.

    Every call is throttled. This is the only path here that makes many
    requests in a row, and it is authenticated as the user.
    """
    client = _client()
    if client is None:
        return {"ok": False, "reason": "not_configured", "points": 0}

    end = end or date.today()
    start = start or (end - timedelta(days=DEFAULT_BACKFILL_DAYS))
    if start > end:
        return {"ok": False, "reason": "start_after_end", "points": 0}

    logger.info(f"Garmin backfill starting: {start}..{end}")
    points = _backfill_bulk(client, start, end)
    points += _backfill_per_day(client, start, end)

    metrics_store.record(M_BACKFILL_MARKER, 1.0, ts=date.today().isoformat())
    logger.info(f"Garmin backfill {start}..{end} complete: {points} points")
    return {"ok": True, "reason": None, "points": points, "start": start.isoformat(), "end": end.isoformat()}


def has_backfilled() -> bool:
    """Whether a backfill has ever completed. Used so the automatic
    first-run backfill happens exactly once rather than on every restart."""
    return metrics_store.latest(M_BACKFILL_MARKER) is not None


def status() -> Dict:
    """Whether Garmin is configured and when it last produced data --
    for the setup guide and the dashboard's connection list."""
    settings = get_settings()
    configured = looks_configured(getattr(settings, "garmin_email", "")) and \
        looks_configured(getattr(settings, "garmin_password", ""))
    try:
        from garminconnect import Garmin  # noqa: F401
        installed = True
    except ImportError:
        installed = False

    latest = metrics_store.latest(M_SLEEP_SCORE) or metrics_store.latest(M_RESTING_HR)
    return {
        "configured": configured,
        "library_installed": installed,
        "last_data": latest["ts"] if latest else None,
    }


def recent(names: Optional[List[str]] = None, days: int = 7) -> Dict[str, List[Dict]]:
    """Recent series for the named metrics (default: the brief's set),
    for the fitness section of a briefing."""
    names = names or [M_SLEEP_SCORE, M_SLEEP_HOURS, M_BODY_BATTERY_WAKE, M_TRAINING_READINESS, M_STEPS]
    start = (date.today() - timedelta(days=days)).isoformat()
    return {name: metrics_store.series(name, start=start) for name in names}
