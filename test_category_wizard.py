#!/usr/bin/env python
"""Regression tests for the two category-prompt bugs (item 3).

assistant.py can't be imported without the full dependency set, so this
reimplements the two decision points verbatim and tests those. Both are
pure functions of (reply, category list), which is the whole of the logic.

BUG 1 — phantom categories. _finish_task_with_category used to accept any
string, so answering "shcool" filed the task under "shcool". That became
its own heading in the dashboard grouping forever, and the task was
invisible in the School list where it was expected.

BUG 2 — swallowed answers. The pending handler ran _looks_like_a_command()
before checking whether the reply was simply a category name. A category
named "Help", "Info" or "Lists" would be classified as an unrelated
command, the pending task silently dropped, and the half-created task lost.
"""

import sys

FAILURES = []

CATEGORIES = ["General", "School", "Motorsports"]
_HELP_TRIGGERS = ("", "help", "/help", "commands", "info", "what can you do", "what can i ask")


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def resolve_category(reply, categories):
    """_finish_task_with_category's matching, verbatim.
    Returns (matched_category, outcome) where outcome is one of
    "created" / "reask" / "ambiguous"."""
    category = reply.strip().strip('"\'')
    if not category:
        return None, "reask"

    matched = next((c for c in categories if c.lower() == category.lower()), None)
    if matched is None:
        prefix_hits = [c for c in categories if c.lower().startswith(category.lower())]
        if len(prefix_hits) == 1:
            matched = prefix_hits[0]
        elif len(prefix_hits) > 1:
            return None, "ambiguous"

    if matched is None:
        return None, "reask"
    return matched, "created"


def routes_to_category_answer(reply, categories, looks_like_command):
    """The pending-handler precedence, verbatim: an exact category name
    wins before the command guard is consulted."""
    answer = reply.strip().strip('"\'').lower()
    if any(c.lower() == answer for c in categories):
        return True
    return not looks_like_command


def test_exact_and_case():
    print("\n-- exact matches --")
    for reply, expected in [("School", "School"), ("school", "School"), ("SCHOOL", "School"),
                            ('"School"', "School"), ("  School  ", "School")]:
        matched, outcome = resolve_category(reply, CATEGORIES)
        check(f"{reply!r} resolves to {expected}", matched == expected and outcome == "created")


def test_typos_no_longer_create_phantom_categories():
    print("\n-- BUG 1: typos --")
    for typo in ["shcool", "skool", "motorsprots", "genral"]:
        matched, outcome = resolve_category(typo, CATEGORIES)
        check(f"{typo!r} does not become a category", matched is None)
        check(f"{typo!r} re-asks instead of filing", outcome == "reask")


def test_prefix_matching():
    print("\n-- prefix shorthand --")
    matched, outcome = resolve_category("mot", CATEGORIES)
    check("'mot' resolves to Motorsports", matched == "Motorsports" and outcome == "created")
    matched, outcome = resolve_category("sch", CATEGORIES)
    check("'sch' resolves to School", matched == "School")

    # Ambiguous prefix must ask rather than guess.
    cats = ["School", "Scholarships", "General"]
    matched, outcome = resolve_category("sch", cats)
    check("ambiguous prefix does not guess", matched is None)
    check("ambiguous prefix asks which one", outcome == "ambiguous")


def test_empty_reply_reasks():
    print("\n-- empty reply --")
    matched, outcome = resolve_category("   ", CATEGORIES)
    check("blank answer re-asks", matched is None and outcome == "reask")


def test_colliding_category_names_are_answerable():
    print("\n-- BUG 2: names that collide with other commands --")
    # A category the user genuinely added whose name is also a help trigger.
    cats = CATEGORIES + ["Help", "Info", "Lists"]
    for name in ["Help", "Info", "Lists"]:
        looks_like_command = name.lower() in _HELP_TRIGGERS or name.lower() == "lists"
        check(f"{name!r} would have been swallowed by the old guard", looks_like_command)
        check(f"{name!r} is now accepted as a category answer",
              routes_to_category_answer(name, cats, looks_like_command) is True)
        matched, outcome = resolve_category(name, cats)
        check(f"{name!r} resolves to itself", matched == name and outcome == "created")


def test_unrelated_message_still_routes_away():
    print("\n-- unrelated messages must still escape the wizard --")
    for message in ["show my tasks", "what's the weather", "help"]:
        # "help" is only a category here if the user made one; with the
        # default list it must still route to help.
        routed_as_answer = routes_to_category_answer(message, CATEGORIES, looks_like_command=True)
        check(f"{message!r} still routes onward, not into the wizard", routed_as_answer is False)


if __name__ == "__main__":
    test_exact_and_case()
    test_typos_no_longer_create_phantom_categories()
    test_prefix_matching()
    test_empty_reply_reasks()
    test_colliding_category_names_are_answerable()
    test_unrelated_message_still_routes_away()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All category-wizard checks passed.")
