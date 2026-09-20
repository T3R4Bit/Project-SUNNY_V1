#!/usr/bin/env python
"""Regression tests for the readiness composite and workout windows.

The cases that matter are the ones where a plausible-looking score would
be wrong rather than absent:

  - A missing component must renormalize, not count as zero. Treating "no
    watch data" as "terrible sleep" produces a confidently wrong number,
    which is worse than no number.
  - Under-training must not suppress a workout suggestion. That was the
    reason load was pulled out of the composite -- averaged in, a large
    load gap cancels the high readiness it causes.
  - A disconnected calendar must not read as a free day.
"""

import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from sunny_code.components import garmin_client as gc
from sunny_code.components import metrics_store, readiness, workouts

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_readiness_"))
metrics_store._db_path = lambda: _TMP / "t.db"

DAY = "2026-09-20"


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def seed(readiness_v=None, battery=None, sleep=None, day=DAY):
    for metric, value in (
        (gc.M_TRAINING_READINESS, readiness_v),
        (gc.M_BODY_BATTERY_WAKE, battery),
        (gc.M_SLEEP_SCORE, sleep),
    ):
        if value is not None:
            metrics_store.record(metric, value, ts=day)


def test_full_score():
    print("\n-- complete score --")
    seed(readiness_v=80, battery=60, sleep=76)
    r = readiness.score(DAY)
    # 80*.45 + 60*.30 + 76*.25 = 36 + 18 + 19 = 73
    check("weights applied as documented", r["score"] == 73)
    check("marked complete", r["complete"] is True)
    check("no missing components", r["missing"] == [])
    check("components sorted by weight", r["components"][0]["label"] == "training readiness")
    check("band derived from score", r["band"] == readiness.band(73) == "good")


def test_missing_component_renormalizes():
    print("\n-- missing component --")
    day = "2026-09-18"
    # No training readiness -- the common case for most of the backfilled
    # year. Remaining weights are .30 and .25, renormalized to .545/.455.
    seed(battery=60, sleep=76, day=day)
    r = readiness.score(day)
    expected = round(60 * (0.30 / 0.55) + 76 * (0.25 / 0.55))
    check("renormalizes over present components", r["score"] == expected)
    check("does NOT treat missing as zero", r["score"] > 50)
    check("reports the missing component", gc.M_TRAINING_READINESS in r["missing"])
    check("marked incomplete", r["complete"] is False)

    weights = sum(c["weight"] for c in r["components"])
    check("effective weights sum to 1", abs(weights - 1.0) < 0.001)


def test_no_data():
    print("\n-- no data --")
    check("returns None rather than 0", readiness.score("1999-01-01") is None)
    check("summary_line goes quiet", readiness.summary_line("1999-01-01") is None)


def test_clamping():
    print("\n-- out-of-range inputs --")
    day = "2026-09-17"
    # Body Battery genuinely reported 101 in the real data.
    seed(readiness_v=120, battery=101, sleep=-5, day=day)
    r = readiness.score(day)
    check("score stays within 0-100", 0 <= r["score"] <= 100)


def test_load_gap_direction():
    print("\n-- load gap --")
    metrics_store.record(gc.M_LOAD_AEROBIC_LOW, 18, ts=DAY)
    metrics_store.record(gc.M_LOAD_AEROBIC_LOW_MIN, 137, ts=DAY)
    metrics_store.record(gc.M_LOAD_AEROBIC_HIGH, 127, ts=DAY)
    metrics_store.record(gc.M_LOAD_AEROBIC_HIGH_MIN, 249, ts=DAY)

    gap = readiness.load_gap()
    check("deficit is positive when under target", gap["worst"]["deficit_pct"] > 0)
    check("flags under_target", gap["under_target"] is True)
    check("worst band is the biggest deficit", gap["worst"]["label"] == "aerobic base")
    # 137 -> 18 is an 87% shortfall.
    check("deficit computed against target minimum", gap["worst"]["deficit_pct"] == 87)

    # The whole reason load is not in the composite: a big gap must not
    # drag the score down.
    r = readiness.score(DAY)
    check("load gap does not lower the readiness score", r["score"] == 73)


def test_intensity_never_says_skip():
    print("\n-- intensity advice --")
    check("prime day -> hard", workouts._intensity(90) == "hard session")
    check("good day -> moderate", workouts._intensity(70) == "moderate session")
    check("moderate day -> easy", workouts._intensity(55) == "easy session")
    check("low day still suggests movement", "walk" in workouts._intensity(30))
    check("unknown readiness doesn't suppress", workouts._intensity(None) == "your call")


def test_gap_detection():
    print("\n-- window detection --")
    target = date.today() + timedelta(days=1)

    def dt(h, m=0):
        return datetime.combine(target, datetime.min.time()).replace(hour=h, minute=m)

    # Class 9-11, class 13-14 -> a 2h gap at 11, and the evening.
    workouts._busy_blocks = lambda offset: [
        {"start": dt(9), "end": dt(11)},
        {"start": dt(13), "end": dt(14)},
    ] if offset == 1 else []

    gaps = workouts._gaps_for_day(1)
    lengths = sorted(g["minutes"] for g in gaps)
    check("finds the between-class gap", 120 in lengths)
    check("all windows meet the minimum",
          all(g["minutes"] >= workouts.MIN_WINDOW_MINUTES for g in gaps))
    check("no window starts before the earliest hour",
          all(g["start"].hour >= workouts.EARLIEST_HOUR for g in gaps))
    check("no window starts past the latest hour",
          all(g["start"].hour <= workouts.LATEST_START_HOUR for g in gaps))


def test_no_calendar_is_not_a_free_day():
    print("\n-- calendar unavailable --")
    workouts._busy_blocks = lambda offset: None
    result = workouts.find_windows(days_ahead=2)
    check("available is False", result["available"] is False)
    check("no windows invented", result["windows"] == [])
    check("advice says so honestly", "isn't connected" in result["advice"])


def test_diminishing_returns():
    print("\n-- ranking --")
    short = {"minutes": 45, "start": datetime(2026, 9, 21, 16)}
    long = {"minutes": 180, "start": datetime(2026, 9, 21, 16)}
    check("longer ranks higher", workouts._rank(long, 80) > workouts._rank(short, 80))
    huge = {"minutes": 480, "start": datetime(2026, 9, 21, 16)}
    check("but past 90 min it stops mattering",
          workouts._rank(huge, 80) == workouts._rank(long, 80))
    odd_hour = {"minutes": 180, "start": datetime(2026, 9, 21, 7)}
    check("afternoon beats early morning", workouts._rank(long, 80) > workouts._rank(odd_hour, 80))


def test_recompute_history():
    print("\n-- history --")
    stored = readiness.recompute_history(days=10)
    check("stores a score per day with data", stored >= 1)
    check("score series is chartable",
          len(metrics_store.series(readiness.M_SCORE)) == stored)


if __name__ == "__main__":
    test_full_score()
    test_missing_component_renormalizes()
    test_no_data()
    test_clamping()
    test_load_gap_direction()
    test_intensity_never_says_skip()
    test_gap_detection()
    test_no_calendar_is_not_a_free_day()
    test_diminishing_returns()
    test_recompute_history()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All readiness / workout-window checks passed.")
