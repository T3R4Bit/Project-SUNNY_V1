"""HTTP API over metrics_store -- the one endpoint every chart reads.

Built as a generic series endpoint rather than a route per metric so that
the dashboard's range selector (1D/1W/1M/3M/1Y/ALL) is written once and
pointed at whatever series exists, instead of needing a new route and a
new chart component each time something becomes worth measuring. Adding a
metric anywhere in the codebase makes it chartable here with no API change.

Also carries the check-in read/write routes, because a check-in answer is
just a metric with a question attached to it, and the PWA needs to be able
to answer one without going through Discord.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sunny_code.components import checkin, daily_ingest, day_boundary, garmin_client, metrics_store

logger = logging.getLogger(__name__)

# Range selector presets, in days. "all" is absent deliberately -- it maps
# to no start bound rather than to a very large number.
RANGE_DAYS = {"1d": 1, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}


class CheckinAnswer(BaseModel):
    question_id: str
    # Free text rather than a number: the PWA sends a tapped "yes"/"no",
    # but so does a voice reply routed here, and parsing belongs in one
    # place (checkin.parse_answer) rather than in each caller.
    answer: str
    # Optional explicit day for correcting an earlier entry. Omitted means
    # today's logging day, which is almost always what is wanted.
    day: Optional[str] = None


class BackfillRequest(BaseModel):
    start: str
    end: Optional[str] = None


def create_metrics_router() -> APIRouter:
    router = APIRouter()

    @router.get("/metrics/series")
    async def metric_series(
        name: str,
        range: str = Query("1m", description="1d|1w|1m|3m|6m|1y|all"),
        bucket: str = Query(metrics_store.BUCKET_RAW, description="raw|hour|day"),
        agg: str = Query(metrics_store.AGG_AVG, description="avg|sum|min|max|last"),
    ):
        """One metric over a range. `range` is a preset rather than
        free-form dates because every caller is a range-selector button;
        explicit from/to is available via /metrics/series/window below."""
        start = None
        if range != "all":
            days = RANGE_DAYS.get(range.lower())
            if days is None:
                raise HTTPException(status_code=400, detail=f"Unknown range {range!r}")
            start = (date.today() - timedelta(days=days)).isoformat()

        points = metrics_store.series(name, start=start, bucket=bucket, agg=agg)
        return {"name": name, "range": range, "bucket": bucket, "points": points}

    @router.get("/metrics/series/window")
    async def metric_series_window(
        name: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        bucket: str = Query(metrics_store.BUCKET_RAW),
        agg: str = Query(metrics_store.AGG_AVG),
    ):
        """Explicit ISO date/datetime bounds, for a chart that has been
        zoomed or panned off the presets."""
        points = metrics_store.series(name, start=start, end=end, bucket=bucket, agg=agg)
        return {"name": name, "start": start, "end": end, "bucket": bucket, "points": points}

    @router.get("/metrics/available")
    async def available_metrics():
        """Every series with at least one stored point. Lets the dashboard
        discover what is chartable rather than hardcoding a list that
        drifts as metrics are added."""
        return {"metrics": metrics_store.known_metrics()}

    @router.get("/metrics/latest")
    async def latest_metric(name: str):
        point = metrics_store.latest(name)
        if point is None:
            return {"name": name, "available": False, "point": None}
        return {"name": name, "available": True, "point": point}

    # --- check-in ---------------------------------------------------------

    @router.get("/checkin/pending")
    async def checkin_pending():
        """What is still unanswered for today's logging day. `day` is
        returned explicitly so a client showing "today" agrees with the
        5am boundary instead of using its own midnight."""
        day = day_boundary.day_key()
        question = checkin.next_question(day)
        return {
            "day": day,
            "question": {
                "id": question["id"],
                "prompt": question["prompt"],
                "type": question["type"],
            } if question else None,
            "answered": checkin.answered(day),
        }

    @router.post("/checkin/answer")
    async def checkin_answer(body: CheckinAnswer):
        question = checkin._BY_ID.get(body.question_id)
        if question is None:
            raise HTTPException(status_code=404, detail=f"Unknown question {body.question_id!r}")

        value = checkin.parse_answer(question, body.answer)
        if value is None:
            # 422 rather than silently storing something: an unparseable
            # answer must not become a 0, which would be indistinguishable
            # from a real "no" forever after.
            raise HTTPException(
                status_code=422,
                detail=f"Could not read {body.answer!r} as an answer to {question['prompt']!r}",
            )

        day = body.day or day_boundary.day_key()
        checkin.record_answer(body.question_id, value, day=day)
        return {"ok": True, "day": day, "question_id": body.question_id, "value": value}

    @router.get("/checkin/history")
    async def checkin_history(days: int = Query(30, ge=1, le=365)):
        """Answers over the last N days, one series per question -- the
        migraine chart on the dashboard."""
        start = (date.today() - timedelta(days=days)).isoformat()
        return {
            q["id"]: metrics_store.series(q["metric"], start=start)
            for q in checkin.QUESTIONS
        }

    # --- health data sources ---------------------------------------------

    @router.get("/health/garmin/status")
    async def garmin_status():
        return garmin_client.status()

    @router.post("/health/garmin/ingest")
    async def garmin_ingest(days: int = Query(garmin_client.ROUTINE_LOOKBACK_DAYS, ge=1, le=30)):
        """Trigger a pull by hand. The scheduled job covers normal
        operation; this exists for the first run after adding credentials,
        when waiting up to 12 hours to find out whether they work is the
        wrong feedback loop."""
        return garmin_client.ingest(days=days)

    @router.post("/health/garmin/backfill")
    async def garmin_backfill(body: BackfillRequest):
        """Historical pull. Deliberately POST and deliberately manual --
        a long backfill is many sequential calls against an unofficial API."""
        try:
            start = datetime.fromisoformat(body.start).date()
            end = datetime.fromisoformat(body.end).date() if body.end else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Bad date: {e}")
        return garmin_client.backfill(start, end)

    @router.post("/health/ingest/run")
    async def run_daily_ingest():
        """Run the whole daily capture now (pressure + Garmin)."""
        return daily_ingest.run()

    return router
