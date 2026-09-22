#!/usr/bin/env python
"""Regression tests for long-term memory (Stage G).

The cases that matter are the ones where memory would be quietly wrong
rather than absent:

  - The vault markdown is the source of truth. A fact deleted by hand in
    Obsidian must stop being injected into prompts, or Sunny keeps
    asserting something you explicitly removed with no way to see why.
  - format_for_prompt must be EMPTY when there is nothing to say, since
    callers concatenate it unconditionally.
  - An empty profile scaffold must not be injected -- headings with
    nothing under them cost tokens and say nothing.
  - Preferences and flaws outrank plain facts on equal keyword overlap,
    because they shape how an answer is given rather than just adding a
    detail.
"""

import sys
import tempfile
from pathlib import Path

from sunny_code.components import memory_store

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_memory_"))
memory_store._memory_dir = lambda: _TMP / "memory"
memory_store._facts_dir = lambda: _TMP / "memory" / "facts"
memory_store._profile_path = lambda: _TMP / "memory" / "profile.md"
memory_store._db_path = lambda: _TMP / "mem.db"


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def test_remember_and_recall():
    print("\n-- remember / recall --")
    fid = memory_store.remember("Keaton races in KSU Motorsports and builds the suspension",
                                kind="fact", source="test")
    check("returns an id", bool(fid))
    memory_store.remember("Prefers blunt answers with the conclusion first",
                          kind="preference", source="test")
    memory_store.remember("Tends to start projects and leave them at 80 percent",
                          kind="flaw", source="test")

    check("all three stored", len(memory_store.all_facts()) == 3)
    check("filter by type works", len(memory_store.all_facts(kind="preference")) == 1)

    hits = memory_store.recall("tell me about motorsports suspension")
    check("recall finds the relevant fact", any("Motorsports" in h["text"] for h in hits))

    check("irrelevant query recalls nothing",
          memory_store.recall("photosynthesis in ferns") == [])
    check("empty query recalls nothing", memory_store.recall("") == [])


def test_preferences_outrank_plain_facts():
    print("\n-- ranking --")
    # Same single keyword overlap on "projects" for both.
    memory_store.remember("Projects live under sunny-vault/data/projects", kind="fact")
    hits = memory_store.recall("projects")
    kinds = [h["type"] for h in hits]
    check("a flaw about projects outranks a plain fact",
          kinds and kinds[0] in ("flaw", "preference"))


def test_prompt_formatting():
    print("\n-- prompt formatting --")
    text = memory_store.format_for_prompt("motorsports")
    check("includes the relevant fact", "Motorsports" in text)
    check("labelled so the model knows what it is", "RELEVANT MEMORY" in text)
    check("ends with a blank-line separator", text.endswith("\n\n"))

    check("no query and no profile yields empty string",
          memory_store.format_for_prompt("") == "")


def test_empty_profile_is_not_injected():
    print("\n-- empty profile --")
    check("scaffold created", memory_store.ensure_profile() is True)
    check("does not overwrite", memory_store.ensure_profile() is False)
    # The scaffold has headings but no content under any of them.
    check("empty scaffold contributes nothing", memory_store.profile_text() == "")
    check("format_for_prompt stays empty for an empty profile",
          "WHAT YOU KNOW" not in memory_store.format_for_prompt(""))


def test_filled_profile_is_injected():
    print("\n-- filled profile --")
    path = memory_store._profile_path()
    path.write_text(
        "---\nid: profile\n---\n\n# Profile\n\n"
        "## How I work\n\n- Late nights, early deadlines\n\n"
        "## What I'm bad at\n\n-\n",
        encoding="utf-8",
    )
    text = memory_store.profile_text()
    check("filled section is kept", "Late nights" in text)
    check("empty section is dropped", "bad at" not in text)
    check("injected into the prompt", "WHAT YOU KNOW" in memory_store.format_for_prompt(""))


def test_vault_is_source_of_truth():
    print("\n-- hand-deleted fact --")
    fid = memory_store.remember("Temporary thing that will be deleted by hand", kind="fact")
    check("indexed", any(f["id"] == fid for f in memory_store.all_facts()))

    # Simulate deleting the note in Obsidian.
    for p in memory_store._facts_dir().glob(f"*{fid[:6]}.md"):
        p.unlink()

    check("still indexed until reindex (expected)",
          any(f["id"] == fid for f in memory_store.all_facts()))
    memory_store.reindex()
    check("reindex drops the hand-deleted fact",
          not any(f["id"] == fid for f in memory_store.all_facts()))
    check("reindex keeps the others", len(memory_store.all_facts()) >= 3)


def test_forget():
    print("\n-- forget --")
    fid = memory_store.remember("Something to forget entirely", kind="fact")
    check("forget reports success", memory_store.forget(fid) is True)
    check("gone from the index", not any(f["id"] == fid for f in memory_store.all_facts()))
    check("vault file deleted too",
          not list(memory_store._facts_dir().glob(f"*{fid[:6]}.md")))


def test_rejects_junk():
    print("\n-- input hygiene --")
    check("empty text rejected", memory_store.remember("") is None)
    check("whitespace rejected", memory_store.remember("   ") is None)
    fid = memory_store.remember("Valid text", kind="nonsense-type")
    stored = next(f for f in memory_store.all_facts() if f["id"] == fid)
    check("unknown type falls back to 'fact'", stored["type"] == "fact")


if __name__ == "__main__":
    test_remember_and_recall()
    test_preferences_outrank_plain_facts()
    test_prompt_formatting()
    test_empty_profile_is_not_injected()
    test_filled_profile_is_injected()
    test_vault_is_source_of_truth()
    test_forget()
    test_rejects_junk()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All memory-store checks passed.")
