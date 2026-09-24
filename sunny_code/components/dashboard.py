"""Dashboard API endpoints for monitoring."""

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from sunny_code.components import token_tracker
from sunny_code.config import get_settings


logger = logging.getLogger(__name__)


class DashboardDB:
    """SQLite database for metrics and health tracking."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Thread-local connections; see _connect().
        self._local = threading.local()
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Long-lived connection per thread, reused across calls instead of
        reopening sunny.db every time.

        Pooled because DashboardDB is single-PROCESS-only (only the main
        server ever constructs one; chat.py, the one other process running
        this codebase, never does), so there's no cross-process
        lock-contention concern, unlike scheduled_db.py's scheduled.db.

        Per-THREAD because sqlite3 connections may only be used from the
        thread that created them, and this class is reached from both
        FastAPI request handlers and discord.ext.tasks loops. Sharing one
        connection across those raised "SQLite objects created in a thread
        can only be used in that same thread" — see token_tracker._connect
        for the live 2026-09-20 occurrence and the same fix.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            with self._conns_lock:
                self._conns.append(conn)
        return conn

    def close(self) -> None:
        """Release every pooled connection. Call on app shutdown. Guarded
        per connection because closing one from a thread other than its
        creator is itself an error, and the process is exiting anyway."""
        with self._conns_lock:
            for conn in self._conns:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._conns.clear()
        self._local.conn = None

    def _init_db(self):
        """Initialize database schema."""
        conn = self._connect()
        with conn:
            cursor = conn.cursor()

            # Metrics table (30-second samples)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL,
                    ram_percent REAL,
                    disk_percent REAL,
                    cpu_temp REAL,
                    tokens_used INTEGER,
                    tokens_cost REAL
                )
                """
            )

            # Service health tracking
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS service_health (
                    service_name TEXT PRIMARY KEY,
                    last_success DATETIME,
                    last_error TEXT,
                    error_count INTEGER DEFAULT 0
                )
                """
            )

            # Token usage daily rollup
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    date DATE PRIMARY KEY,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_cost REAL,
                    by_model TEXT
                )
                """
            )

            logger.info(f"Database initialized: {self.db_path}")

    def record_metric(
        self,
        cpu: float,
        ram: float,
        disk: float,
        cpu_temp: float = None,
        tokens: int = 0,
        cost: float = 0.0,
    ):
        """Record a metrics snapshot."""
        conn = self._connect()
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO metrics (cpu_percent, ram_percent, disk_percent, cpu_temp, tokens_used, tokens_cost)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cpu, ram, disk, cpu_temp, tokens, cost),
            )

    def update_service_health(self, service: str, success: bool, error: str = None):
        """Update service health status."""
        conn = self._connect()
        with conn:
            cursor = conn.cursor()
            if success:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO service_health (service_name, last_success, error_count)
                    VALUES (?, ?, 0)
                    """,
                    (service, datetime.utcnow().isoformat()),
                )
            else:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO service_health (service_name, error_count)
                    VALUES (?, 1)
                    """,
                    (service,),
                )
                cursor.execute(
                    """
                    UPDATE service_health
                    SET last_error = ?, error_count = error_count + 1
                    WHERE service_name = ?
                    """,
                    (error, service),
                )

    def get_health_status(self) -> dict:
        """Get current service health."""
        conn = self._connect()
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM service_health ORDER BY service_name")
            rows = cursor.fetchall()
            return {row["service_name"]: dict(row) for row in rows}


class DashboardAPI:
    """Dashboard API routes."""

    def __init__(self, db: DashboardDB):
        self.db = db
        self.router = APIRouter(prefix="/dashboard")
        self._setup_routes()

    def _setup_routes(self):
        """Register API routes."""

        @self.router.get("/health")
        async def dashboard_health():
            """Get service health status."""
            health = self.db.get_health_status()
            return {"services": health, "timestamp": datetime.utcnow().isoformat()}

        @self.router.get("/metrics/latest")
        async def latest_metrics():
            """Get latest metrics snapshot."""
            conn = self.db._connect()
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM metrics ORDER BY timestamp DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return {"error": "No metrics recorded yet"}

        @self.router.post("/metrics/record")
        async def record_metrics(
            cpu: float, ram: float, disk: float, cpu_temp: float = None
        ):
            """Record a metrics snapshot."""
            self.db.record_metric(cpu, ram, disk, cpu_temp)
            return {"status": "recorded"}

        @self.router.get("/spend/today")
        async def spend_today():
            """Get today's actual LLM token spending, tracked by token_tracker.py."""
            settings = get_settings()
            usage = token_tracker.get_today_usage()
            return {
                "date": usage["date"],
                "tokens": usage["total_tokens"],
                "cost": usage["cost"],
                "cap": settings.daily_spend_cap,
                "remaining": max(0.0, settings.daily_spend_cap - usage["cost"]),
                "by_model": usage["by_model"],
            }

        @self.router.get("/spend/month")
        async def spend_month():
            """Get this month's cumulative LLM spend against the monthly cap."""
            settings = get_settings()
            usage = token_tracker.get_month_usage()
            cost = usage["cost"]
            return {
                "month": usage["month"],
                "cost": cost,
                "cap": settings.monthly_spend_cap,
                "remaining": max(0.0, settings.monthly_spend_cap - cost),
                # Added so the dashboard can break the month down by model.
                # A one-day split is mostly noise -- a single long
                # conversation dominates it -- while a month's is the
                # number that says where the money actually goes.
                "tokens": usage["total_tokens"],
                "by_model": usage["by_model"],
            }

        @self.router.get("/usage/live")
        async def usage_live():
            """Anthropic's own real-time rate-limit numbers (requests/tokens
            remaining in the current window, when each resets), straight from
            the response headers on the most recent Claude call -- distinct
            from spend/today and spend/month above, which are this app's own
            self-tracked cost estimate. Empty dict if no Claude call has
            happened yet this process (nothing to report, not an error)."""
            return {"rate_limits": token_tracker.get_latest_rate_limits()}

        @self.router.get("/status")
        async def status():
            """Overall dashboard status."""
            settings = get_settings()
            return {
                "name": settings.app_name,
                "status": "online",
                "tailscale_ip": settings.tailscale_ip,
                "api_port": settings.api_port,
                "timestamp": datetime.utcnow().isoformat(),
            }


def create_dashboard_app() -> DashboardAPI:
    """Factory for dashboard API."""
    settings = get_settings()
    db = DashboardDB(settings.db_path)
    return DashboardAPI(db)
