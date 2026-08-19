"""Dashboard API endpoints for monitoring."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from sunny_code.config import get_settings


logger = logging.getLogger(__name__)


class DashboardDB:
    """SQLite database for metrics and health tracking."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
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

            conn.commit()
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO metrics (cpu_percent, ram_percent, disk_percent, cpu_temp, tokens_used, tokens_cost)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cpu, ram, disk, cpu_temp, tokens, cost),
            )
            conn.commit()

    def update_service_health(self, service: str, success: bool, error: str = None):
        """Update service health status."""
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def get_health_status(self) -> dict:
        """Get current service health."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
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
            with sqlite3.connect(self.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
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
            """Get today's token spending."""
            return {
                "date": datetime.now().date().isoformat(),
                "tokens": 0,
                "cost": 0.0,
                "cap": 20.0,
                "remaining": 20.0,
            }

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
