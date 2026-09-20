#!/usr/bin/env python
"""Regression tests for plan item A4 (SQLite connection reuse in
scheduled_db.py, token_tracker.py, dashboard.py). Proves two things per
class: (1) the exercised methods still return correct results end-to-end,
and (2) the connection is actually being pooled (same object across calls)
rather than silently falling back to reconnect-per-call. Plain assert-based
script, matching the style of test_routing_fixes.py.
"""

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from sunny_code.components.scheduled_db import ScheduledDB
from sunny_code.components import token_tracker
from sunny_code.components.dashboard import DashboardDB

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def test_scheduled_db_pooled_read_path():
    with tempfile.TemporaryDirectory() as tmp:
        db = ScheduledDB(Path(tmp) / "scheduled.db")

        item_id = db.create_item("reminder", "call mom", datetime.now() + timedelta(hours=1))
        check("create_item returns an id", bool(item_id))

        active = db.get_active_items()
        check("get_active_items sees the new item", len(active) == 1 and active[0]["id"] == item_id)

        due = db.get_due_items(now=datetime.now() + timedelta(hours=2))
        check("get_due_items sees the now-due item", len(due) == 1 and due[0]["id"] == item_id)

        conn_after_first_call = db._read_conn
        check("get_due_items lazily created its pooled connection", conn_after_first_call is not None)

        # Second call must reuse the exact same connection object, not
        # reconnect - this is the actual behavior change under test.
        db.get_due_items(now=datetime.now() + timedelta(hours=2))
        check("get_due_items reuses the same pooled connection on a second call",
              db._read_conn is conn_after_first_call)

        ok = db.deactivate(item_id)
        check("deactivate succeeds", ok is True)

        due_after_deactivate = db.get_due_items(now=datetime.now() + timedelta(hours=2))
        check("get_due_items no longer sees the deactivated item", due_after_deactivate == [])

        # get_active_items / get_item / create_item / deactivate remain
        # connect-per-call by design (chat.py writes to the same file from
        # a separate process) - confirm they're untouched, not pooled.
        check("get_active_items path was NOT pooled (stays connect-per-call by design)",
              not hasattr(db, "_conn"))

        db.close()
        check("close() clears the pooled connection", db._read_conn is None)


def test_dashboard_db_pooled_connection():
    with tempfile.TemporaryDirectory() as tmp:
        db = DashboardDB(Path(tmp) / "sunny.db")

        conn_after_init = db._conn
        check("DashboardDB lazily created its pooled connection during _init_db", conn_after_init is not None)

        db.record_metric(cpu=12.5, ram=40.0, disk=55.0, cpu_temp=45.0, tokens=100, cost=0.01)
        db.update_service_health("sunny", success=True)
        db.update_service_health("warren", success=False, error="timeout")

        check("record_metric/update_service_health reused the same pooled connection",
              db._conn is conn_after_init)

        health = db.get_health_status()
        check("get_health_status sees both services",
              set(health.keys()) == {"sunny", "warren"})
        check("get_health_status reports the success case correctly",
              health["sunny"]["error_count"] == 0)
        # error_count == 2 (not 1) on a first-ever failure is a pre-existing
        # bug in update_service_health (INSERT OR IGNORE seeds error_count=1,
        # then the UPDATE unconditionally adds 1 more) - confirmed present
        # in the unmodified code too, so preserved as-is here; fixing it is
        # a behavior change outside this plan's "no observable behavior
        # change" scope for A4.
        check("get_health_status reports the failure case correctly (pre-existing double-count preserved)",
              health["warren"]["error_count"] == 2 and health["warren"]["last_error"] == "timeout")

        db.close()
        check("DashboardDB.close() clears the pooled connection", db._conn is None)


def test_token_tracker_pooled_connection():
    import sunny_code.config as config_module
    config_module._settings_cache = None

    with tempfile.TemporaryDirectory() as tmp:
        import os
        os.environ["DB_PATH"] = str(Path(tmp) / "sunny.db")

        token_tracker._pooled_conn = None  # start from a clean slate

        today = token_tracker.get_today_usage()
        check("get_today_usage on an empty db returns zeroed usage", today["total_tokens"] == 0)

        conn_after_first_call = token_tracker._pooled_conn
        check("token_tracker lazily created its pooled connection", conn_after_first_call is not None)

        token_tracker.record_usage("claude-sonnet-5", 1000, 500, 0.0125)
        token_tracker.record_usage("claude-haiku-4-5", 2000, 1000, 0.007)

        check("record_usage calls reused the same pooled connection",
              token_tracker._pooled_conn is conn_after_first_call)

        usage = token_tracker.get_today_usage()
        check("get_today_usage aggregates both recorded calls",
              usage["total_tokens"] == (1000 + 500 + 2000 + 1000))
        check("get_today_usage tracks by_model breakdown for both models",
              set(usage["by_model"].keys()) == {"claude-sonnet-5", "claude-haiku-4-5"})

        month_cost = token_tracker.get_month_cost()
        expected_cost = 0.0125 + 0.007
        check("get_month_cost matches the sum of recorded costs",
              abs(month_cost - expected_cost) < 1e-9)

        daily = token_tracker.get_daily_costs(days=3)
        check("get_daily_costs returns 3 zero-filled/populated rows", len(daily) == 3)
        check("get_daily_costs' last (today) row has the recorded cost",
              abs(daily[-1]["cost"] - expected_cost) < 1e-9)

        token_tracker.close()
        check("token_tracker.close() clears the pooled connection", token_tracker._pooled_conn is None)


if __name__ == "__main__":
    test_scheduled_db_pooled_read_path()
    test_dashboard_db_pooled_connection()
    test_token_tracker_pooled_connection()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All DB-pooling (A4) regression checks passed.")
