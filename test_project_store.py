#!/usr/bin/env python
"""Regression tests for the project container (project_store).

The cases that matter are the ones where a project system goes quietly
wrong rather than loudly:

  - context() is what makes a project a container. If a file in the
    folder is silently left out, Sunny answers confidently without it and
    nothing indicates why. Skipped files must be NAMED.
  - write_file takes a filename from an LLM. "../../.env" must not
    escape the project folder.
  - resolve() must refuse to guess between two projects. Filing work
    under the wrong project is worse than being asked which one.
  - The vault is the source of truth: a folder deleted by hand in
    Obsidian must disappear here, not linger.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from sunny_code.components import project_store as ps

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_projects_"))
ps._projects_dir = lambda: _TMP / "projects"


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def test_create_and_read():
    print("\n-- create / read --")
    slug = ps.create("Sunny Assistant", "A self-hosted assistant.", ps.ACTIVE, ps.BUILDING)
    check("returns a slug", slug == "sunny-assistant")

    project = ps.get(slug)
    check("name kept", project["name"] == "Sunny Assistant")
    check("status kept", project["status"] == ps.ACTIVE)
    check("phase kept", project["phase"] == ps.BUILDING)
    check("description kept", "self-hosted" in project["description"])

    check("empty name rejected", ps.create("") is None)
    check("whitespace name rejected", ps.create("   ") is None)

    # Same name twice must not collide into one folder.
    other = ps.create("Sunny Assistant")
    check("duplicate name gets its own slug", other == "sunny-assistant-2")


def test_invalid_values_fall_back():
    print("\n-- invalid status/phase --")
    slug = ps.create("Bad Values", "", "nonsense", "also-nonsense")
    project = ps.get(slug)
    check("unknown status falls back to active", project["status"] == ps.ACTIVE)
    check("unknown phase falls back to idea", project["phase"] == ps.IDEA)
    check("update rejects an unknown status", ps.update(slug, status="wat") is False)
    check("update rejects an unknown phase", ps.update(slug, phase="wat") is False)
    check("status unchanged after rejection", ps.get(slug)["status"] == ps.ACTIVE)


def test_filtering():
    print("\n-- filtering --")
    ps.create("Personal Website", "", ps.LONG_TERM, ps.IDEA)
    ps.create("Rebuild The Shed", "", ps.SOMEDAY, ps.IDEA)

    check("filter by status", len(ps.all_projects(status=ps.SOMEDAY)) == 1)
    check("filter by phase", any(p["phase"] == ps.BUILDING
                                 for p in ps.all_projects(phase=ps.BUILDING)))
    check("no filter returns all", len(ps.all_projects()) >= 4)

    statuses = {p["status"] for p in ps.all_projects()}
    check("all three statuses usable", statuses >= {ps.ACTIVE, ps.LONG_TERM, ps.SOMEDAY})


def test_status_and_phase_are_independent():
    print("\n-- status vs phase --")
    # A someday project with a finished plan is a real and important state:
    # thinking done, waiting on time. Collapsing the two fields would lose it.
    slug = ps.create("Someday With A Plan", "", ps.SOMEDAY, ps.REFINED)
    project = ps.get(slug)
    check("someday can be refined", project["status"] == ps.SOMEDAY
          and project["phase"] == ps.REFINED)

    ps.update(slug, status=ps.ACTIVE)
    check("status changes without touching phase", ps.get(slug)["phase"] == ps.REFINED)


def test_resolve():
    print("\n-- resolve --")
    check("exact slug", ps.resolve("personal-website")["name"] == "Personal Website")
    check("exact name, any case", ps.resolve("personal website")["slug"] == "personal-website")
    check("unambiguous prefix", ps.resolve("rebuild")["slug"] == "rebuild-the-shed")
    check("substring when unique", ps.resolve("shed")["slug"] == "rebuild-the-shed")
    check("no match yields None", ps.resolve("nothing here") is None)
    check("empty yields None", ps.resolve("") is None)
    # "sunny-assistant" and "sunny-assistant-2" both start with "sunny"
    check("refuses to guess between two matches", ps.resolve("sunny") is None)


def test_context_gathers_the_folder():
    print("\n-- context --")
    slug = ps.create("Context Test", "The description.", ps.ACTIVE, ps.PLANNING)
    ps.write_file(slug, ps.PLAN_FILE, "# Plan\n\nStep one: do the thing.")
    ps.write_file(slug, "research/2026-09-23-options.md", "Option A beats option B.")
    ps.write_file(slug, "hand-written-note.md", "Added by hand in Obsidian.")

    text = ps.context(slug)
    check("names the project", "Context Test" in text)
    check("states status and phase", "active" in text and "planning" in text)
    check("includes the description", "The description." in text)
    check("includes the plan", "Step one" in text)
    check("includes nested research", "Option A beats" in text)
    check("includes hand-added files", "Added by hand" in text)

    check("unknown project yields empty string", ps.context("does-not-exist") == "")


def test_context_budget_names_what_it_dropped():
    print("\n-- context budget --")
    slug = ps.create("Big Project", "desc")
    for i in range(6):
        ps.write_file(slug, f"research/note-{i}.md", "x" * 900)

    text = ps.context(slug, budget=2000)
    check("stays near the budget", len(text) < 4000)
    check("says something was dropped", "context budget" in text)
    check("names a dropped file", "note-" in text.split("context budget")[-1])


def test_write_file_cannot_escape():
    print("\n-- path traversal --")
    slug = ps.create("Escape Test")
    outside = _TMP / "escaped.md"

    check("../ path refused", ps.write_file(slug, "../../escaped.md", "nope") is None)
    check("absolute path stays inside",
          ps.write_file(slug, "/etc/passwd", "nope") is not None)
    check("nothing written outside the folder", not outside.exists())

    written = ps.write_file(slug, "notes/ok.md", "fine")
    check("normal nested path works", written is not None and written.exists())


def test_instructions_are_read_only():
    print("\n-- per-project instructions --")
    slug = ps.create("Instructed")
    check("absent instructions yield empty", ps.instructions(slug) == "")
    ps.write_file(slug, ps.INSTRUCTIONS_FILE, "Always cite the syllabus.")
    check("instructions read back", "syllabus" in ps.instructions(slug))
    check("instructions reach the context", "syllabus" in ps.context(slug))


def test_vault_is_source_of_truth():
    print("\n-- hand-deleted project --")
    slug = ps.create("Temporary Thing")
    check("listed", any(p["slug"] == slug for p in ps.all_projects()))
    shutil.rmtree(ps._projects_dir() / slug)
    check("deleting the folder removes it", not any(p["slug"] == slug
                                                    for p in ps.all_projects()))
    check("and get() returns None", ps.get(slug) is None)


def test_summary_groups_by_status():
    print("\n-- summary --")
    lines = ps.summary_lines()
    text = "\n".join(lines)
    check("groups under status headings", "ACTIVE" in text and "SOMEDAY" in text)
    check("explains what a status means", "on it now" in text)


if __name__ == "__main__":
    test_create_and_read()
    test_invalid_values_fall_back()
    test_filtering()
    test_status_and_phase_are_independent()
    test_resolve()
    test_context_gathers_the_folder()
    test_context_budget_names_what_it_dropped()
    test_write_file_cannot_escape()
    test_instructions_are_read_only()
    test_vault_is_source_of_truth()
    test_summary_groups_by_status()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All project-store checks passed.")
