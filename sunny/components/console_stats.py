"""Console-style system stats API and UI."""

import psutil
import logging
import subprocess
import socket
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import datetime

logger = logging.getLogger(__name__)

# Color scheme - modern dark with bright cyan/green
COLORS = {
    'bg': '#0a0e27',
    'primary': '#00d4ff',
    'secondary': '#00ff88',
    'border': '#00d4ff',
    'warning': '#ffb81c',
    'critical': '#ff4757',
}


def get_tailscale_ip():
    """Get current Tailscale IPv4 address."""
    try:
        result = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"Could not get Tailscale IP: {e}")
    return None


def create_console_router() -> APIRouter:
    """Create console stats routes."""
    router = APIRouter(prefix="/console")

    @router.get("/")
    async def console_ui():
        """Serve console-style dashboard."""
        tailscale_ip = get_tailscale_ip()
        tailscale_url = f"http://{tailscale_ip}:5000" if tailscale_ip else "http://127.0.0.1:5000"

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SUNNY Console</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Courier New', monospace;
            background: {COLORS['bg']};
            color: {COLORS['text']};
            padding: 20px;
            min-height: 100vh;
        }}

        .console {{
            background: {COLORS['bg']};
            border: 2px solid {COLORS['border']};
            padding: 15px;
            font-size: 13px;
            line-height: 1.6;
            max-width: 1000px;
            margin: 0 auto;
        }}

        .header {{
            border-bottom: 2px solid {COLORS['border']};
            margin-bottom: 15px;
            padding-bottom: 10px;
        }}

        .title {{
            font-weight: bold;
            color: {COLORS['primary']};
            white-space: pre;
            font-size: 11px;
        }}

        .status {{
            margin-bottom: 20px;
        }}

        .stat-line {{
            margin: 8px 0;
        }}

        .label {{
            display: inline-block;
            width: 180px;
            color: {COLORS['primary']};
            font-weight: bold;
        }}

        .value {{
            color: {COLORS['secondary']};
        }}

        .bar {{
            display: inline-block;
            width: 100px;
            height: 12px;
            background: #1a2540;
            border: 1px solid {COLORS['border']};
            margin: 0 5px;
            vertical-align: middle;
        }}

        .fill {{
            height: 100%;
            background: {COLORS['secondary']};
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 9px;
            color: {COLORS['bg']};
        }}

        .fill.warning {{ background: {COLORS['warning']}; }}
        .fill.critical {{ background: {COLORS['critical']}; }}

        .divider {{
            border-top: 1px solid {COLORS['border']};
            margin: 15px 0;
        }}

        .nav {{
            margin-bottom: 20px;
        }}

        .nav a {{
            color: {COLORS['primary']};
            text-decoration: none;
            margin-right: 20px;
        }}

        .nav a:hover {{
            text-decoration: underline;
            color: {COLORS['secondary']};
        }}

        .timestamp {{
            color: {COLORS['secondary']};
            font-size: 11px;
            margin-top: 20px;
            border-top: 1px solid {COLORS['border']};
            padding-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="console">
        <div class="nav">
            <a href="{tailscale_url}/console">STATS</a>
            <a href="{tailscale_url}/chatbot">CHAT</a>
            <a href="{tailscale_url}/">HOME</a>
        </div>

        <div class="header">
            <div class="title">
   [•][•]
    \\_/
   ·███·
  ·█████·
   ·███·

[PROJECT SUNNY SYSTEM MONITOR]
            </div>
        </div>

        <div class="status">
            <div class="stat-line">
                <span class="label">HOSTNAME:</span>
                <span class="value" id="hostname">connecting...</span>
            </div>
            <div class="stat-line">
                <span class="label">TAILSCALE IP:</span>
                <span class="value" id="tailscale-ip">connecting...</span>
            </div>
            <div class="stat-line">
                <span class="label">STATUS:</span>
                <span class="value" id="status">ONLINE</span>
            </div>
            <div class="stat-line">
                <span class="label">NETWORK:</span>
                <span class="value"><a href="{tailscale_url}/chatbot" style="color: {COLORS['primary']}; text-decoration: none;">{tailscale_url}/chatbot</a></span>
            </div>
        </div>

        <div class="divider"></div>

        <div class="status">
            <div class="stat-line">
                <span class="label">CPU USAGE:</span>
                <span class="value" id="cpu">-</span>
                <span class="bar"><span class="fill" id="cpu-bar" style="width: 0%"></span></span>
            </div>
            <div class="stat-line">
                <span class="label">RAM USAGE:</span>
                <span class="value" id="ram">-</span>
                <span class="bar"><span class="fill" id="ram-bar" style="width: 0%"></span></span>
            </div>
            <div class="stat-line">
                <span class="label">DISK USAGE:</span>
                <span class="value" id="disk">-</span>
                <span class="bar"><span class="fill" id="disk-bar" style="width: 0%"></span></span>
            </div>
        </div>

        <div class="divider"></div>

        <div class="status">
            <div class="stat-line">
                <span class="label">CPU TEMP:</span>
                <span class="value" id="temp">-</span>
            </div>
            <div class="stat-line">
                <span class="label">NETWORK RX:</span>
                <span class="value" id="net-rx">-</span>
            </div>
            <div class="stat-line">
                <span class="label">NETWORK TX:</span>
                <span class="value" id="net-tx">-</span>
            </div>
        </div>

        <div class="timestamp">
            Last updated: <span id="timestamp">-</span>
        </div>
    </div>

    <script>
        let lastNetStats = null;

        async function updateStats() {{
            try {{
                const response = await fetch('/console/api/stats');

                if (!response.ok) {{
                    throw new Error('HTTP ' + response.status);
                }}

                const data = await response.json();

                if (data.error) {{
                    console.error('API error:', data.error);
                    return;
                }}

                // Hostname
                if (data.hostname) {{
                    document.getElementById('hostname').textContent = data.hostname;
                }}

                // Tailscale IP
                if (data.tailscale_ip) {{
                    document.getElementById('tailscale-ip').textContent = data.tailscale_ip;
                }} else {{
                    document.getElementById('tailscale-ip').textContent = 'N/A';
                }}

                // CPU
                if (typeof data.cpu === 'number') {{
                    const cpu = data.cpu;
                    document.getElementById('cpu').textContent = cpu.toFixed(1) + '%';
                    const cpuBar = document.getElementById('cpu-bar');
                    cpuBar.style.width = cpu + '%';
                    cpuBar.className = 'fill' + (cpu > 90 ? ' critical' : cpu > 70 ? ' warning' : '');
                }}

                // RAM
                if (typeof data.ram === 'number') {{
                    const ram = data.ram;
                    document.getElementById('ram').textContent = ram.toFixed(1) + '%';
                    const ramBar = document.getElementById('ram-bar');
                    ramBar.style.width = ram + '%';
                    ramBar.className = 'fill' + (ram > 90 ? ' critical' : ram > 70 ? ' warning' : '');
                }}

                // Disk
                if (typeof data.disk === 'number') {{
                    const disk = data.disk;
                    document.getElementById('disk').textContent = disk.toFixed(1) + '%';
                    const diskBar = document.getElementById('disk-bar');
                    diskBar.style.width = disk + '%';
                    diskBar.className = 'fill' + (disk > 90 ? ' critical' : disk > 70 ? ' warning' : '');
                }}

                // Temperature
                if (data.temp) {{
                    document.getElementById('temp').textContent = data.temp.toFixed(1) + ' C';
                }} else {{
                    document.getElementById('temp').textContent = 'N/A';
                }}

                // Network
                if (typeof data.net_rx === 'number' && typeof data.net_tx === 'number') {{
                    if (lastNetStats) {{
                        const rxSpeed = ((data.net_rx - lastNetStats.rx) / 1024 / 1024).toFixed(2);
                        const txSpeed = ((data.net_tx - lastNetStats.tx) / 1024 / 1024).toFixed(2);
                        document.getElementById('net-rx').textContent = rxSpeed + ' MB/s';
                        document.getElementById('net-tx').textContent = txSpeed + ' MB/s';
                    }} else {{
                        document.getElementById('net-rx').textContent = 'Measuring...';
                        document.getElementById('net-tx').textContent = 'Measuring...';
                    }}
                    lastNetStats = {{ rx: data.net_rx, tx: data.net_tx }};
                }}

                // Timestamp
                document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();

            }} catch (error) {{
                console.error('Stats error:', error);
            }}
        }}

        // Initial load and refresh
        window.addEventListener('load', () => {{
            updateStats();
            setInterval(updateStats, 2000);
        }});
    </script>
</body>
</html>
        """
        return HTMLResponse(content=html)

    @router.get("/api/stats")
    async def get_stats():
        """Get system statistics."""
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            # Temperature (may not work on all systems)
            temp = None
            try:
                temps = psutil.sensors_temperatures()
                if 'coretemp' in temps:
                    temp = temps['coretemp'][0].current
                elif 'acpitz' in temps:
                    temp = temps['acpitz'][0].current
            except Exception as e:
                logger.debug(f"Temp error: {e}")

            # Network stats
            net = psutil.net_io_counters()

            return {
                'hostname': socket.gethostname(),
                'tailscale_ip': get_tailscale_ip(),
                'cpu': cpu,
                'ram': ram,
                'disk': disk,
                'temp': temp,
                'net_rx': net.bytes_recv,
                'net_tx': net.bytes_sent,
            }
        except Exception as e:
            logger.error(f"Stats API error: {e}", exc_info=True)
            return {'error': str(e)}, 500

    return router
