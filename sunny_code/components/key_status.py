"""Startup summary of which API keys are configured vs still missing.

Nothing crashes without a key — the affected feature just says "not connected"
(see sunny_code.components.data_sources). This module is purely for visibility: a
clear one-time summary of what's set up and what isn't, logged at startup and
posted to Discord when the bot connects.
"""

from typing import List, Tuple

from sunny_code.components import google_auth
from sunny_code.config import get_settings

# (label, settings attribute, env var name)
_TRACKED_KEYS = [
    ("Claude API (LLM)", "claude_api_key", "CLAUDE_API_KEY"),
    ("OpenWeatherMap (weather)", "openweathermap_api_key", "OPENWEATHERMAP_API_KEY"),
    ("Google OAuth client ID", "google_client_id", "GOOGLE_CLIENT_ID"),
    ("Google OAuth client secret", "google_client_secret", "GOOGLE_CLIENT_SECRET"),
    ("Discord bot token", "discord_bot_token", "DISCORD_BOT_TOKEN"),
    ("Discord tasks channel ID", "discord_tasks_channel_id", "DISCORD_TASKS_CHANNEL_ID"),
]


def missing_api_keys() -> List[Tuple[str, str]]:
    """Return (label, env_var) pairs for every tracked key that isn't set."""
    settings = get_settings()
    missing = []
    for label, attr, env_var in _TRACKED_KEYS:
        if not getattr(settings, attr, None):
            missing.append((label, env_var))
    return missing


def startup_summary() -> str:
    """Human-readable summary for logs / Discord: what still needs a key."""
    missing = missing_api_keys()
    lines = []

    if missing:
        lines.append("⚠️  Still needs an API key (set in .env at the project root):")
        for label, env_var in missing:
            lines.append(f"  • {label} — {env_var}")
        lines.append('Nothing breaks without these — affected features just say')
        lines.append('"not connected" instead of faking an answer.')
    else:
        lines.append("✅ All tracked API keys are configured.")

    if google_auth.is_client_configured() and not google_auth.is_connected():
        lines.append(
            "⚠️  Google OAuth client is configured but no account is signed in yet — "
            "visit /console and click \"Connect Google Account\"."
        )

    return "\n".join(lines)
