#!/usr/bin/env python
"""Regression test for plan item B4: assistant.py's _handle_message_inner
used to call category_store.get_categories() (a disk read + JSON parse)
redundantly within a single message pass. Proves the call count dropped
without changing the resulting behavior. Plain assert-based script,
matching the style of test_routing_fixes.py.
"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from sunny_code.components import category_store
from sunny_code.components.assistant import handle_message
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


async def run():
    tmp = Path(tempfile.mkdtemp())
    try:
        tasks_engine = TaskEngine(TaskDB(tmp / "tasks"))
        briefing_engine = BriefingEngine()

        real_get_categories = category_store.get_categories
        call_count = {"n": 0}

        def counting_get_categories():
            call_count["n"] += 1
            return real_get_categories()

        with patch("sunny_code.components.category_store.get_categories", counting_get_categories):
            # A command that reaches the deepest category-touching branch:
            # not a wizard reply, not a category-list/add/remove trigger,
            # a real "add" task command with an explicit category inline
            # (cmd_type == "add" and success, "tag" IS in task_data) so it
            # falls through past the "ask which category" branch into
            # tasks_engine.execute_command's known_categories= call.
            reply = await handle_message(
                'add task "buy milk" --tag School',
                tasks_engine,
                briefing_engine,
                session_id="test-b4",
            )

        check("command was handled (non-empty reply)", bool(reply))
        check(
            f"get_categories() called at most twice per message pass (was: {call_count['n']})",
            call_count["n"] <= 2,
        )

        # Confirm the task was actually created with the right category -
        # dedup must not have broken the category resolution itself.
        all_tasks = TaskDB(tmp / "tasks").get_all_tasks()
        check("task was created", len(all_tasks) == 1)
        if all_tasks:
            check("task got the correct category", all_tasks[0]["tag"] == "School")

        # Second branch: a bare "add" with no inline tag hits the
        # "ask which category" path (cmd_type == add, success, no "tag"),
        # a different call site whose category_store read was also deduped.
        call_count["n"] = 0
        with patch("sunny_code.components.category_store.get_categories", counting_get_categories):
            reply2 = await handle_message(
                'add task "call dentist"',
                tasks_engine,
                briefing_engine,
                session_id="test-b4-ask",
            )
        check("ask-which-category reply lists the real categories",
              "General" in reply2 and "School" in reply2)
        check(
            f"ask-which-category path also calls get_categories() at most once (was: {call_count['n']})",
            call_count["n"] <= 1,
        )

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run())

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All category-dedup (B4) regression checks passed.")
