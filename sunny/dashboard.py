"""FastAPI dashboard for monitoring Sunny health, spending, and system status."""

import sqlite3
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import psutil

from .config import Config
from .logging import logger

app = FastAPI(title="Project SUNNY Dashboard")


# ============================================================================
# Database Setup
# ============================================================================

def init_db():
    """Initialize SQLite database for metrics."""
    db_path = Config.DB_PATH
    db_path.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Metrics table (30-second samples)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            cpu_percent REAL,
            ram_percent REAL,
            disk_percent REAL,
            cpu_temp REAL,
            tokens_used INTEGER,
            tokens_cost REAL
        )
    """)

    # Service health (last-success timestamps)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_health (
            service_name TEXT PRIMARY KEY,
            last_success DATETIME,
            last_error TEXT,
            error_count INTEGER DEFAULT 0
        )
    """)

    # Token usage (daily rollup)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            date DATE PRIMARY KEY,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_cost REAL,
            by_model TEXT
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/health")
def get_health():
    """Service health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": psutil.boot_time(),
    }


@app.get("/api/resources")
def get_resources():
    """Get host resource metrics (CPU, RAM, disk, temperature)."""
    cpu_percent = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # CPU temperature (Linux only, may fail on some systems)
    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if "coretemp" in temps:
            cpu_temp = temps["coretemp"][0].current
    except (FileNotFoundError, AttributeError):
        pass

    return {
        "cpu_percent": cpu_percent,
        "ram_used_mb": ram.used // (1024 * 1024),
        "ram_total_mb": ram.total // (1024 * 1024),
        "ram_percent": ram.percent,
        "disk_used_gb": disk.used // (1024**3),
        "disk_total_gb": disk.total // (1024**3),
        "disk_percent": disk.percent,
        "cpu_temp_celsius": cpu_temp,
        "load_average": psutil.getloadavg(),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/spend")
def get_spend():
    """Current day spending and budget (placeholder)."""
    return {
        "tokens_today": 0,
        "cost_today": 0.0,
        "budget_daily": Config.CLAUDE_MONTHLY_BUDGET_CENTS / 100 / 30,  # Rough daily average
        "budget_monthly": Config.CLAUDE_MONTHLY_BUDGET_CENTS / 100,
        "month_to_date": 0.0,
        "projected_month_end": 0.0,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/alerts")
def get_alerts():
    """Things needing attention."""
    alerts = []

    # Check disk space
    disk = psutil.disk_usage("/")
    if disk.percent > 80:
        alerts.append({
            "type": "disk",
            "severity": "warning",
            "message": f"Root disk {disk.percent}% full",
        })

    # Check RAM
    ram = psutil.virtual_memory()
    if ram.percent > 85:
        alerts.append({
            "type": "memory",
            "severity": "warning",
            "message": f"RAM usage {ram.percent}%",
        })

    return {
        "count": len(alerts),
        "alerts": alerts,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Main dashboard HTML (simple for now)."""
    resources = get_resources()
    alerts = get_alerts()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Project SUNNY Dashboard</title>
        <style>
            body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
            .panel {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin: 10px 0; }}
            .metric {{ display: flex; justify-content: space-between; padding: 5px 0; }}
            .label {{ color: #8b949e; }}
            .value {{ color: #58a6ff; }}
            .warning {{ color: #d29922; }}
            .error {{ color: #f85149; }}
            h2 {{ border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
        </style>
        <meta http-equiv="refresh" content="60">
    </head>
    <body>
        <h1>🌞 Project SUNNY Dashboard</h1>

        <div class="panel">
            <h2>💻 Host Resources</h2>
            <div class="metric">
                <span class="label">CPU:</span>
                <span class="value">{resources['cpu_percent']}%</span>
            </div>
            <div class="metric">
                <span class="label">RAM:</span>
                <span class="value">{resources['ram_used_mb']}MB / {resources['ram_total_mb']}MB ({resources['ram_percent']}%)</span>
            </div>
            <div class="metric">
                <span class="label">Disk:</span>
                <span class="value">{resources['disk_used_gb']}GB / {resources['disk_total_gb']}GB ({resources['disk_percent']}%)</span>
            </div>
            {f'<div class="metric"><span class="label">CPU Temp:</span><span class="value">{resources["cpu_temp_celsius"]:.1f}°C</span></div>' if resources['cpu_temp_celsius'] else ''}
            <div class="metric">
                <span class="label">Load Avg:</span>
                <span class="value">{resources['load_average'][0]:.2f} {resources['load_average'][1]:.2f} {resources['load_average'][2]:.2f}</span>
            </div>
        </div>

        <div class="panel">
            <h2>💰 Spending</h2>
            <div class="metric">
                <span class="label">Today:</span>
                <span class="value">${0.00}</span>
            </div>
            <div class="metric">
                <span class="label">Month-to-date:</span>
                <span class="value">${0.00}</span>
            </div>
            <div class="metric">
                <span class="label">Budget (daily):</span>
                <span class="value">${0.00}</span>
            </div>
        </div>

        <div class="panel">
            <h2>⚠️ Alerts ({alerts['count']})</h2>
            {f"<p>✓ No alerts</p>" if not alerts['alerts'] else ''.join([
                f"<div class='metric'><span class='warning'>[{a['severity'].upper()}]</span> {a['message']}</div>"
                for a in alerts['alerts']
            ])}
        </div>

        <div class="panel">
            <p>Last updated: {resources['timestamp']}</p>
            <p>Page refreshes every 60 seconds.</p>
        </div>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host=Config.TAILSCALE_IP, port=Config.TAILSCALE_PORT)
