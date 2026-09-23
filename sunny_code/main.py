"""Main entry point for Project SUNNY."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from discord.ext import tasks
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from uvicorn import Server, Config

from sunny_code.config import get_settings, looks_configured
from sunny_code.logging_config import setup_logging
from sunny_code.components.dashboard import create_dashboard_app
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.briefing_api import create_briefing_router
from sunny_code.components.dashboard_data_routes import create_dashboard_data_router
from sunny_code.components.logs_routes import create_logs_router
from sunny_code.components.metrics_routes import create_metrics_router
from sunny_code.components.chat_routes import create_chat_router
from sunny_code.components.push_routes import create_push_router
from sunny_code.components.time_parse import next_occurrence
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.tasks_api import create_tasks_router
from sunny_code.components.lists_db import ListDB
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_db import ScheduledDB
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.scheduled_vault_mirror import create_scheduled_vault_mirror, write_scheduled_mirror
from sunny_code.components import pi_companion
from sunny_code.components.pi_companion import create_pi_companion_router
from sunny_code.components.discord_bot import create_discord_bot
from sunny_code.components.google_routes import create_google_auth_router
from sunny_code.components.spotify_engine import SpotifyEngine
from sunny_code.components.spotify_routes import create_spotify_auth_router
from sunny_code.components.calendar_engine import CalendarEngine
from sunny_code.components.crash_check import check_previous_crash
from sunny_code.components import (
    daily_ingest, health_check, memory_store, notify, personality, push_service,
    rules_engine, service_registry, token_tracker,
)
from sunny_code.components.health_check import run_weekly_health_check
from sunny_code.components.weather_routes import create_weather_router
from sunny_code.components.location_routes import create_location_router
from sunny_code.components.legal_pages import create_legal_router
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
        vault_state_dir = self.settings.project_root / "sunny-vault" / "data" / "state"
        tasks_db = TaskDB(vault_state_dir / "tasks")
        self.tasks_engine = TaskEngine(tasks_db)
        self.briefing_engine = BriefingEngine()
        lists_db = ListDB(vault_state_dir / "lists")
        self.list_engine = ListEngine(lists_db)
        scheduled_db = ScheduledDB(self.settings.project_root / "scheduled.db")
        self.scheduled_engine = ScheduledEngine(scheduled_db)
        self.project_engine = ProjectEngine()
        self.spotify_engine = SpotifyEngine()
        self.calendar_engine = CalendarEngine()

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

        # Same guard, same reason, for the weekly health-check loop below.
        self._health_check_started = False

        # Same guard, same reason, for the rules-engine loop below.
        self._rules_engine_started = False

        # Same guard, same reason, for the daily health-data ingest loop below.
        self._daily_ingest_started = False

        # Same guard, same reason, for the scheduled-dispatch loop below.
        self._scheduled_dispatch_started = False

        # Create sunny-vault/personality.md if it's missing, so the file is
        # discoverable in Obsidian rather than being a feature you'd only
        # find by reading the source. Never overwrites an existing one --
        # see personality.py on why Sunny otherwise never writes this file.
        personality.ensure_exists()
        # Same for the memory profile -- a scaffold in the vault is how
        # the feature becomes discoverable in Obsidian rather than
        # something you would only find by reading the source. Never
        # overwrites; see memory_store on why Sunny must not author it.
        memory_store.ensure_profile()

        self.app = self._create_app()
        self.discord_bot = self._create_discord_bot()
        # Registered once here (not re-fetched per run) so run_weekly_health_check()
        # posts the same way whether it's the scheduled Sunday loop below or an
        # on-demand "run health check" from assistant.py -- self.discord_bot never
        # changes after this point, so a one-time registration is equivalent to the
        # old getattr-every-time pattern.
        health_check.set_post_fn(getattr(self.discord_bot, "post_to_health", None) if self.discord_bot else None)
        self.health_check_loop = self._create_health_check_loop()
        self.rules_engine_loop = self._create_rules_engine_loop()
        self.daily_ingest_loop = self._create_daily_ingest_loop()
        self.scheduled_dispatch_loop = self._create_scheduled_dispatch_loop()
        # Discord becomes one delivery channel rather than the mechanism.
        notify.register("discord", self._discord_notifier())
        # The companion screen is a delivery channel too -- a notification
        # that only reaches a phone is no use when the phone is in another
        # room and the device is on the desk in front of you.
        notify.register("pi", pi_companion.notify_device)

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
            self.project_engine,
            self.spotify_engine,
            self.calendar_engine,
            self.settings.discord_chat_channel_id,
            dashboard_channel_id=self.settings.discord_tasks_channel_id,
            briefings_channel_id=self.settings.discord_briefings_channel_id,
            warnings_channel_id=self.settings.discord_warnings_channel_id,
            task_updates_channel_id=self.settings.discord_task_updates_channel_id,
            health_channel_id=self.settings.discord_health_channel_id,
            usage_channel_id=self.settings.discord_usage_channel_id,
            reminders_channel_id=self.settings.discord_reminders_channel_id,
            voice_channel_id=self.settings.discord_voice_channel_id,
        )

    def _create_health_check_loop(self):
        """Standalone weekly Sunday-4am system health check (see
        sunny_code/components/health_check.py) — deliberately not attached to
        the Discord client, unlike the bot's own tasks.loop instances in
        discord_bot.py. Must run and log even when Discord isn't configured;
        posting the report to Discord is optional, not a requirement for the
        check itself to happen. Same reasoning, same place, as the vault
        mirror wiring above.

        discord.ext.tasks.loop's time= fires daily with no native
        day-of-week filter, so the callback checks for Sunday itself and
        no-ops otherwise. tzinfo is bound once here at startup — changing
        LOCAL_TIMEZONE needs a restart, unlike most settings in this app."""
        tz = ZoneInfo(self.settings.local_timezone)

        @tasks.loop(time=dtime(hour=4, tzinfo=tz))
        async def health_check_loop():
            if not service_registry.is_enabled("health_check"):
                return
            if datetime.now(tz).weekday() != 6:  # Monday=0 ... Sunday=6
                return
            await run_weekly_health_check()

        return health_check_loop

    def _create_rules_engine_loop(self):
        """Layer 1/2 proactive-architecture loop (see sunny_code/components/
        rules_engine.py, sensors.py) — deterministic, no LLM calls, so a
        30-minute interval is cheap. Standalone like the health-check loop
        above, not Discord-attached: the sensors/rules don't need Discord to
        do their (currently log-only) work, same "run and log regardless of
        whether Discord is configured" reasoning."""

        @tasks.loop(minutes=30)
        async def rules_engine_loop():
            if not service_registry.is_enabled("rules_engine"):
                return
            try:
                await asyncio.to_thread(rules_engine.evaluate)
            except Exception as e:
                self.logger.error(f"rules_engine_loop: evaluate() failed: {e}", exc_info=True)

        return rules_engine_loop

    def _create_daily_ingest_loop(self):
        """Health-data capture (see daily_ingest.py). Standalone like the
        two loops above — it doesn't need Discord, and barometric pressure
        in particular must keep being logged whether or not anything is
        connected, because it's the one input to the migraine correlation
        that can't be backfilled later.

        An interval loop rather than a fixed clock time so a restart can't
        skip a day. Twice daily: enough to pick up Garmin's revisions to
        the previous night's sleep/readiness scores, nowhere near often
        enough to resemble polling an unofficial API authenticated as the
        user. discord.ext.tasks runs the callback once immediately on
        .start(), so a restart also captures straight away rather than
        waiting out the first interval."""

        @tasks.loop(hours=daily_ingest.INTERVAL_HOURS)
        async def daily_ingest_loop():
            if not service_registry.is_enabled("daily_ingest"):
                return
            try:
                await asyncio.to_thread(daily_ingest.run)
            except Exception as e:
                self.logger.error(f"daily_ingest_loop: run() failed: {e}", exc_info=True)

        return daily_ingest_loop

    def _discord_notifier(self):
        """Discord as a notify.py channel, or None when unconfigured.

        Returning None rather than a no-op callable is deliberate: notify
        then reports Discord as simply absent, instead of a channel that
        silently accepts everything and delivers nothing.
        """
        if self.discord_bot is None:
            return None

        async def deliver(title: str, body: str) -> None:
            channel = await self.discord_bot.fetch_channel(self.settings.discord_chat_channel_id)
            await channel.send(f"{title}: {body}" if body else title)

        return deliver

    def _create_scheduled_dispatch_loop(self):
        """Fire due alarms and reminders, through every notification
        channel rather than just Discord.

        This used to live inside discord_bot.py's scheduled_check_loop,
        which had two real consequences: with Discord unconfigured the
        loop never ran, so a reminder set from the web or the Pi fired
        nowhere at all; and a Discord channel-fetch failure returned
        early, before anything was marked fired or rescheduled, so a
        permissions problem silently suppressed reminders instead of
        reporting one.

        Standalone here alongside the health-check and rules loops, for
        the same reason those are: delivery is optional, the work is not.
        Marking an item fired happens whether or not any channel accepted
        it -- otherwise a failing channel would make it re-fire every 30
        seconds forever.
        """

        @tasks.loop(seconds=30)
        async def scheduled_dispatch_loop():
            if not service_registry.is_enabled("scheduled_check"):
                return
            try:
                now = datetime.now()
                due = self.scheduled_engine.db.get_due_items(now)
                for item in due:
                    noun = "Alarm" if item["kind"] == "alarm" else "Reminder"
                    await notify.send(
                        title=noun,
                        body=item["label"],
                        url="/sunny",
                        tag=f"scheduled-{item['id']}",
                        # An alarm you sleep through is useless, so it
                        # stays on screen until acknowledged. A reminder
                        # behaves like every other notification.
                        require_interaction=(item["kind"] == "alarm"),
                    )

                    if item["recurrence"]:
                        trigger_at = datetime.fromisoformat(item["trigger_at"])
                        self.scheduled_engine.db.reschedule(
                            item["id"], next_occurrence(trigger_at, item["recurrence"])
                        )
                    else:
                        self.scheduled_engine.db.deactivate(item["id"])
            except Exception as e:
                self.logger.error(f"scheduled_dispatch_loop failed: {e}", exc_info=True)

        return scheduled_dispatch_loop

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

            # Same double-start hazard as the Discord bot above (HTTP + HTTPS
            # servers both fire this hook against the same app) — same guard.
            if not self._health_check_started:
                self._health_check_started = True
                if service_registry.is_autostart("health_check"):
                    self.health_check_loop.start()

            # Same double-start hazard, same guard, for the rules-engine loop.
            if not self._rules_engine_started:
                self._rules_engine_started = True
                if service_registry.is_autostart("rules_engine"):
                    self.rules_engine_loop.start()

            # Same again for health-data capture (Garmin + barometric
            # pressure) -- see _create_daily_ingest_loop.
            if not self._daily_ingest_started:
                self._daily_ingest_started = True
                if service_registry.is_autostart("daily_ingest"):
                    self.daily_ingest_loop.start()

            # Same again for due alarms/reminders.
            if not self._scheduled_dispatch_started:
                self._scheduled_dispatch_started = True
                if service_registry.is_autostart("scheduled_check"):
                    self.scheduled_dispatch_loop.start()

            yield
            if discord_task is not None:
                await self.discord_bot.close()
                discord_task.cancel()
            self.health_check_loop.cancel()
            self.rules_engine_loop.cancel()
            self.daily_ingest_loop.cancel()
            self.scheduled_dispatch_loop.cancel()
            # Release the pooled SQLite connections from plan item A4 —
            # each of these opened a single long-lived connection instead
            # of reconnecting per call; close them on real shutdown so the
            # fd isn't held by a process that's exiting anyway.
            self.scheduled_engine.db.close()
            self.dashboard_app.db.close()
            token_tracker.close()

        app = FastAPI(
            title=self.settings.app_name,
            version="0.1.0",
            debug=self.settings.debug,
            lifespan=lifespan,
        )

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/")
        @app.get("/console")
        async def root():
            """Sunny's own web console was retired 2026-09-13 -- the
            project-dashboard app now owns this host's web UI. /console
            redirects too, not just /, since that was the URL people
            actually had bookmarked/documented."""
            return RedirectResponse(url=self.settings.dashboard_url)

        # Dashboard endpoints
        dashboard_app = create_dashboard_app()
        self.dashboard_app = dashboard_app
        app.include_router(dashboard_app.router, prefix="/api")

        # Briefing endpoints
        briefing_router = create_briefing_router()
        app.include_router(briefing_router, prefix="/api")

        # Structured Calendar/Gmail read endpoints for external dashboards
        # (e.g. keaton.dev) — /api/calendar/today, /api/gmail/flagged
        dashboard_data_router = create_dashboard_data_router()
        app.include_router(dashboard_data_router, prefix="/api")

        # Time-series + check-in endpoints -- /api/metrics/series,
        # /api/checkin/*, /api/health/garmin/* (see metrics_routes.py)
        app.include_router(create_metrics_router(), prefix="/api")

        # Read-only log + routing-trace access -- /api/logs,
        # /api/logs/{name}, /api/traces/recent (see logs_routes.py).
        # traces.jsonl has been written with no reader since the console
        # was retired 2026-09-13; this gives it one again.
        app.include_router(create_logs_router(), prefix="/api")

        # Web Push subscription + send (see push_service.py)
        app.include_router(create_push_router(), prefix="/api")

        # Streaming HTTP chat for the web/PWA -- same handle_message() the
        # Discord bot and the Pi use, same shared engines (see chat_routes.py)
        app.include_router(
            create_chat_router(
                self.tasks_engine, self.briefing_engine, self.list_engine,
                self.scheduled_engine, self.project_engine, self.spotify_engine,
                self.calendar_engine,
            ),
            prefix="/api",
        )

        # Task endpoints
        tasks_router = create_tasks_router(self.tasks_engine)
        app.include_router(tasks_router, prefix="/api")

        # Sunny Companion hardware device -- /ws/pi (bypasses Discord entirely,
        # see sunny-companion/BUILD_PLAN.md Phase 6)
        async def _post_to_warnings_if_configured(text: str) -> None:
            # Lazy lookup, not a resolved value up front: _create_app() runs
            # before self.discord_bot is assigned (see __init__), but by the
            # time any request actually reaches this endpoint the app is
            # fully constructed, so the attribute is there.
            post_fn = getattr(self.discord_bot, "post_to_warnings", None)
            if post_fn is not None:
                await post_fn(text)

        pi_companion_router = create_pi_companion_router(
            self.tasks_engine,
            self.briefing_engine,
            self.list_engine,
            self.scheduled_engine,
            self.project_engine,
            self.spotify_engine,
            self.calendar_engine,
            post_to_warnings=_post_to_warnings_if_configured,
        )
        app.include_router(pi_companion_router)

        # Google Sign-In (OAuth) — /auth/google/login, /callback, /status, /disconnect
        google_router = create_google_auth_router()
        app.include_router(google_router)

        # Spotify Sign-In (OAuth) — /auth/spotify/login, /callback, /status, /disconnect
        spotify_router = create_spotify_auth_router()
        app.include_router(spotify_router)

        # Weather location — /api/weather/location (read/write; no web UI since the console's retirement)
        weather_router = create_weather_router()
        app.include_router(weather_router)

        # GPS location reports — /api/location/owntracks
        location_router = create_location_router()
        app.include_router(location_router)

        # /legal/home, /legal/privacy, /legal/terms — for Google OAuth verification
        legal_router = create_legal_router()
        app.include_router(legal_router)

        return app

    async def start(self):
        """Start the Sunny core application."""
        self.logger.info("Starting Project SUNNY...")
        self.logger.info(
            f"Environment: {self.settings.app_env}, Debug: {self.settings.debug}"
        )
        for line in startup_summary().split("\n"):
            self.logger.info(line)

        # A native crash (segfault, glibc heap corruption, OOM-kill) never
        # reaches sunny.log — the process dies before Python logging runs.
        # This is the one place that gap is closed, so it's logged locally
        # even when Discord isn't configured — see crash_check.py.
        crash_signature = check_previous_crash()
        if crash_signature:
            self.logger.warning(f"Previous run crashed: {crash_signature}")

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
