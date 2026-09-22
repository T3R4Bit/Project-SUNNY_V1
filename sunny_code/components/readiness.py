"""Sunny Readiness -- one 0-100 number for "how ready am I to train today",
plus the separate question of whether I actually need to.

WHY NOT BEVEL'S SCORE
---------------------
Bevel blends resting HR, HRV (RMSSD in sleep), respiratory rate, SpO2 and
wrist temperature. Its weights are proprietary, and it runs on Apple
Health. Garmin's own Training Readiness *already* blends sleep, HRV,
recovery time and recent load internally, so stacking Bevel's input list
on top of it would double-count the same signals under a different name.
Those inputs are still ingested and charted (see garmin_client) -- they
are context, not score components.

The weights here are deliberately visible and tunable rather than
proprietary. A score you cannot interrogate is one you cannot trust when
it disagrees with how you feel.

WHY LOAD IS NOT IN THE SCORE
----------------------------
The original plan had acute:chronic training load as 15% of the
composite. Two things killed that after looking at real data on
2026-09-20:

  1. Garmin does not expose acuteTrainingLoad on this account at all --
     the field is None. What exists is MONTHLY load per intensity band
     against Garmin's own target range.
  2. More importantly, it points the wrong way. Being under-trained
     RAISES readiness to train while LOWERING any load-adequacy figure.
     Averaging them into one number cancels exactly the signal that
     matters, and the cancellation is invisible in the output.

So they are two separate outputs. `score()` answers "can I train hard
today". `load_gap()` answers "do I need to". A high score with a large
load gap is the strongest possible case for a workout; a low score with a
large gap means schedule something easy, not nothing.

MISSING COMPONENTS
------------------
Weights are renormalized over whatever components exist for a given day
rather than treating a missing one as zero -- a zero would read as
"terrible sleep" instead of "no watch data". Every result reports which
components it actually used, because a score built from two of three
inputs is not the same claim as one built from all three, and the chart
would otherwise show a step change where history begins with no
explanation.
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from sunny_code.components import garmin_client, metrics_store
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

M_SCORE = "sunny.readiness"

# Component weights, renormalized when a component is missing. Tunable --
# these are a considered starting point, not a calibrated model.
#
# Training Readiness carries the most because Garmin computes it from
# sleep, HRV, recovery time and recent load together, using signals this
# code never sees directly. Body Battery is next because it is the
# wake-time energy reserve. Sleep score is last of the three not because
# sleep matters least but because Training Readiness already accounts for
# it -- weighting it heavily here would count a bad night twice.
DEFAULT_WEIGHTS: Dict[str, float] = {
    garmin_client.M_TRAINING_READINESS: 0.45,
    garmin_client.M_BODY_BATTERY_WAKE: 0.30,
    garmin_client.M_SLEEP_SCORE: 0.25,
}

# All three are already 0-100 on Garmin's side, so no rescaling is needed.
# Recorded explicitly so a future component on a different scale can't be
# added without someone noticing it needs normalizing first.
_NATIVE_0_100 = set(DEFAULT_WEIGHTS)

_LABELS = {
    garmin_client.M_TRAINING_READINESS: "training readiness",
    garmin_client.M_BODY_BATTERY_WAKE: "body battery",
    garmin_client.M_SLEEP_SCORE: "sleep score",
}

# Bands for wording. Cutoffs are judgement, not science -- they exist so
# the same number always produces the same advice.
BAND_PRIME = 80
BAND_GOOD = 65
BAND_MODERATE = 50


def _weights() -> Dict[str, float]:
    """Weights from config when present, else the defaults. Lets the blend
    be retuned in .env once there is enough history to judge it, without a
    code change."""
    settings = get_settings()
    configured = getattr(settings, "readiness_weights", None)
    if not configured:
        return dict(DEFAULT_WEIGHTS)

    try:
        parsed = {}
        for pair in str(configured).split(","):
            name, _, value = pair.partition("=")
            parsed[name.strip()] = float(value)
        total = sum(parsed.values())
        if parsed and total > 0:
            return parsed
    except (ValueError, AttributeError) as e:
        logger.warning(f"READINESS_WEIGHTS unparseable, using defaults: {e}")
    return dict(DEFAULT_WEIGHTS)


def score(day: Optional[str] = None) -> Optional[Dict]:
    """The composite for `day` (default: today's logging day), or None if
    no component has data.

    Returns the number plus everything needed to explain it: each
    component's raw value, the weight it actually carried after
    renormalization, and the list of components that were missing.
    """
    from sunny_code.components import day_boundary

    day = day or day_boundary.day_key()
    weights = _weights()

    present, missing = {}, []
    for metric in weights:
        value = metrics_store.get_for_day(metric, day)
        if value is None:
            missing.append(metric)
        else:
            present[metric] = value

    if not present:
        return None

    total_weight = sum(weights[m] for m in present)
    if total_weight <= 0:
        return None

    components = []
    composite = 0.0
    for metric, value in present.items():
        effective = weights[metric] / total_weight
        clamped = max(0.0, min(100.0, value))
        composite += clamped * effective
        components.append({
            "metric": metric,
            "label": _LABELS.get(metric, metric),
            "value": round(value, 1),
            "weight": round(effective, 3),
        })

    components.sort(key=lambda c: -c["weight"])
    return {
        "day": day,
        "score": round(composite),
        "band": band(composite),
        "components": components,
        "missing": missing,
        # True only when every configured component had data. The chart
        # and the brief both need to distinguish a full score from a
        # partial one rather than showing them identically.
        "complete": not missing,
    }


def band(value: float) -> str:
    if value >= BAND_PRIME:
        return "prime"
    if value >= BAND_GOOD:
        return "good"
    if value >= BAND_MODERATE:
        return "moderate"
    return "low"


def load_gap() -> Optional[Dict]:
    """How current monthly training load compares to Garmin's own target
    range, per intensity band.

    Separate from score() on purpose -- see the module docstring. This is
    the "do I need to train" half, and it is the half that speaks to
    consistency rather than recovery.

    `deficit` is how far below the target minimum each band sits, as a
    percentage of that minimum. Positive means under-trained.
    """
    bands = []
    for metric, target_min_metric, label in (
        (garmin_client.M_LOAD_AEROBIC_LOW, garmin_client.M_LOAD_AEROBIC_LOW_MIN, "aerobic base"),
        (garmin_client.M_LOAD_AEROBIC_HIGH, garmin_client.M_LOAD_AEROBIC_HIGH_MIN, "aerobic high"),
        (garmin_client.M_LOAD_ANAEROBIC, garmin_client.M_LOAD_ANAEROBIC_MIN, "anaerobic"),
    ):
        current = metrics_store.latest(metric)
        target = metrics_store.latest(target_min_metric)
        if not current or not target or not target["value"]:
            continue
        deficit = (target["value"] - current["value"]) / target["value"] * 100
        bands.append({
            "label": label,
            "current": round(current["value"]),
            "target_min": round(target["value"]),
            "deficit_pct": round(max(0.0, deficit)),
        })

    if not bands:
        return None

    worst = max(bands, key=lambda b: b["deficit_pct"])
    return {
        "bands": bands,
        "worst": worst,
        # Any band more than a quarter below its target minimum is a real
        # gap rather than normal week-to-week variation.
        "under_target": worst["deficit_pct"] >= 25,
    }


def headline(day: Optional[str] = None) -> Optional[Dict]:
    """The readiness number to LEAD with, and what it actually is.

    Garmin's own Training Readiness when it exists, because that is the
    figure also shown in the Garmin app -- two screens disagreeing about
    "readiness" is worse than either number being slightly less
    considered.

    Falls back to the composite when Garmin has none for that day (it only
    reports on recent days, and only on watches that support it). The
    fallback is LABELLED differently rather than silently substituted:
    showing a blended score under the same name Garmin uses would make
    the series quietly mean two different things depending on the date.
    """
    from sunny_code.components import day_boundary, garmin_client, metrics_store

    day = day or day_boundary.day_key()
    garmin_value = metrics_store.get_for_day(garmin_client.M_TRAINING_READINESS, day)
    if garmin_value is not None:
        return {
            "value": round(garmin_value),
            "source": "garmin",
            "label": "Training readiness",
            "band": band(garmin_value),
        }

    composite = score(day)
    if composite is None:
        return None
    return {
        "value": composite["score"],
        "source": "composite",
        "label": "Sunny Readiness",
        "band": composite["band"],
    }


def summary_line(day: Optional[str] = None) -> Optional[str]:
    """One line for a briefing, or None if there's nothing to say."""
    lead = headline(day)
    if lead is None:
        return None

    parts = [f"{lead['label']} {lead['value']}/100 ({lead['band']})"]
    if lead["source"] == "composite":
        result = score(day)
        if result and not result["complete"]:
            parts.append(f"from {len(result['components'])} of {len(_weights())} signals")

    gap = load_gap()
    if gap and gap["under_target"]:
        worst = gap["worst"]
        parts.append(
            f"{worst['label']} load {worst['deficit_pct']}% under target "
            f"({worst['current']} vs {worst['target_min']})"
        )

    return " · ".join(parts)


def recompute_history(days: int = 365) -> int:
    """Store the composite for every day that has components, so the chart
    has history rather than starting from today.

    Cheap and idempotent: pure arithmetic over already-stored metrics, no
    API calls, and metrics_store upserts. Safe to re-run after retuning
    the weights -- which is the point, since retuning should update the
    past as well as the future.
    """
    from sunny_code.components import day_boundary

    today = day_boundary.logging_day()
    stored = 0
    for offset in range(days):
        day = (today - timedelta(days=offset)).isoformat()
        result = score(day)
        if result is not None:
            metrics_store.record(M_SCORE, result["score"], ts=day)
            stored += 1

    logger.info(f"Readiness history recomputed: {stored} days")
    return stored
