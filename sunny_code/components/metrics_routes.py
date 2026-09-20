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

from sunny_code.components import (
    checkin, daily_ingest, day_boundary, garmin_client, metrics_store, readiness, workouts,
)

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
    # Both optional: omitting them backfills the default window
    # (garmin_client.DEFAULT_BACKFILL_DAYS) ending today, which is what the
    # automatic first-run backfill does.
    start: Optional[str] = None
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

    @router.get("/health/summary")
    async def health_summary(days: int = Query(30, ge=7, le=365)):
        """Everything the website's health panel needs, in one call.

        Each metric returns today's value, a recent average to compare it
        against, and the raw series for a sparkline. The comparison is the
        point: "6.1 hours" means nothing on its own, but "6.1 vs 7.4
        average" is a fact you can act on. Doing this server-side keeps the
        dashboard from making one request per metric.

        `available` is False when nothing has ever been ingested, so the
        page can show an honest "not connected yet" instead of a grid of
        blanks -- same contract as every other data source here.
        """
        start = (date.today() - timedelta(days=days)).isoformat()
        today = day_boundary.day_key()

        # (series name, label, unit, decimals, higher_is_better)
        tracked = [
            (readiness.M_SCORE, "Sunny Readiness", "", 0, True),
            (garmin_client.M_TRAINING_READINESS, "Training readiness", "", 0, True),
            (garmin_client.M_BODY_BATTERY_WAKE, "Body Battery at wake", "", 0, True),
            (garmin_client.M_SLEEP_HOURS, "Sleep", "h", 1, True),
            (garmin_client.M_SLEEP_SCORE, "Sleep score", "", 0, True),
            (garmin_client.M_RESTING_HR, "Resting HR", "bpm", 0, False),
            (garmin_client.M_HRV, "Overnight HRV", "ms", 0, True),
            (garmin_client.M_STEPS, "Steps", "", 0, True),
            (garmin_client.M_STRESS_AVG, "Average stress", "", 0, False),
            (garmin_client.M_ACUTE_LOAD, "Acute load", "", 0, None),
            (garmin_client.M_RESPIRATION, "Respiration", "br/min", 0, None),
            (garmin_client.M_SPO2, "SpO₂", "%", 0, True),
            (garmin_client.M_SKIN_TEMP, "Skin temp", "°C", 1, None),
            (garmin_client.M_VO2MAX, "VO₂ max", "", 1, True),
            (garmin_client.M_LOAD_AEROBIC_LOW, "Aerobic base load", "", 0, True),
            (garmin_client.M_LOAD_AEROBIC_HIGH, "Aerobic high load", "", 0, True),
            (garmin_client.M_LOAD_ANAEROBIC, "Anaerobic load", "", 0, True),
            (daily_ingest.M_PRESSURE, "Pressure", "hPa", 0, None),
        ]

        out = {}
        any_data = False
        for name, label, unit, decimals, higher_better in tracked:
            points = metrics_store.series(name, start=start)
            if not points:
                continue
            any_data = True
            values = [p["value"] for p in points]
            current = metrics_store.get_for_day(name, today)
            # Average excludes today so "today vs normal" isn't diluted by
            # today itself -- with a short history that shift is large
            # enough to hide the very change the comparison is for.
            prior = [p["value"] for p in points if p["ts"] != today]
            average = sum(prior) / len(prior) if prior else None

            out[name] = {
                "label": label,
                "unit": unit,
                "decimals": decimals,
                "higher_is_better": higher_better,
                "current": current,
                "average": round(average, 2) if average is not None else None,
                "min": min(values),
                "max": max(values),
                "points": points,
            }

        return {
            "available": any_data,
            "day": today,
            "days": days,
            "metrics": out,
            "checkin": checkin.answered(today),
            "garmin": garmin_client.status(),
        }

    @router.get("/health/readiness")
    async def get_readiness(day: Optional[str] = None):
        """Today's composite, with the components that produced it.

        Always returns the breakdown, never a bare number: a score built
        from two of three signals is a different claim from one built on
        all three, and the caller has to be able to tell."""
        result = readiness.score(day)
        if result is None:
            return {"available": False, "score": None, "load_gap": readiness.load_gap()}
        return {"available": True, **result, "load_gap": readiness.load_gap()}

    @router.post("/health/readiness/recompute")
    async def recompute_readiness(days: int = Query(365, ge=1, le=1000)):
        """Rebuild the stored score series. Pure arithmetic over metrics
        already held -- no API calls -- so it's safe to re-run after
        retuning the weights, which is the point: a retune should change
        history too, not just tomorrow."""
        return {"days_stored": readiness.recompute_history(days=days)}

    @router.get("/health/workouts")
    async def get_workout_windows(days_ahead: int = Query(2, ge=1, le=7)):
        """Free calendar windows ranked by readiness."""
        return workouts.find_windows(days_ahead=days_ahead)

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
            start = datetime.fromisoformat(body.start).date() if body.start else None
            end = datetime.fromisoformat(body.end).date() if body.end else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Bad date: {e}")
        return garmin_client.backfill(start, end)

    @router.post("/health/ingest/run")
    async def run_daily_ingest():
        """Run the whole daily capture now (pressure + Garmin)."""
        return daily_ingest.run()

    return router
