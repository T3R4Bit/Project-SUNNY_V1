#!/usr/bin/env python
"""Regression tests for the 2026-08-28 hardcoded-routing audit fixes.

Exercises the parser classes directly (no DB/engine setup needed for most
cases) against the specific edge-case phrasings the audit found broken.
Plain assert-based script, matching the style of test_tasks_complete.py.
"""

import asyncio
import sys

from sunny_code.components.tasks_parser import TaskCommandParser
from sunny_code.components.lists_parser import ListCommandParser
from sunny_code.components.scheduled_parser import ScheduledCommandParser
from sunny_code.components.spotify_engine import SpotifyEngine

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def test_tasks_parser():
    print("\n--- tasks_parser.py ---")

    # Unrecognized category word: title extracted correctly, no tag (asks
    # instead of swallowing the whole phrase as the title).
    cmd_type, success, data = TaskCommandParser.parse_command(
        "add buy milk to my homework tasks", known_categories=["School", "General"]
    )
    check(
        "unrecognized category word -> correct title, no tag",
        cmd_type == "add" and success and data.get("title") == "buy milk" and "tag" not in data,
    )

    # Recognized category word still resolves inline as before.
    cmd_type, success, data = TaskCommandParser.parse_command(
        "add buy milk to my school tasks", known_categories=["School", "General"]
    )
    check(
        "recognized category word -> tag set inline",
        cmd_type == "add" and success and data.get("title") == "buy milk" and data.get("tag") == "School",
    )

    # Legacy add without quotes -> real format error, not swallowed as "missing title".
    cmd_type, success, data = TaskCommandParser.parse_command('!task add buy milk --tag School')
    check(
        "legacy add without quotes -> real format error",
        cmd_type == "add" and not success and "Invalid add command format" in data.get("error", ""),
    )

    # !task <id> <field> with no value -> real "missing a value" error, not silently "list".
    cmd_type, success, data = TaskCommandParser.parse_command("!task abc123 status")
    check(
        "incomplete update -> real error, not list",
        cmd_type == "update" and not success and "Missing a value" in data.get("error", ""),
    )

    # Multi-word tag no longer truncated at the first space.
    cmd_type, success, data = TaskCommandParser.parse_command(
        "add buy milk to my tasks --tag School Stuff"
    )
    check(
        "multi-word --tag not truncated",
        cmd_type == "add" and success and data.get("tag") == "School Stuff",
    )


def test_lists_parser():
    print("\n--- lists_parser.py ---")

    # Bare "and", no comma: stays one item (the fixed food-name collision).
    items = ListCommandParser._split_items("mac and cheese")
    check('"mac and cheese" (no comma) -> one item', items == ["mac and cheese"])

    # Comma-separated list with Oxford comma still splits correctly.
    items = ListCommandParser._split_items("milk, eggs, and bread")
    check('"milk, eggs, and bread" -> 3 items', items == ["milk", "eggs", "bread"])

    # Comma-separated list without Oxford comma still splits correctly.
    items = ListCommandParser._split_items("milk, eggs and bread")
    check('"milk, eggs and bread" (no Oxford comma) -> 3 items', items == ["milk", "eggs", "bread"])

    # NOTE: "milk, mac and cheese, bread" (an "and"-containing item name
    # combined with other list items) is NOT handled -- once any comma is
    # present the parser can't distinguish a real list's missing-Oxford-comma
    # connector from an item name that happens to contain "and". This is a
    # genuine, pure-regex-unsolvable ambiguity (out of scope per the plan --
    # same class as the calendar/task "cancel my X" ambiguity), not a
    # regression to chase further.


def test_scheduled_parser():
    print("\n--- scheduled_parser.py ---")

    parsed = ScheduledCommandParser.parse("cancel all my alarms")
    check('"cancel all my alarms" -> cancel_all_alarms', parsed is not None and parsed[0] == "cancel_all_alarms")

    parsed = ScheduledCommandParser.parse("remove my reminder to call mom")
    check(
        '"remove my reminder to call mom" -> delete_reminder',
        parsed is not None and parsed[0] == "delete_reminder" and parsed[1]["label_text"] == "call mom",
    )

    parsed = ScheduledCommandParser.parse("cancel my reminder to call mom")
    check(
        '"cancel my reminder to call mom" -> delete_reminder',
        parsed is not None and parsed[0] == "delete_reminder",
    )

    parsed = ScheduledCommandParser.parse("set an alarm for 7am every other week")
    check(
        '"every other week" -> unparsed recurrence flagged, not silently one-time',
        parsed is not None and parsed[0] == "create_alarm"
        and parsed[1]["recurrence"] is None and parsed[1]["recurrence_unparsed"] == "other week",
    )

    parsed = ScheduledCommandParser.parse("set an alarm for 7am every monday")
    check(
        '"every monday" -> recurrence resolved, no unparsed flag',
        parsed is not None and parsed[0] == "create_alarm"
        and parsed[1]["recurrence"] is not None and parsed[1]["recurrence_unparsed"] is None,
    )


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_spotify_search():
    print("\n--- spotify_engine.py ---")

    async def run():
        engine = SpotifyEngine.__new__(SpotifyEngine)  # bypass __init__, no real client needed
        calls = []

        async def fake_request(method, path, params=None, json=None):
            calls.append(params["q"])
            if params["q"] == "stand by me":
                return _FakeResp(200, {"tracks": {"items": [
                    {"uri": "spotify:track:1", "name": "Stand By Me", "artists": [{"name": "Ben E. King"}]}
                ]}})
            return _FakeResp(200, {"tracks": {"items": []}})

        engine._request = fake_request

        uri, label = await engine._search_track("stand by me")
        check(
            '"stand by me" found on full-query search (no split needed)',
            uri == "spotify:track:1" and calls == ["stand by me"],
        )

        calls.clear()

        async def fake_request_fallback(method, path, params=None, json=None):
            calls.append(params["q"])
            if params["q"] == "some obscure title artist:some artist":
                return _FakeResp(200, {"tracks": {"items": [
                    {"uri": "spotify:track:2", "name": "Some Obscure Title", "artists": [{"name": "Some Artist"}]}
                ]}})
            return _FakeResp(200, {"tracks": {"items": []}})

        engine._request = fake_request_fallback
        uri, label = await engine._search_track("some obscure title by some artist")
        check(
            "full-query miss falls back to title/artist split",
            uri == "spotify:track:2" and calls == ["some obscure title by some artist", "some obscure title artist:some artist"],
        )

    asyncio.run(run())


if __name__ == "__main__":
    test_tasks_parser()
    test_lists_parser()
    test_scheduled_parser()
    test_spotify_search()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All routing-fix regression checks passed.")
