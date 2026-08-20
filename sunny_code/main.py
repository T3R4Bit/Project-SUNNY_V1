"""Main entry point for Project SUNNY."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from uvicorn import Server, Config

from sunny_code.config import get_settings, looks_configured
from sunny_code.logging_config import setup_logging
from sunny_code.components.dashboard import create_dashboard_app
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.briefing_api import create_briefing_router
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.tasks_api import create_tasks_router
from sunny_code.components.lists_db import ListDB
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.scheduled_db import ScheduledDB
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.scheduled_vault_mirror import create_scheduled_vault_mirror, write_scheduled_mirror
from sunny_code.components.chatbot_ui import create_chatbot_router
from sunny_code.components.console_stats import create_console_router
from sunny_code.components.discord_bot import create_discord_bot
from sunny_code.components.google_routes import create_google_auth_router
from sunny_code.components.weather_routes import create_weather_router
from sunny_code.components.key_status import startup_summary


logger = logging.getLogger(__name__)


class SunnyCore:
    """Main application coordinator."""

    def __init__(self):
        self.settings = get_settings()
        self.logger = setup_logging()
        # Shared engine instances used by the web chatbot, REST API, and Discord
        # bot, so a change from any interface is visible everywhere immediately
        # (e.g. an instant Discord dashboard refresh) instead of waiting on a
        # timer — see TaskEngine.on_change / ScheduledEngine.on_change.
        #
        # Tasks and Lists live in the Obsidian vault as markdown (Sunny is the
        # sole writer — see sunny-vault/docs/architecture/vault-storage.md),
        # not SQLite. Alarms/Reminders/Scheduled items are unaffected and stay
        # SQLite — see the read-only vault mirror wiring below instead.
        vault_state_dir = self.settings.project_root / "sunny-vault" / "state"
        tasks_db = TaskDB(vault_state_dir / "tasks")
        self.tasks_engine = TaskEngine(tasks_db)
        self.briefing_engine = BriefingEngine()
        lists_db = ListDB(vault_state_dir / "lists")
        self.list_engine = ListEngine(lists_db)
        scheduled_db = ScheduledDB(self.settings.project_root / "scheduled.db")
        self.scheduled_engine = ScheduledEngine(scheduled_db)

        # Read-only alarms/reminders mirror — updates on every change, and once
        # now so the file reflects reality from startup rather than staying
        # stale/absent until the first future change. Wired here (not inside
        # discord_bot.py) since it must work whether or not Discord is configured.
        write_scheduled_mirror(scheduled_db, self.settings.project_root / "sunny-vault")
        self.scheduled_engine.on_change = create_scheduled_vault_mirror(
            scheduled_db, self.settings.project_root / "sunny-vault"
        )

        # Guards the lifespan hook below against starting the Discord bot
        # twice — start() runs one uvicorn Server per port (plain HTTP always,
        # plus HTTPS when TLS is configured), and FastAPI's lifespan protocol
        # fires once per Server serving the same app.
        self._discord_started = False

        self.app = self._create_app()
        self.discord_bot = self._create_discord_bot()

    def _create_discord_bot(self):
        """Build the Discord bot if a token + chat channel are configured;
        otherwise skip it quietly — the web chatbot covers the same commands
        regardless. The dashboard channel is optional (falls back to chat)."""
        if not looks_configured(self.settings.discord_bot_token) or not self.settings.discord_chat_channel_id:
            self.logger.info("Discord bot not configured (no token/chat channel) — skipping")
            return None

        return create_discord_bot(
            self.tasks_engine,
            self.briefing_engine,
            self.list_engine,
            self.scheduled_engine,
            self.settings.discord_chat_channel_id,
            dashboard_channel_id=self.settings.discord_tasks_channel_id,
            briefings_channel_id=self.settings.discord_briefings_channel_id,
            warnings_channel_id=self.settings.discord_warnings_channel_id,
            task_updates_channel_id=self.settings.discord_task_updates_channel_id,
        )

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with all routes."""

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            # Must start the Discord bot from here, not from run()/start()'s own
            # asyncio.gather() below — this app object can be served multiple
            # ways (plain `uvicorn sunny_code.main:app` CLI, SunnyCore.run()
            # with one server, or SunnyCore.run() with an HTTP + HTTPS server
            # pair — see start()), and only the ASGI lifespan protocol fires
            # identically under all of them. A bot task started from
            # run()/start() alone silently never launches under the
            # `uvicorn module:app` CLI form, since that form never calls
            # run()/start() at all — found and fixed 2026-08-20 (the Discord
            # client constructed fine and sat there forever, never connecting,
            # no error, because .start() was simply never reached).
            #
            # Guarded by self._discord_started because running two Server
            # instances (HTTP + HTTPS) against this same app fires lifespan
            # twice — without the guard, the bot would connect twice and every
            # message would get handled and replied to twice.
            discord_task = None
            if self.discord_bot is not None and not self._discord_started:
                self._discord_started = True
                discord_task = asyncio.create_task(
                    self.discord_bot.start(self.settings.discord_bot_token)
                )
            yield
            if discord_task is not None:
                await self.discord_bot.close()
                discord_task.cancel()

        app = FastAPI(
            title=self.settings.app_name,
            version="0.1.0",
            debug=self.settings.debug,
            lifespan=lifespan,
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
        tasks_router = create_tasks_router(self.tasks_engine)
        app.include_router(tasks_router, prefix="/api")

        # Chatbot UI
        chatbot_router = create_chatbot_router(
            self.tasks_engine, self.briefing_engine, self.list_engine, self.scheduled_engine
        )
        app.include_router(chatbot_router)

        # Console stats dashboard
        console_router = create_console_router()
        app.include_router(console_router)

        # Google Sign-In (OAuth) — /auth/google/login, /callback, /status, /disconnect
        google_router = create_google_auth_router()
        app.include_router(google_router)

        # Weather location — /api/weather/location (read/write for the console's LOCATION card)
        weather_router = create_weather_router()
        app.include_router(weather_router)

        return app

    async def start(self):
        """Start the Sunny core application."""
        self.logger.info("Starting Project SUNNY...")
        self.logger.info(
            f"Environment: {self.settings.app_env}, Debug: {self.settings.debug}"
        )
        for line in startup_summary().split("\n"):
            self.logger.info(line)

        # Run FastAPI server. The Discord bot (if configured) starts from the
        # FastAPI lifespan hook in _create_app(), not here — see the comment
        # there for why, and for why it's guarded against firing per-server.
        log_level = "info" if self.settings.debug else "warning"
        http_config = Config(
            app=self.app,
            host=self.settings.api_host,
            port=self.settings.api_port,
            log_level=log_level,
        )
        servers = [Server(http_config)]

        # HTTPS is optional and only needed today for Google OAuth's redirect
        # URI policy (rejects plain http:// on a non-localhost domain) — see
        # sunny-vault/docs/architecture/google-integration.md. Plain HTTP on
        # api_port keeps working unchanged either way.
        if self.settings.tls_certfile and self.settings.tls_keyfile:
            https_config = Config(
                app=self.app,
                host=self.settings.api_host,
                port=self.settings.tls_port,
                ssl_certfile=self.settings.tls_certfile,
                ssl_keyfile=self.settings.tls_keyfile,
                log_level=log_level,
            )
            servers.append(Server(https_config))
            self.logger.info(f"HTTPS enabled on port {self.settings.tls_port}")

        await asyncio.gather(*(server.serve() for server in servers))

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
