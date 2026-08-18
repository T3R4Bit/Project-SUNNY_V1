"""Configuration and secrets management for Project SUNNY."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)


class Config:
    """Application configuration from environment variables."""

    # Tailscale
    TAILSCALE_IP = os.getenv("TAILSCALE_IP", "127.0.0.1")
    TAILSCALE_PORT = int(os.getenv("TAILSCALE_PORT", "5000"))

    # Claude API
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    # Sonic API (TTS)
    SONIC_API_KEY = os.getenv("SONIC_API_KEY", "")

    # Twilio (phone)
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

    # Discord (logging/audit)
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

    # Notion (final storage)
    NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")

    # Obsidian vault paths
    OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "sunny-vault")

    # Spending limits (provider-level hard caps, in cents)
    CLAUDE_MONTHLY_BUDGET_CENTS = int(os.getenv("CLAUDE_MONTHLY_BUDGET_CENTS", "2000"))  # $20
    TWILIO_MONTHLY_BUDGET_CENTS = int(os.getenv("TWILIO_MONTHLY_BUDGET_CENTS", "1000"))  # $10

    # Database
    DB_PATH = Path(__file__).parent.parent / "sunny.db"

    @classmethod
    def validate(cls) -> list[str]:
        """
        Validate required secrets are set.

        Returns:
            List of missing required secrets (empty if all present)
        """
        required = [
            "CLAUDE_API_KEY",
            "SONIC_API_KEY",
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_PHONE_NUMBER",
            "DISCORD_WEBHOOK_URL",
            "NOTION_API_KEY",
        ]

        missing = [key for key in required if not getattr(cls, key)]
        return missing


def check_config():
    """Check and log configuration status."""
    from .logging import logger

    missing = Config.validate()
    if missing:
        logger.warning(f"Missing secrets: {', '.join(missing)}")
        logger.info("Set them in .env file or as environment variables")
    else:
        logger.info("All required secrets configured ✓")
