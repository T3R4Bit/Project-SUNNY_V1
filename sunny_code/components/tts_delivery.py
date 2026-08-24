"""TTS delivery/prosody layer -- personal-assistant-vision.md section 14:
"a separate layer should determine HOW something gets spoken." Deterministic
only, per that section's own preference to reserve an LLM call for nuanced
delivery decisions, not the common cases. This pass covers the common
cases; there is no LLM-driven delivery path built.

Piper's SynthesisConfig doesn't expose a "tone" knob -- length_scale
(speech rate) is the one lever here that reliably maps to the vision doc's
examples (reminder=calm, warning=deliberate/slower, casual=relaxed)
without guessing at settings that would need actual listening to tune
(noise_scale/noise_w_scale affect voice expressiveness/variability, not
pace, and aren't touched here). Multipliers apply ON TOP OF the user's own
.env-configured base length_scale (tts.py's PIPER_LENGTH_SCALE), not
instead of it, so a user's own tuning still composes with this.

No real caller yet: tts.py's two synthesis functions accept an optional
message_type parameter (default None, meaning "no change" -- every
existing caller keeps working identically), and voice_worker.py's
speak()/speak_chunk() pass one through if given, but nothing upstream
classifies a reply's type today. Wiring a real classification in is
future work, once there's an actual reminder/warning-style voice
announcement to test it against.
"""

from typing import Optional

# Multiplier on the configured base length_scale. >1.0 = slower/more
# deliberate, <1.0 = faster, 1.0 = unchanged (the default for any
# unrecognized or unset message_type).
_PACE_MULTIPLIERS = {
    "warning": 1.15,
    "reminder": 1.05,
    "briefing": 1.0,
    "casual": 1.0,
}


def pace_multiplier(message_type: Optional[str]) -> float:
    if message_type is None:
        return 1.0
    return _PACE_MULTIPLIERS.get(message_type, 1.0)
