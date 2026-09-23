#!/usr/bin/env python
"""Regression tests for structured capture (Stage B).

The cases here are the ones where extraction would be quietly wrong
rather than absent -- a capture tool that fails loudly costs one retry,
one that files the right task under the wrong date costs a deadline.

  - An off-enum category must never reach the task store. That bug
    (a typo creating a phantom category) is the reason the schema
    constrains the field at all, so it is tested on the assumption the
    constraint might fail.
  - A syntactically valid but impossible date -- "2026-02-31" -- passes
    the schema and would crash a calendar call. It must be dropped.
  - kind "none" must return None, or "thanks!" becomes a task.
  - Relative dates resolve against the LOGGING day, not the wall clock,
    or "tomorrow" means different things before and after midnight.

Nothing here calls the API. capture() is exercised with a stubbed
ask_claude_json so the parsing contract is tested deterministically and
for free; the live check is test_extract_live.py.
"""

import asyncio
import sys
from datetime import date

from sunny_code.components import extract, llm_client

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def stub_response(payload):
    """Replace the LLM call with a fixed payload."""
    async def _stub(*args, **kwargs):
        return dict(payload)
    extract.llm_client.ask_claude_json = _stub


def base_payload(**overrides):
    payload = {
        "kind": "assignment",
        "title": "Quiz 3",
        "due_date": "2026-09-25",
        "due_time": None,
        "category": "School",
        "category_confidence": 0.95,
        "class_name": "Physics",
        "notes": None,
        "confidence": 0.95,
    }
    payload.update(overrides)
    return payload


def test_schema_constrains_category():
    print("\n-- schema --")
    schema = extract._schema(["General", "School", "Motorsports"])
    category = schema["properties"]["category"]
    check("category is an enum", category.get("enum") == ["General", "School", "Motorsports"])
    check("additionalProperties is closed", schema["additionalProperties"] is False)
    check("every property is required",
          set(schema["required"]) == set(schema["properties"]))
    check("kind can be none", "none" in schema["properties"]["kind"]["enum"])

    # A category added since startup must be selectable.
    later = extract._schema(["General", "KSU"])
    check("enum reflects the list at call time",
          later["properties"]["category"]["enum"] == ["General", "KSU"])


def test_reference_block_weekdays():
    print("\n-- date reference --")
    # 2026-09-22 is a Tuesday.
    block = extract._reference_block(date(2026, 9, 22))
    check("names the reference day", "2026-09-22 (Tuesday)" in block)
    check("maps the coming Friday", "Friday = 2026-09-25" in block)
    check("maps a full week ahead", "2026-09-29" in block)
    check("does not offer past days", "2026-09-21" not in block)


def test_date_validation():
    print("\n-- date/time validation --")
    check("valid date kept", extract._valid_date("2026-09-25") == "2026-09-25")
    check("impossible date dropped", extract._valid_date("2026-02-31") is None)
    check("garbage dropped", extract._valid_date("friday") is None)
    check("null stays null", extract._valid_date(None) is None)
    check("valid time kept", extract._valid_time("23:59") == "23:59")
    check("impossible time dropped", extract._valid_time("25:00") is None)
    check("null time stays null", extract._valid_time(None) is None)


def test_capture_happy_path():
    print("\n-- capture --")
    stub_response(base_payload())
    result = asyncio.run(extract.capture("quiz 3 in physics due friday"))
    check("returns a result", result is not None)
    check("title kept", result["title"] == "Quiz 3")
    check("date kept", result["due_date"] == "2026-09-25")
    check("auto-files when confident", result["auto_file"] is True)
    check("nothing uncertain", result["uncertain"] == [])


def test_capture_rejects_non_items():
    print("\n-- not an item --")
    stub_response(base_payload(kind="none", title="", confidence=0.1))
    check("kind none yields None", asyncio.run(extract.capture("thanks!")) is None)
    check("empty text yields None", asyncio.run(extract.capture("")) is None)
    check("whitespace yields None", asyncio.run(extract.capture("   ")) is None)


def test_capture_survives_llm_failure():
    print("\n-- llm unavailable --")
    async def _none(*args, **kwargs):
        return None
    extract.llm_client.ask_claude_json = _none
    check("None from the LLM path yields None",
          asyncio.run(extract.capture("quiz friday")) is None)


def test_off_enum_category_is_caught():
    print("\n-- phantom category --")
    # The enum should prevent this. Tested anyway: this is the exact bug
    # the constraint exists to kill.
    stub_response(base_payload(category="Scool"))
    result = asyncio.run(extract.capture("quiz 3 friday"))
    check("off-enum category does not survive", result["category"] != "Scool")
    check("falls back to a real category",
          result["category"] in extract.category_store.get_categories())
    check("confidence zeroed so the caller asks", result["category_confidence"] == 0.0)
    check("flagged uncertain", "category" in result["uncertain"])
    check("and therefore not auto-filed", result["auto_file"] is False)


def test_low_confidence_asks():
    print("\n-- confidence routing --")
    stub_response(base_payload(category_confidence=0.4))
    result = asyncio.run(extract.capture("do the thing friday"))
    check("low category confidence flagged", result["uncertain"] == ["category"])
    check("not auto-filed", result["auto_file"] is False)

    stub_response(base_payload(confidence=0.3))
    result = asyncio.run(extract.capture("something vague"))
    check("low overall confidence flagged", "reading" in result["uncertain"])

    stub_response(base_payload(confidence=0.86, category_confidence=0.86))
    result = asyncio.run(extract.capture("clear enough"))
    check("just above threshold auto-files", result["auto_file"] is True)


def test_bad_date_from_model_is_dropped():
    print("\n-- model returns a bad date --")
    stub_response(base_payload(due_date="2026-02-31", due_time="99:99"))
    result = asyncio.run(extract.capture("quiz on the 31st of february"))
    check("impossible date dropped, item kept", result is not None and result["due_date"] is None)
    check("impossible time dropped", result["due_time"] is None)


def test_describe():
    print("\n-- describe --")
    line = extract.describe(base_payload())
    check("includes the title", "Quiz 3" in line)
    check("includes a readable date", "Sep 25" in line)
    check("includes the category", "#School" in line)
    check("includes the class", "Physics" in line)

    undated = extract.describe(base_payload(due_date=None, class_name=None))
    check("no date section when undated", "due" not in undated)
    check("still names the category", "#School" in undated)

    timed = extract.describe(base_payload(due_time="23:59"))
    check("time shown when set", "23:59" in timed)


if __name__ == "__main__":
    _real = llm_client.ask_claude_json
    try:
        test_schema_constrains_category()
        test_reference_block_weekdays()
        test_date_validation()
        test_capture_happy_path()
        test_capture_rejects_non_items()
        test_capture_survives_llm_failure()
        test_off_enum_category_is_caught()
        test_low_confidence_asks()
        test_bad_date_from_model_is_dropped()
        test_describe()
    finally:
        extract.llm_client.ask_claude_json = _real

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All extraction checks passed.")
