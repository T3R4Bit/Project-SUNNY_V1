"""Generic time-series store: one table, `(name, ts) -> value`.

Replaces the fixed-column `metrics` table in dashboard.py, which had a
column per thing worth measuring (cpu_percent, ram_percent, disk_percent,
cpu_temp, tokens_used, tokens_cost) and therefore needed a schema
migration every time something new became worth measuring. Nothing ever
wrote to it -- record_metric() has no callers anywhere in the codebase --
so there is no data to migrate, only a shape to stop repeating.

Everything chartable goes here: Garmin readiness/sleep/steps, check-in
answers, barometric pressure, API spend, server stats. One table means one
series endpoint and therefore one chart component with one range selector,
rather than a bespoke query and renderer per metric.

UPSERT, NOT APPEND
------------------
The primary key is (name, ts), and writes are INSERT OR REPLACE. This is
load-bearing for backfill: Garmin ingest re-pulls recent days on every run
(yesterday's sleep score is often revised hours after the fact, and a
backfill deliberately overlaps what is already stored), so an append-only
table would accumulate silent duplicates and every average over a range
would be wrong in a way nothing would surface. Re-ingesting the same day
must be idempotent.

TIMESTAMP CONVENTION
--------------------
`ts` is an ISO-8601 string, and its precision carries meaning:

  - Daily metrics store a bare date ("2026-09-20"). These are day-grained
    facts -- last night's sleep score is not a reading taken at a moment,
    it describes a whole night. The day comes from day_boundary.day_key(),
    never date.today().
  - Sampled metrics store a full datetime ("2026-09-20T14:30:00").

Both sort correctly as strings, which is what lets a range query be a
plain BETWEEN with no date parsing in SQL.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from sunny_code.components.db_connection import closing_transaction
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Bucket sizes for series(). "raw" returns every stored point; the others
# aggregate. Chosen to match what a range selector actually needs -- a year
# of daily points is 365 rows, which is fine to send to a chart as-is, so
# there is no need for anything coarser than a day.
BUCKET_RAW = "raw"
BUCKET_HOUR = "hour"
BUCKET_DAY = "day"

# How to combine points inside a bucket.
AGG_AVG = "avg"
AGG_SUM = "sum"
AGG_MIN = "min"
AGG_MAX = "max"
AGG_LAST = "last"

_AGG_SQL = {
    AGG_AVG: "AVG(value)",
    AGG_SUM: "SUM(value)",
    AGG_MIN: "MIN(value)",
    AGG_MAX: "MAX(value)",
    # LAST is the value at the greatest ts in the bucket. Needed for
    # cumulative readings (a step count is already a running total, so
    # summing samples within a day would multiply it).
    AGG_LAST: "value",
}


def _db_path() -> Path:
    return get_settings().project_root / "sunny.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the table if absent. Safe to call repeatedly; called at
    import-time by the first write or read rather than needing wiring into
    startup."""
    with closing_transaction(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_series (
                name  TEXT NOT NULL,
                ts    TEXT NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY (name, ts)
            )
            """
        )
        # Range queries are always "one metric, ordered by time" -- the
        # composite primary key already serves that, but an explicit index
        # on (name, ts) makes the intent obvious to anyone reading the
        # schema and costs nothing on a table this small.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metric_series_name_ts ON metric_series (name, ts)"
        )


def record(name: str, value: float, ts: Optional[str] = None) -> None:
    """Store one point. `ts` defaults to today's logging day (see
    day_boundary) -- i.e. a bare date, appropriate for a daily metric. Pass
    an explicit ISO datetime for a sampled one.

    Re-recording the same (name, ts) overwrites rather than duplicating;
    see the module docstring on why that is required, not merely
    convenient."""
    from sunny_code.components import day_boundary

    ts = ts or day_boundary.day_key()
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metric_series (name, ts, value) VALUES (?, ?, ?)",
                (name, ts, float(value)),
            )
    except (sqlite3.Error, TypeError, ValueError) as e:
        # Same fail-quiet contract as every other integration here: a
        # metric that cannot be stored must never take down the caller
        # that produced it (a brief, an ingest run, a check-in reply).
        logger.error(f"Failed to record metric {name!r}: {e}", exc_info=True)


def record_many(points: Dict[str, float], ts: Optional[str] = None) -> int:
    """Store several metrics sharing one timestamp -- the normal shape of a
    Garmin daily pull or a server-stats sample. Returns how many were
    written. None values are skipped rather than stored as 0, since "the
    watch did not report this" and "this was zero" are different facts."""
    from sunny_code.components import day_boundary

    ts = ts or day_boundary.day_key()
    usable = {k: v for k, v in points.items() if v is not None}
    if not usable:
        return 0

    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO metric_series (name, ts, value) VALUES (?, ?, ?)",
                [(name, ts, float(v)) for name, v in usable.items()],
            )
        return len(usable)
    except (sqlite3.Error, TypeError, ValueError) as e:
        logger.error(f"Failed to record metrics {sorted(usable)}: {e}", exc_info=True)
        return 0


def latest(name: str) -> Optional[Dict]:
    """The most recent point for `name`, or None if never recorded."""
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            row = conn.execute(
                "SELECT ts, value FROM metric_series WHERE name = ? ORDER BY ts DESC LIMIT 1",
                (name,),
            ).fetchone()
    except sqlite3.Error as e:
        logger.error(f"Failed to read latest {name!r}: {e}", exc_info=True)
        return None
    return {"ts": row["ts"], "value": row["value"]} if row else None


def get_for_day(name: str, day: str) -> Optional[float]:
    """The value stored for a specific logging day, or None. For daily
    metrics only -- matches on the exact date key."""
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            row = conn.execute(
                "SELECT value FROM metric_series WHERE name = ? AND ts = ?", (name, day)
            ).fetchone()
    except sqlite3.Error as e:
        logger.error(f"Failed to read {name!r} for {day}: {e}", exc_info=True)
        return None
    return row["value"] if row else None


def series(
    name: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    bucket: str = BUCKET_RAW,
    agg: str = AGG_AVG,
) -> List[Dict]:
    """Points for `name` between `start` and `end` (inclusive ISO strings),
    optionally aggregated into buckets.

    Because daily metrics are stored as bare dates and BETWEEN is a string
    comparison, an `end` of "2026-09-20" correctly includes that day's
    daily row. A full datetime end ("2026-09-20T00:00:00") would not --
    pass dates when querying daily metrics, which is what the API layer
    does.
    """
    init_db()

    if bucket == BUCKET_DAY:
        bucket_expr = "substr(ts, 1, 10)"
    elif bucket == BUCKET_HOUR:
        bucket_expr = "substr(ts, 1, 13)"
    else:
        bucket_expr = None

    clauses = ["name = ?"]
    params: List = [name]
    if start:
        clauses.append("ts >= ?")
        params.append(start)
    if end:
        clauses.append("ts <= ?")
        params.append(end)
    where = " AND ".join(clauses)

    if bucket_expr is None:
        query = f"SELECT ts, value FROM metric_series WHERE {where} ORDER BY ts"
    elif agg == AGG_LAST:
        # The value at the latest ts within each bucket. A correlated
        # subquery rather than a window function, because the SQLite
        # bundled with older Python builds may predate window support and
        # this table is small enough that it does not matter.
        query = f"""
            SELECT {bucket_expr} AS ts, value FROM metric_series m WHERE {where}
              AND ts = (SELECT MAX(ts) FROM metric_series x
                        WHERE x.name = m.name AND {bucket_expr.replace('ts', 'x.ts')} = {bucket_expr})
            ORDER BY ts
        """
    else:
        agg_sql = _AGG_SQL.get(agg, _AGG_SQL[AGG_AVG])
        query = f"""
            SELECT {bucket_expr} AS ts, {agg_sql} AS value
            FROM metric_series WHERE {where}
            GROUP BY {bucket_expr} ORDER BY ts
        """

    try:
        with closing_transaction(_connect()) as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error as e:
        logger.error(f"Failed to read series {name!r}: {e}", exc_info=True)
        return []

    return [{"ts": r["ts"], "value": r["value"]} for r in rows]


def known_metrics() -> List[str]:
    """Every metric name with at least one stored point, alphabetically.
    Lets the dashboard discover what is chartable instead of hardcoding a
    list that drifts as new metrics get added."""
    init_db()
    try:
        with closing_transaction(_connect()) as conn:
            rows = conn.execute(
                "SELECT DISTINCT name FROM metric_series ORDER BY name"
            ).fetchall()
    except sqlite3.Error as e:
        logger.error(f"Failed to list metrics: {e}", exc_info=True)
        return []
    return [r["name"] for r in rows]
