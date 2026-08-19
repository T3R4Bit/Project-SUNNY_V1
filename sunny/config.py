"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings
from pathlib import Path


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

    # Network
    tailscale_ip: str = "100.117.41.53"  # Lenovo brain
    api_port: int = 5000
    api_host: str = "127.0.0.1"  # Local dev, will bind to tailscale_ip on brain

    # APIs
    claude_api_key: str = ""
    openweathermap_api_key: str = ""
    google_calendar_api_key: str = ""

    # Discord bot (tasks channel)
    discord_bot_token: str = ""
    discord_tasks_channel_id: int = 0

    # Spending caps
    daily_spend_cap: float = 20.0  # USD per day
    monthly_spend_cap: float = 100.0  # USD per month

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Lazy-load settings singleton."""
    return Settings()
