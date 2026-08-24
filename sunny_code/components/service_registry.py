"""Per-service on/off + autostart-on-boot state for Sunny's background
loops (dashboard refresh, alarm/reminder due-checks, usage refresh, the
weekly health check, morning-prep pre-warming, and whether Sunny's
persistent voice presence connects at all). Set through /service in
Discord, not .env -- same "runtime state, not a secret" reasoning and
live-takes-effect pattern as category_store.py/location_store.py.

Two independent flags per service:
- enabled:   is it allowed to act right now? Checked at the top of every
             loop tick / at the point a service would act, so toggling
             takes effect within one tick, not just at boot.
- autostart: should its tasks.loop actually .start() when Sunny boots?
             Checked once, at startup, alongside `enabled` -- a service
             can be enabled but not autostarted (stays off until manually
             started -- not exposed today, no loop.start() call site takes
             a manual-start path yet) or autostarted but later disabled
             (loop keeps running, ticks are just no-ops).

Also holds vacation_mode -- a single global flag, not a per-service one --
since it doesn't map to any one loop; see assistant.py and discord_bot.py
for what checks it.
"""

import json
import logging
from typing import Dict, List, Tuple

from sunny_code.components import vault_io
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# The fixed set of togglable services -- not user-extensible (unlike
# categories/lists), since each name corresponds to a real loop wired by
# hand in main.py/discord_bot.py, not an open-ended user concept.
SERVICES = (
    "dashboard_refresh",
    "scheduled_check",
    "usage_refresh",
    "health_check",
    "morning_prep",
    "voice_join",
    "rules_engine",
)

_DEFAULTS = {name: {"enabled": True, "autostart": True} for name in SERVICES}


def _path():
    return get_settings().project_root / "service_registry.json"


def _load() -> Dict[str, Dict[str, bool]]:
    path = _path()
    if not path.exists():
        _save(_DEFAULTS, vacation_mode=False)
        return {k: dict(v) for k, v in _DEFAULTS.items()}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        services = data.get("services")
        vacation = bool(data.get("vacation_mode", False))
        if isinstance(services, dict):
            # Merge with defaults so a newly-added SERVICES entry (a future
            # code change) still gets a sane default instead of a KeyError.
            merged = {k: dict(v) for k, v in _DEFAULTS.items()}
            for name, flags in services.items():
                if name in merged and isinstance(flags, dict):
                    merged[name]["enabled"] = bool(flags.get("enabled", True))
                    merged[name]["autostart"] = bool(flags.get("autostart", True))
            merged["_vacation_mode"] = vacation
            return merged
    except (OSError, ValueError) as e:
        logger.error(f"service_registry.json unreadable: {e}")

    return {k: dict(v) for k, v in _DEFAULTS.items()}


def _save(services: Dict[str, Dict[str, bool]], vacation_mode: bool = None) -> None:
    services = {k: v for k, v in services.items() if k in SERVICES}
    if vacation_mode is None:
        vacation_mode = _load().get("_vacation_mode", False)
    vault_io.atomic_write_text(
        _path(), json.dumps({"services": services, "vacation_mode": vacation_mode}, indent=2)
    )


def _validate(name: str) -> None:
    if name not in SERVICES:
        raise ValueError(f"Unknown service {name!r} -- must be one of {', '.join(SERVICES)}")


def is_enabled(name: str) -> bool:
    _validate(name)
    return _load()[name]["enabled"]


def is_autostart(name: str) -> bool:
    _validate(name)
    return _load()[name]["autostart"]


def set_enabled(name: str, on: bool) -> Tuple[bool, str]:
    _validate(name)
    data = _load()
    data[name]["enabled"] = on
    _save(data)
    logger.info(f"Service {name!r} {'enabled' if on else 'disabled'}")
    return True, f'{name}: {"enabled" if on else "disabled"}'


def set_autostart(name: str, on: bool) -> Tuple[bool, str]:
    _validate(name)
    data = _load()
    data[name]["autostart"] = on
    _save(data)
    logger.info(f"Service {name!r} autostart {'on' if on else 'off'}")
    return True, f'{name}: autostart {"on" if on else "off"} (takes effect on next restart)'


def status_lines() -> List[str]:
    """One line per service, for /service with no arguments."""
    data = _load()
    lines = []
    for name in SERVICES:
        flags = data[name]
        state = "on" if flags["enabled"] else "off"
        autostart = "autostart" if flags["autostart"] else "manual"
        lines.append(f"{name}: {state} ({autostart})")
    return lines


def is_vacation_mode() -> bool:
    return _load().get("_vacation_mode", False)


def set_vacation_mode(on: bool) -> Tuple[bool, str]:
    data = _load()
    _save(data, vacation_mode=on)
    logger.info(f"Vacation mode {'on' if on else 'off'}")
    if on:
        return True, "Vacation mode on -- morning/evening prep and nudges are paused until you turn it off."
    return True, "Vacation mode off -- back to normal morning/evening behavior."
