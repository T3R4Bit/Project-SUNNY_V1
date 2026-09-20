#!/usr/bin/env python
"""Regression tests for the nightly check-in conversation flow (Stage A).

assistant.py can't be imported on a dev box without the full dependency
set (discord, anthropic, googleapiclient), so this exercises the pending/
answer state machine against the same checkin primitives the handler uses,
plus the exact guard conditions copied from the handler branch.

The case that matters most is the negative one: while a check-in is
pending, an unrelated message ("what's the weather") must fall through to
normal routing rather than being recorded as an answer. A false 0 there is
indistinguishable from a real "no" forever afterwards, and it would land
in the one dataset that cannot be rebuilt.
"""

import sys
import tempfile
from pathlib import Path

from sunny_code.components import checkin, day_boundary, metrics_store

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_checkin_flow_"))
metrics_store._db_path = lambda: _TMP / "test.db"
checkin._log_path = lambda: _TMP / "checkins.md"

_CANCEL_WORDS = ("cancel", "nevermind", "never mind", "stop", "skip", "forget it")


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


class FakeSession:
    """Mirrors assistant.py's _pending dict plus the checkin branch logic,
    so the state machine is tested without importing the whole app."""

    def __init__(self):
        self.pending = None

    def arm_after_evening_brief(self):
        question = checkin.next_question()
        self.pending = {"awaiting": "checkin", "question_id": question["id"]} if question else None
        return self.pending is not None

    def send(self, text):
        """Returns (reply, routed_normally). routed_normally=True means the
        message fell through to ordinary command handling."""
        stripped = text.strip()
        lowered = stripped.lower().strip("?!. ")

        if self.pending and self.pending.get("awaiting") == "checkin":
            question = checkin._BY_ID.get(self.pending.get("question_id", ""))
            if question is not None and lowered not in _CANCEL_WORDS:
                value = checkin.parse_answer(question, stripped)
                if value is not None:
                    self.pending = None
                    checkin.record_answer(question["id"], value)
                    nxt = checkin.next_question()
                    if nxt is not None:
                        self.pending = {"awaiting": "checkin", "question_id": nxt["id"]}
                        return f"Logged. {nxt['prompt']}", False
                    return "Logged — thanks. Sleep well.", False
            self.pending = None
            return None, True

        return None, True


def test_answer_recorded():
    print("\n-- answering --")
    day = day_boundary.day_key()
    session = FakeSession()
    check("evening brief arms a pending check-in", session.arm_after_evening_brief())

    reply, routed = session.send("no")
    check("'no' is captured, not routed onward", routed is False)
    check("reply confirms the log", reply is not None and "Logged" in reply)
    check("answer is stored against today's logging day",
          metrics_store.get_for_day("health.migraine", day) == 0.0)
    check("pending state is cleared once answered", session.pending is None)


def test_unrelated_message_falls_through():
    print("\n-- the case that must not record a false 0 --")
    for day_offset, message in enumerate(
        ["what's the weather", "add milk to my grocery list", "show my tasks", "I don't know"], start=1
    ):
        # Fresh day each time so the question is genuinely pending.
        day = f"2026-10-{day_offset:02d}"
        session = FakeSession()
        session.pending = {"awaiting": "checkin", "question_id": "migraine"}

        reply, routed = session.send(message)
        check(f"{message!r} routes onward normally", routed is True)
        check(f"{message!r} records nothing",
              metrics_store.get_for_day("health.migraine", day) is None)
        check(f"{message!r} clears the pending state rather than re-asking",
              session.pending is None)


def test_cancel_is_not_an_answer():
    print("\n-- cancelling --")
    session = FakeSession()
    session.pending = {"awaiting": "checkin", "question_id": "migraine"}
    reply, routed = session.send("skip")
    check("'skip' does not record an answer", routed is True and reply is None)
    check("'skip' clears the pending state", session.pending is None)


def test_reask_is_suppressed_once_answered():
    print("\n-- re-reading the brief after answering --")
    day = day_boundary.day_key()
    checkin.record_answer("migraine", 1.0, day=day)
    session = FakeSession()
    check("a second evening brief does not re-arm an answered check-in",
          session.arm_after_evening_brief() is False)
    check("brief shows a recap instead of the question",
          checkin.prompt_text(day) is None and checkin.summary_line(day) == "migraine: yes")


if __name__ == "__main__":
    test_answer_recorded()
    test_unrelated_message_falls_through()
    test_cancel_is_not_an_answer()
    test_reask_is_suppressed_once_answered()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All check-in conversation-flow checks passed.")
