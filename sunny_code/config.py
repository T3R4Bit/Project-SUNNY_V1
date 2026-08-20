"""Configuration management using pydantic-settings."""

from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


def looks_configured(value: Optional[str]) -> bool:
    """True if `value` looks like a real secret, not empty and not a
    leftover placeholder from the .env template (see run.sh — every
    placeholder there, e.g. '...' or 'sk-ant-...', ends in '...'). No real
    API key/token/client-id/client-secret ends in three literal dots, so
    this is a safe way to tell "never filled in" from "actually set"."""
    v = (value or "").strip()
    return bool(v) and not v.endswith("...")


class Settings(BaseSettings):
    """Application settings from environment or .env file."""

    # App
    app_name: str = "Project SUNNY"
    app_env: str = "development"  # development, production
    debug: bool = True

    # Paths
    project_root: Path = Path(__file__).parent.parent
    logs_dir: Path = project_root / "logs"
    db_path: Path = project_root / "sunny.db"
    config_dir: Path = project_root / "config"
    google_token_path: Path = project_root / "google_token.json"

    # Network
    tailscale_ip: str = "100.117.41.53"  # Lenovo brain
    api_port: int = 5000
    api_host: str = "127.0.0.1"  # Local dev, will bind to tailscale_ip on brain

    # APIs
    claude_api_key: str = ""
    openweathermap_api_key: str = ""
    # OpenWeatherMap needs a place, not just a key — "City,State,CountryCode",
    # e.g. "Detroit,MI,US" (state code only applies to US cities).
    weather_location: str = ""

    # Google Sign-In (OAuth 2.0) — powers Calendar + Gmail. See
    # sunny-vault/docs/architecture/google-integration.md for the Google
    # Cloud Console setup steps required before this works.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://127.0.0.1:5000/auth/google/callback"

    # Discord bot — DISCORD_CHAT_CHANNEL_ID is the one required channel the bot
    # reads commands from (tasks/lists/alarms/server-admin). DISCORD_TASKS_
    # CHANNEL_ID is a separate, optional, read-only home for the pinned task
    # dashboard — falls back to the chat channel if unset, so a bare chat
    # channel alone reproduces the old single-channel behavior. The remaining
    # three are optional *output* channels for specific things — the bot never
    # reads commands from any of them. Any left unset (0) means that output
    # keeps going to the chat channel instead — see
    # sunny-vault/docs/architecture/discord-bot.md.
    discord_bot_token: str = ""
    discord_chat_channel_id: int = 0
    discord_tasks_channel_id: int = 0
    discord_briefings_channel_id: int = 0
    discord_warnings_channel_id: int = 0
    discord_task_updates_channel_id: int = 0

    @field_validator(
        "discord_chat_channel_id",
        "discord_tasks_channel_id",
        "discord_briefings_channel_id",
        "discord_warnings_channel_id",
        "discord_task_updates_channel_id",
        mode="before",
    )
    @classmethod
    def _coerce_channel_id(cls, v):
        """A blank value or a leftover '...' placeholder from the .env template
        (see run.sh) means "not set," same as omitting the line entirely —
        not a crash. Settings() is built from a hand-edited .env (an external
        boundary), so this is real input validation, not a hypothetical.

        No logging here on purpose — get_settings() constructs a fresh
        Settings() on every call (by design, so a live .env/location edit
        needs no restart), so this validator runs far more often than
        "someone changed something." key_status.startup_summary() already
        reports this once, cleanly, instead of flooding the log."""
        if v in (None, ""):
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    # Spending caps
    daily_spend_cap: float = 20.0  # USD per day
    monthly_spend_cap: float = 100.0  # USD per month

    # TLS (optional) — some external providers require HTTPS on the redirect/
    # callback URI (e.g. Google OAuth won't accept a plain-http non-localhost
    # URI). Empty means "not configured": Sunny serves plain HTTP only on
    # api_port, same as always. See sunny-vault/docs/architecture/
    # google-integration.md for how these get populated (a Tailscale-issued
    # cert, not a manually-managed one).
    tls_certfile: str = ""
    tls_keyfile: str = ""
    tls_port: int = 5443

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Build a fresh Settings from the current .env — deliberately not cached,
    so a live edit (location, an API key) takes effect on the very next call
    with no restart. Called often; keep this cheap and side-effect-free."""
    return Settings()
