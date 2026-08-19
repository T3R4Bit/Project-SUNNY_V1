"""Main entry point for Project SUNNY."""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from uvicorn import Server, Config

from sunny.config import get_settings
from sunny.logging_config import setup_logging
from sunny.components.dashboard import create_dashboard_app
from sunny.components.briefing import BriefingEngine
from sunny.components.briefing_api import create_briefing_router
from sunny.components.tasks_db import TaskDB
from sunny.components.tasks_engine import TaskEngine
from sunny.components.tasks_api import create_tasks_router
from sunny.components.chatbot_ui import create_chatbot_router
from sunny.components.console_stats import create_console_router
from sunny.components.discord_bot import create_discord_bot
from sunny.components.key_status import startup_summary


logger = logging.getLogger(__name__)


class SunnyCore:
    """Main application coordinator."""

    def __init__(self):
        self.settings = get_settings()
        self.logger = setup_logging()
        self.app = self._create_app()
        self.discord_bot = self._create_discord_bot()

    def _create_discord_bot(self):
        """Build the Discord bot if a token is configured; otherwise skip it quietly —
        the web chatbot covers the same task commands regardless."""
        if not self.settings.discord_bot_token or not self.settings.discord_tasks_channel_id:
            self.logger.info("Discord bot not configured (no token/channel) — skipping")
            return None

        tasks_db = TaskDB(self.settings.project_root / "tasks.db")
        tasks_engine = TaskEngine(tasks_db)
        briefing_engine = BriefingEngine()
        return create_discord_bot(
            tasks_engine, briefing_engine, self.settings.discord_tasks_channel_id
        )

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with all routes."""
        app = FastAPI(
            title=self.settings.app_name,
            version="0.1.0",
            debug=self.settings.debug,
        )

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        # Dashboard endpoints
        dashboard_app = create_dashboard_app()
        app.include_router(dashboard_app.router, prefix="/api")

        # Briefing endpoints
        briefing_router = create_briefing_router()
        app.include_router(briefing_router, prefix="/api")

        # Task endpoints
        tasks_router = create_tasks_router()
        app.include_router(tasks_router, prefix="/api")

        # Chatbot UI
        chatbot_router = create_chatbot_router()
        app.include_router(chatbot_router)

        # Console stats dashboard
        console_router = create_console_router()
        app.include_router(console_router)

        return app

    async def start(self):
        """Start the Sunny core application."""
        self.logger.info("Starting Project SUNNY...")
        self.logger.info(
            f"Environment: {self.settings.app_env}, Debug: {self.settings.debug}"
        )
        for line in startup_summary().split("\n"):
            self.logger.info(line)

        # Run FastAPI server
        config = Config(
            app=self.app,
            host=self.settings.api_host,
            port=self.settings.api_port,
            log_level="info" if self.settings.debug else "warning",
        )
        server = Server(config)

        if self.discord_bot is not None:
            await asyncio.gather(
                server.serve(),
                self.discord_bot.start(self.settings.discord_bot_token),
            )
        else:
            await server.serve()

    def run(self):
        """Blocking run (for systemd/production)."""
        asyncio.run(self.start())


# Global app instance for uvicorn
sunny = SunnyCore()
app = sunny.app


def main():
    """Entry point."""
    sunny.run()


if __name__ == "__main__":
    main()
