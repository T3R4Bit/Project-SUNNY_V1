"""Loads the tunable personality file at sunny-vault/personality.md.

Sits alongside instructions.py rather than inside it, because the two
answer different questions. instructions.py loads a prompt PER PURPOSE
(how to write a health report, how to parse a syllabus). This loads how
Sunny should sound in ALL of them. Folding personality into each
instruction file would mean editing seven files to make Sunny less chatty.

HUMAN-OWNED FILE
----------------
Sunny reads this and never writes it. That rule is not stylistic -- it is
what keeps the file out of the vault's sync-conflict class. A file that
both you (in Obsidian, on a phone, on a desktop) and a server process edit
is precisely the situation no file-sync tool can resolve cleanly, and it
is the shape of the conflicts already being hit with Syncthing. Any
personality change Sunny wants to propose belongs in a suggestions file
for you to merge deliberately, never an in-place edit here.

The same rule will apply to memory/profile.md when that lands.

DIALS
-----
Frontmatter holds integer 1-5 dials; the body is freeform guidance. The
dials exist so that "be less formal" is a one-character edit rather than a
paragraph rewrite, and so the same intent can reach a non-text consumer --
tts_delivery.py varies speech pace, and a `verbosity` or `bluntness` dial
means something there too.

Unknown dials are kept and rendered rather than rejected: inventing one in
the file and referring to it in the body is a legitimate way to steer the
model, and refusing to pass it through would make the file feel brittle to
edit.

FAILING QUIET
-------------
A malformed personality file must never break Sunny's ability to answer.
Every failure path here returns the last known-good rendering, or nothing
at all -- never an exception into an LLM call path. The worst outcome of a
bad edit is that Sunny sounds like its old self until the file parses
again.
"""

import logging
from typing import Dict, Optional, Tuple

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Dial -> (low label, high label). Rendered into the prompt as a sentence
# rather than a number, because "3/5" means nothing to a model without the
# scale being explained, and explaining it every time is wasted tokens.
_DIAL_SCALES: Dict[str, Tuple[str, str]] = {
    "verbosity": ("very terse, one or two sentences", "thorough and detailed"),
    "formality": ("casual and conversational", "formal and precise"),
    "humor": ("completely straight, no jokes", "playful, jokes welcome"),
    "bluntness": ("gentle, soften disagreement", "blunt, disagree directly and early"),
    "proactivity": (
        "answer only what was asked",
        "volunteer relevant things that weren't asked",
    ),
}

_DEFAULTS: Dict[str, int] = {name: 3 for name in _DIAL_SCALES}

# Last successfully rendered prompt, reused when a later read fails or the
# file is mid-edit (a real occurrence: Obsidian and most editors write
# through a truncate, so a read landing in that window sees an empty or
# partial file).
_last_good: Optional[str] = None


def _path():
    return get_settings().project_root / "sunny-vault" / "personality.md"


def _describe_dial(name: str, value: int) -> Optional[str]:
    """One dial as a natural-language instruction, or None when it sits at
    the neutral midpoint -- a 3 out of 5 carries no instruction, and
    spending tokens to say "be moderately humorous" makes the prompt
    longer without making it more specific."""
    scale = _DIAL_SCALES.get(name)
    if scale is None:
        return f"{name}: {value}"
    if value == 3:
        return None

    low, high = scale
    if value <= 1:
        return f"Strongly {low}."
    if value == 2:
        return f"Lean towards {low}."
    if value == 4:
        return f"Lean towards {high}."
    return f"Strongly {high}."


def load() -> Dict:
    """Parsed personality: {"dials": {...}, "body": str, "ok": bool}.

    Not cached -- matches instructions.py and get_settings()'s deliberate
    "a hand-edit takes effect on the very next call" contract. The file is
    a few hundred bytes and is read once per LLM call, which is
    considerably cheaper than the call it is shaping.
    """
    path = _path()
    if not path.exists():
        return {"dials": dict(_DEFAULTS), "body": "", "ok": False}

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"Could not read personality.md: {e}")
        return {"dials": dict(_DEFAULTS), "body": "", "ok": False}

    if not text.strip():
        # A zero-byte file is far more likely an editor mid-write than a
        # deliberate "no personality" -- Obsidian and most editors save by
        # truncating and rewriting, so a read landing in that window sees
        # exactly this. Reported as not-ok so as_prompt_section() holds the
        # last good rendering instead of silently dropping the personality
        # for whatever reply happens to be in flight. Genuinely wanting no
        # personality is expressed by deleting the file or leaving all
        # dials neutral, both of which are handled elsewhere.
        logger.debug("personality.md is empty — treating as mid-edit, keeping last good")
        return {"dials": dict(_DEFAULTS), "body": "", "ok": False}

    try:
        metadata, body = vault_io.parse_frontmatter(text)
    except Exception as e:
        # A half-written file during an editor's truncate-and-rewrite, or
        # genuinely invalid YAML. Either way: keep working.
        logger.warning(f"personality.md frontmatter unparseable, using defaults: {e}")
        return {"dials": dict(_DEFAULTS), "body": text.strip(), "ok": False}

    dials = dict(_DEFAULTS)
    for key, value in (metadata or {}).items():
        try:
            number = int(value)
        except (TypeError, ValueError):
            # Non-numeric frontmatter is metadata, not a dial (a `tags:`
            # line, an `id:`). Skipping it silently is correct -- warning
            # would fire on every read of a perfectly normal vault file.
            continue
        dials[key] = max(1, min(5, number))

    return {"dials": dials, "body": (body or "").strip(), "ok": True}


def as_prompt_section() -> str:
    """The personality as a prompt fragment, ready to prepend to a system
    prompt. Empty string when there's nothing to say, so callers can
    concatenate unconditionally without a branch.

    Returns the last good rendering if the current file is unreadable, so
    a bad edit degrades to stale behavior rather than to no personality at
    all mid-conversation.
    """
    global _last_good

    try:
        loaded = load()
    except Exception as e:
        logger.error(f"personality load failed: {e}", exc_info=True)
        return _last_good or ""

    lines = []
    for name, value in loaded["dials"].items():
        described = _describe_dial(name, value)
        if described:
            lines.append(described)

    body = loaded["body"]
    if not lines and not body:
        # Two different situations reach here. A file that parsed fine and
        # simply says nothing (all dials neutral, empty body) is a valid
        # state and genuinely means "no instruction". A file that did NOT
        # parse -- missing, unreadable, empty mid-write -- must not be
        # allowed to silently strip the personality from a reply in
        # flight, so it holds the last good rendering instead.
        if loaded["ok"]:
            _last_good = ""
            return ""
        return _last_good or ""

    section = "HOW TO SOUND\n"
    if lines:
        section += "\n".join(f"- {line}" for line in lines) + "\n"
    if body:
        section += "\n" + body + "\n"

    if loaded["ok"]:
        _last_good = section
    return section


def speech_rate_multiplier() -> float:
    """Pace hint for TTS, derived from the verbosity dial.

    A terse register and a brisk delivery are the same preference
    expressed in two media, so one dial should drive both rather than
    needing a separate speech setting that can contradict the text one.
    Composes multiplicatively with the user's own PIPER_LENGTH_SCALE
    tuning and tts_delivery.py's per-message-type multipliers, so this
    only ever nudges -- see tts_delivery.py.
    """
    verbosity = load()["dials"].get("verbosity", 3)
    # Piper's length_scale is inverse to speed: lower is faster. A terse
    # personality speaks a little quicker, a thorough one a little slower.
    return {1: 0.92, 2: 0.96, 3: 1.0, 4: 1.04, 5: 1.08}.get(verbosity, 1.0)


DEFAULT_FILE = """---
verbosity: 3
formality: 2
humor: 3
bluntness: 4
proactivity: 3
---

# Sunny's personality

Edit the dials above (1-5) and this text freely — changes take effect on
the next reply, no restart. A dial at 3 is neutral and adds no instruction.

- verbosity: 1 = one or two sentences · 5 = thorough and detailed
- formality: 1 = casual · 5 = formal and precise
- humor: 1 = completely straight · 5 = playful
- bluntness: 1 = soften disagreement · 5 = disagree directly and early
- proactivity: 1 = answer only what was asked · 5 = volunteer things

Anything written below the dials is passed to the model verbatim, so this
is the place for guidance that doesn't fit a dial.

Call me Keaton. Skip the preamble and lead with the answer. If I'm about
to do something that won't work, say so before explaining anything else.

> Sunny only ever reads this file and never writes it. That is deliberate:
> a vault file edited by both you and a server process is exactly what
> file sync cannot merge cleanly. Suggested changes go elsewhere for you
> to merge by hand.
"""


def ensure_exists() -> bool:
    """Write the default personality file if absent. True if it created
    one. Called at startup so the file is discoverable in Obsidian without
    needing to be documented -- an empty vault gives no hint that this
    feature exists.

    This is the single exception to "Sunny never writes this file", and
    only for a file that does not exist yet: it never overwrites, so it
    cannot clobber an edit or produce a sync conflict.
    """
    path = _path()
    if path.exists():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        vault_io.atomic_write_text(path, DEFAULT_FILE)
        logger.info(f"Created default personality file at {path}")
        return True
    except OSError as e:
        logger.error(f"Could not create personality.md: {e}")
        return False
