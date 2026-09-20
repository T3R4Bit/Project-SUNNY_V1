#!/usr/bin/env python
"""Regression tests for the tunable personality file (Stage B, item 16).

The cases that matter are the failure ones. This file is hand-edited in
Obsidian, on a phone, mid-conversation -- so it will be read while
half-written, with invalid YAML, with a dial someone typed as "high"
instead of 4. None of that may break an LLM call, because the call path
this feeds is every reply Sunny gives.

Plain assert-based script, matching test_settings_cache.py. Uses a temp
vault path so it never touches the real personality.md.
"""

import sys
import tempfile
from pathlib import Path

from sunny_code.components import personality

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_personality_"))
_FILE = _TMP / "personality.md"
personality._path = lambda: _FILE


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def write(text):
    _FILE.write_text(text, encoding="utf-8")
    personality._last_good = None


def test_missing_file():
    print("\n-- no file yet --")
    if _FILE.exists():
        _FILE.unlink()
    personality._last_good = None
    check("missing file yields no prompt section", personality.as_prompt_section() == "")
    check("missing file still reports default dials", personality.load()["dials"]["verbosity"] == 3)


def test_ensure_exists():
    print("\n-- ensure_exists --")
    if _FILE.exists():
        _FILE.unlink()
    check("creates the file when absent", personality.ensure_exists() is True)
    check("file is on disk", _FILE.exists())
    check("does not overwrite an existing file", personality.ensure_exists() is False)

    body = _FILE.read_text(encoding="utf-8")
    check("default file parses back cleanly", personality.load()["ok"] is True)
    check("default file documents that Sunny never writes it", "never writes" in body)


def test_dials_render():
    print("\n-- dials --")
    write("---\nverbosity: 1\nformality: 5\nhumor: 3\n---\n\nAlways call me Keaton.\n")
    section = personality.as_prompt_section()
    check("low verbosity renders a terse instruction", "very terse" in section)
    check("high formality renders a formal instruction", "formal and precise" in section)
    check("neutral dial (3) renders nothing", "playful" not in section and "no jokes" not in section)
    check("freeform body is passed through verbatim", "Always call me Keaton." in section)
    check("section is labelled for the model", section.startswith("HOW TO SOUND"))


def test_dials_clamped():
    print("\n-- out-of-range dials --")
    write("---\nverbosity: 99\nhumor: -4\n---\n")
    dials = personality.load()["dials"]
    check("dial above range clamps to 5", dials["verbosity"] == 5)
    check("dial below range clamps to 1", dials["humor"] == 1)


def test_non_numeric_frontmatter_ignored():
    print("\n-- non-dial frontmatter --")
    write("---\nid: personality\ntags: [voice, tone]\nbluntness: 5\n---\n\nBody text.\n")
    loaded = personality.load()
    check("ordinary vault frontmatter doesn't become a dial", "id" not in loaded["dials"])
    check("a real dial alongside it still applies", loaded["dials"]["bluntness"] == 5)
    check("parse still reports ok", loaded["ok"] is True)


def test_unknown_dial_passed_through():
    print("\n-- unknown dial --")
    write("---\nsnark: 5\n---\n")
    section = personality.as_prompt_section()
    check("an invented numeric dial is rendered rather than dropped", "snark: 5" in section)


def test_malformed_file_falls_back():
    print("\n-- malformed / mid-edit --")
    write("---\nverbosity: 1\n---\n\nTerse please.\n")
    good = personality.as_prompt_section()
    check("baseline good render", "very terse" in good)

    # Simulate an editor's truncate-and-rewrite window: file exists, is
    # empty. Must not raise, and must not lose the personality mid-turn.
    _FILE.write_text("", encoding="utf-8")
    during_edit = personality.as_prompt_section()
    check("empty file during an edit does not raise", isinstance(during_edit, str))
    check("empty file falls back to the last good render", during_edit == good)

    # Invalid YAML frontmatter.
    _FILE.write_text("---\nverbosity: [unclosed\n---\nBody\n", encoding="utf-8")
    broken = personality.as_prompt_section()
    check("invalid YAML does not raise", isinstance(broken, str))


def test_empty_but_valid_is_not_an_error():
    print("\n-- valid but says nothing --")
    write("---\nverbosity: 3\nformality: 3\nhumor: 3\nbluntness: 3\nproactivity: 3\n---\n")
    check("all-neutral file with no body yields no instruction",
          personality.as_prompt_section() == "")


def test_speech_rate():
    print("\n-- speech rate --")
    write("---\nverbosity: 1\n---\n")
    terse = personality.speech_rate_multiplier()
    write("---\nverbosity: 5\n---\n")
    thorough = personality.speech_rate_multiplier()
    write("---\nverbosity: 3\n---\n")
    neutral = personality.speech_rate_multiplier()
    check("neutral verbosity leaves pace unchanged", neutral == 1.0)
    check("terse speaks faster than neutral (lower length_scale)", terse < neutral)
    check("thorough speaks slower than neutral", thorough > neutral)


def test_prompt_composition():
    """_with_personality's contract, without importing llm_client (which
    needs the anthropic SDK)."""
    print("\n-- composition with a per-purpose prompt --")
    write("---\nbluntness: 5\n---\n")
    section = personality.as_prompt_section()
    composed = section + "\n" + "You are writing a weekly health report."
    check("personality precedes the per-purpose prompt",
          composed.index("HOW TO SOUND") < composed.index("weekly health report"))
    check("per-purpose prompt survives intact", "weekly health report" in composed)


if __name__ == "__main__":
    test_missing_file()
    test_ensure_exists()
    test_dials_render()
    test_dials_clamped()
    test_non_numeric_frontmatter_ignored()
    test_unknown_dial_passed_through()
    test_malformed_file_falls_back()
    test_empty_but_valid_is_not_an_error()
    test_speech_rate()
    test_prompt_composition()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All personality-file checks passed.")
