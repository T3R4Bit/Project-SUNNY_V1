#!/usr/bin/env python
"""Regression tests for day_boundary, metrics_store and checkin (Stage A).

Covers the three things most likely to silently corrupt the health dataset
rather than fail loudly:

  1. The 5am day boundary -- an answer given at 2am must file against the
     previous day, or every late night lands in the wrong row and the
     sleep/pressure correlations these rows exist for are destroyed.
  2. Upsert-not-append -- Garmin re-pulls and backfills deliberately
     overlap what is already stored, so a duplicated (name, ts) would make
     every range average quietly wrong.
  3. "no" vs "not an answer" -- parse_answer must return None for an
     unrelated message, otherwise a stray reply while a check-in is
     pending records a false 0.

Plain assert-based script, matching test_settings_cache.py / test_routing_fixes.py.
Storage paths are redirected to a temp dir, so running this never touches
sunny.db or the real vault.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from sunny_code.components import checkin, day_boundary, metrics_store

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_stage_a_"))

# Redirect storage before anything touches it.
metrics_store._db_path = lambda: _TMP / "test.db"
checkin._log_path = lambda: _TMP / "checkins.md"


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


# --- day_boundary ---------------------------------------------------------

def test_day_boundary():
    print("\n-- day_boundary --")
    check(
        "2am files against the previous day",
        day_boundary.logging_day(datetime(2026, 9, 20, 2, 0)) == datetime(2026, 9, 19).date(),
    )
    check(
        "5am files against the current day",
        day_boundary.logging_day(datetime(2026, 9, 20, 5, 0)) == datetime(2026, 9, 20).date(),
    )
    check(
        "11pm files against the current day",
        day_boundary.logging_day(datetime(2026, 9, 20, 23, 0)) == datetime(2026, 9, 20).date(),
    )
    check(
        "3am is the evening period (still last night)",
        day_boundary.active_brief_period(datetime(2026, 9, 20, 3, 0)) == day_boundary.EVENING,
    )
    check(
        "18:29 is still the morning period",
        day_boundary.active_brief_period(datetime(2026, 9, 20, 18, 29)) == day_boundary.MORNING,
    )
    check(
        "18:30 switches to evening",
        day_boundary.active_brief_period(datetime(2026, 9, 20, 18, 30)) == day_boundary.EVENING,
    )
    # No instant may map to neither period, and none to both.
    periods = {
        day_boundary.active_brief_period(datetime(2026, 9, 20, h, m))
        for h in range(24) for m in (0, 29, 30, 59)
    }
    check("every instant maps to exactly one known period",
          periods == {day_boundary.MORNING, day_boundary.EVENING})


# --- metrics_store --------------------------------------------------------

def test_metrics_upsert():
    print("\n-- metrics_store --")
    metrics_store.record("test.sleep", 7.5, ts="2026-09-18")
    metrics_store.record("test.sleep", 6.0, ts="2026-09-19")
    check("stored points read back in order",
          [p["value"] for p in metrics_store.series("test.sleep")] == [7.5, 6.0])

    # Re-ingesting a revised value for a day already stored must replace it.
    metrics_store.record("test.sleep", 6.8, ts="2026-09-19")
    points = metrics_store.series("test.sleep")
    check("re-recording the same day overwrites rather than duplicating", len(points) == 2)
    check("re-recorded value is the revised one", points[-1]["value"] == 6.8)

    check("latest() returns the most recent point",
          metrics_store.latest("test.sleep") == {"ts": "2026-09-19", "value": 6.8})
    check("get_for_day() finds an exact day", metrics_store.get_for_day("test.sleep", "2026-09-18") == 7.5)
    check("get_for_day() returns None for an unrecorded day",
          metrics_store.get_for_day("test.sleep", "2026-09-01") is None)


def test_metrics_range_and_buckets():
    for day, value in [("2026-09-01", 1.0), ("2026-09-15", 2.0), ("2026-09-30", 3.0)]:
        metrics_store.record("test.range", value, ts=day)

    windowed = metrics_store.series("test.range", start="2026-09-10", end="2026-09-30")
    check("range query is inclusive of both endpoints",
          [p["value"] for p in windowed] == [2.0, 3.0])

    # A daily row's ts is a bare date, so a bare-date `end` must include it.
    same_day = metrics_store.series("test.range", start="2026-09-15", end="2026-09-15")
    check("single-day range includes that day's daily row", len(same_day) == 1)

    metrics_store.record("test.hourly", 10.0, ts="2026-09-20T08:00:00")
    metrics_store.record("test.hourly", 20.0, ts="2026-09-20T14:00:00")
    daily = metrics_store.series("test.hourly", bucket=metrics_store.BUCKET_DAY, agg=metrics_store.AGG_AVG)
    check("day bucket averages intraday samples",
          len(daily) == 1 and daily[0]["value"] == 15.0 and daily[0]["ts"] == "2026-09-20")

    summed = metrics_store.series("test.hourly", bucket=metrics_store.BUCKET_DAY, agg=metrics_store.AGG_SUM)
    check("sum aggregation works", summed[0]["value"] == 30.0)

    check("known_metrics lists what has been recorded",
          {"test.sleep", "test.range", "test.hourly"}.issubset(set(metrics_store.known_metrics())))


def test_record_many_skips_none():
    written = metrics_store.record_many(
        {"test.a": 1.0, "test.b": None, "test.c": 3.0}, ts="2026-09-20"
    )
    check("record_many skips None rather than storing 0", written == 2)
    check("a None metric is genuinely absent, not zero",
          metrics_store.get_for_day("test.b", "2026-09-20") is None)


# --- checkin --------------------------------------------------------------

def test_answer_parsing():
    print("\n-- checkin --")
    question = checkin.QUESTIONS[0]
    for reply in ("yes", "Yes", "yep", "y", "YEAH"):
        check(f"{reply!r} parses as yes", checkin.parse_answer(question, reply) == 1.0)
    for reply in ("no", "nope", "n", "Nah"):
        check(f"{reply!r} parses as no", checkin.parse_answer(question, reply) == 0.0)

    check("'no, felt fine' parses as no (leading token)",
          checkin.parse_answer(question, "no, felt fine") == 0.0)

    # The critical negative cases: an unrelated message must not record a 0.
    for reply in ("what's the weather", "add milk to my list", "I don't know", ""):
        check(f"{reply!r} is not treated as an answer",
              checkin.parse_answer(question, reply) is None)


def test_checkin_lifecycle():
    day = "2026-09-20"
    check("question is pending before it is answered",
          [q["id"] for q in checkin.pending(day)] == ["migraine"])
    check("prompt_text offers the pending question",
          checkin.prompt_text(day) == "Did you have a migraine today?")

    checkin.record_answer("migraine", 1.0, day=day)
    check("nothing pending after answering", checkin.pending(day) == [])
    check("prompt_text goes quiet once answered", checkin.prompt_text(day) is None)
    check("answer is readable back", checkin.answered(day) == {"migraine": 1.0})
    check("summary line renders the answer", checkin.summary_line(day) == "migraine: yes")

    # A correction must overwrite, not append a second conflicting row.
    checkin.record_answer("migraine", 0.0, day=day)
    check("correcting an answer overwrites it", checkin.answered(day) == {"migraine": 0.0})
    check("correction leaves exactly one stored point",
          len(metrics_store.series("health.migraine", start=day, end=day)) == 1)

    check("a different day is independently pending",
          [q["id"] for q in checkin.pending("2026-09-21")] == ["migraine"])

    body = (_TMP / "checkins.md").read_text(encoding="utf-8")
    check("vault log records the answer", "migraine: no" in body)
    check("vault log carries frontmatter", body.startswith("---"))


def test_late_night_attribution():
    """The whole point of the 5am boundary, end to end."""
    late = datetime(2026, 9, 21, 2, 30)
    day = day_boundary.day_key(late)
    checkin.record_answer("migraine", 1.0, day=day)
    check("a 2:30am answer files against the previous day",
          metrics_store.get_for_day("health.migraine", "2026-09-20") is not None
          and metrics_store.get_for_day("health.migraine", "2026-09-21") is None)


if __name__ == "__main__":
    test_day_boundary()
    test_metrics_upsert()
    test_metrics_range_and_buckets()
    test_record_many_skips_none()
    test_answer_parsing()
    test_checkin_lifecycle()
    test_late_night_attribution()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All Stage A (day_boundary / metrics_store / checkin) checks passed.")
