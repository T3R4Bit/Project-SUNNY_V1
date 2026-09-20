#!/usr/bin/env python
"""Regression test for the cross-thread SQLite bug (live 2026-09-20).

The connection pooling added to token_tracker and DashboardDB reasoned
correctly about cross-PROCESS safety and missed cross-THREAD safety. A
sqlite3 connection may only be used from the thread that created it, and
both modules are reached from at least three threads:

  - the FastAPI event loop (/api/dashboard/spend/today, /spend/month)
  - asyncio.to_thread worker threads
  - discord.ext.tasks loops (usage_refresh_loop)

The result was "sqlite3.ProgrammingError: SQLite objects created in a
thread can only be used in that same thread" on every call from any
thread but the first, which took out the Discord usage dashboard and the
website's spend panel simultaneously.

This is exactly the class of bug unit tests miss, because single-threaded
tests pass perfectly. Every check here therefore runs the call from a
DIFFERENT thread than the one that opened the connection.
"""

import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sunny_code.config as config_module
from sunny_code.components import token_tracker
from sunny_code.components.dashboard import DashboardDB

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_threads_"))


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def _point_settings_at_tmp():
    """Redirect db_path without touching the real sunny.db."""
    settings = config_module.get_settings()
    object.__setattr__(settings, "db_path", _TMP / "threads.db")
    config_module._settings_cache = (settings, float("inf"))


def test_token_tracker_across_threads():
    print("\n-- token_tracker --")
    _point_settings_at_tmp()

    # Open the pooled connection on THIS thread first, reproducing the
    # original failure shape: first use wins the connection, everything
    # else used to inherit it.
    token_tracker.record_usage("claude-haiku-4-5", 100, 50, 0.001)
    check("baseline write on the creating thread", token_tracker.get_today_usage()["prompt_tokens"] == 100)

    errors = []

    def read_from_other_thread():
        try:
            return token_tracker.get_today_usage()
        except Exception as e:
            errors.append(e)
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: read_from_other_thread(), range(8)))

    check("no ProgrammingError from other threads", not errors)
    if errors:
        print(f"       first error: {type(errors[0]).__name__}: {errors[0]}")
    check("every cross-thread read returned data", all(r is not None for r in results))
    check("cross-thread reads agree with the creating thread",
          all(r and r["prompt_tokens"] == 100 for r in results))


def test_token_tracker_concurrent_writes():
    print("\n-- concurrent writes --")
    _point_settings_at_tmp()
    before = token_tracker.get_today_usage()["completion_tokens"]

    errors = []

    def write():
        try:
            token_tracker.record_usage("claude-haiku-4-5", 0, 10, 0.0001)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("no errors writing from 8 threads", not errors)
    if errors:
        print(f"       first error: {type(errors[0]).__name__}: {errors[0]}")
    after = token_tracker.get_today_usage()["completion_tokens"]
    check("all 8 writes landed (no lost updates)", after == before + 80)


def test_dashboard_db_across_threads():
    print("\n-- DashboardDB --")
    db = DashboardDB(_TMP / "dash.db")
    db.update_service_health("weather", success=True)
    check("baseline write on the creating thread", "weather" in db.get_health_status())

    errors = []

    def touch(i):
        try:
            db.update_service_health(f"svc{i}", success=True)
            return db.get_health_status()
        except Exception as e:
            errors.append(e)
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(touch, range(6)))

    check("no ProgrammingError from other threads", not errors)
    if errors:
        print(f"       first error: {type(errors[0]).__name__}: {errors[0]}")
    check("cross-thread writes all persisted",
          all(f"svc{i}" in db.get_health_status() for i in range(6)))
    check("record_metric works off-thread",
          _no_raise(lambda: ThreadPoolExecutor(max_workers=1).submit(
              db.record_metric, 1.0, 2.0, 3.0).result()))


def test_close_is_safe_from_any_thread():
    print("\n-- shutdown --")
    db = DashboardDB(_TMP / "close.db")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: db.get_health_status(), range(2)))
    # close() runs on the main thread while connections were opened on
    # pool threads — must not raise on shutdown.
    check("DashboardDB.close() from another thread doesn't raise", _no_raise(db.close))
    check("token_tracker.close() doesn't raise", _no_raise(token_tracker.close))
    check("usable again after close", _no_raise(db.get_health_status))


def _no_raise(fn) -> bool:
    try:
        fn()
        return True
    except Exception as e:
        print(f"       raised {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    test_token_tracker_across_threads()
    test_token_tracker_concurrent_writes()
    test_dashboard_db_across_threads()
    test_close_is_safe_from_any_thread()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All cross-thread SQLite checks passed.")
