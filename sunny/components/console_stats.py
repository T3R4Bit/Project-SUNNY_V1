"""Console-style system stats API and UI."""

import psutil
import logging
import subprocess
import socket
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import datetime

logger = logging.getLogger(__name__)


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
        localhost_url = "http://127.0.0.1:5000"

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SUNNY Console</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', monospace;
            background: #000;
            color: #0f0;
            padding: 20px;
            min-height: 100vh;
        }

        .console {
            background: #000;
            border: 2px solid #0f0;
            padding: 15px;
            font-size: 13px;
            line-height: 1.6;
            max-width: 1000px;
            margin: 0 auto;
        }

        .header {
            border-bottom: 1px solid #0f0;
            margin-bottom: 15px;
            padding-bottom: 10px;
        }

        .title {
            font-weight: bold;
            color: #0f0;
        }

        .status {
            margin-bottom: 20px;
        }

        .stat-line {
            margin: 8px 0;
        }

        .label {
            display: inline-block;
            width: 180px;
            color: #0f0;
        }

        .value {
            color: #0f0;
        }

        .bar {
            display: inline-block;
            width: 100px;
            height: 12px;
            background: #111;
            border: 1px solid #0f0;
            margin: 0 5px;
            vertical-align: middle;
        }

        .fill {
            height: 100%;
            background: #0f0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 9px;
            color: #000;
        }

        .warning { color: #ff0; }
        .critical { color: #f00; }

        .divider {
            border-top: 1px solid #0f0;
            margin: 15px 0;
        }

        .nav {
            margin-bottom: 20px;
        }

        .nav a {
            color: #0f0;
            text-decoration: none;
            margin-right: 20px;
        }

        .nav a:hover {
            text-decoration: underline;
        }

        .timestamp {
            color: #0f0;
            font-size: 11px;
            margin-top: 20px;
            border-top: 1px solid #0f0;
            padding-top: 10px;
        }
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
            <span class="title">[PROJECT SUNNY SYSTEM MONITOR]</span>
        </div>

        <div class="status">
            <div class="stat-line">
                <span class="label">HOSTNAME:</span>
                <span class="value" id="hostname">-</span>
            </div>
            <div class="stat-line">
                <span class="label">TAILSCALE IP:</span>
                <span class="value" id="tailscale-ip">{tailscale_ip or 'N/A'}</span>
            </div>
            <div class="stat-line">
                <span class="label">STATUS:</span>
                <span class="value" id="status">ONLINE</span>
            </div>
            <div class="stat-line">
                <span class="label">NETWORK:</span>
                <span class="value"><a href="{tailscale_url}/console" style="color: #0f0; text-decoration: none;">{tailscale_url}</a></span>
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

        <div class="divider"></div>

        <div class="status" id="processes">
            <div class="stat-line">
                <span class="label">TOP PROCESSES:</span>
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
                const data = await response.json();

                // Basic info
                document.getElementById('hostname').textContent = data.hostname;

                // CPU
                const cpuPercent = data.cpu;
                document.getElementById('cpu').textContent = cpuPercent.toFixed(1) + '%';
                document.getElementById('cpu-bar').style.width = cpuPercent + '%';
                document.getElementById('cpu-bar').classList.toggle('critical', cpuPercent > 90);
                document.getElementById('cpu-bar').classList.toggle('warning', cpuPercent > 70);

                // RAM
                const ramPercent = data.ram;
                document.getElementById('ram').textContent = ramPercent.toFixed(1) + '%';
                document.getElementById('ram-bar').style.width = ramPercent + '%';
                document.getElementById('ram-bar').classList.toggle('critical', ramPercent > 90);
                document.getElementById('ram-bar').classList.toggle('warning', ramPercent > 70);

                // Disk
                const diskPercent = data.disk;
                document.getElementById('disk').textContent = diskPercent.toFixed(1) + '%';
                document.getElementById('disk-bar').style.width = diskPercent + '%';
                document.getElementById('disk-bar').classList.toggle('critical', diskPercent > 90);
                document.getElementById('disk-bar').classList.toggle('warning', diskPercent > 70);

                // Temp
                if (data.temp) {{
                    const tempClass = data.temp > 80 ? 'critical' : data.temp > 60 ? 'warning' : '';
                    document.getElementById('temp').innerHTML =
                        '<span class="' + tempClass + '">' + data.temp.toFixed(1) + '°C</span>';
                }} else {{
                    document.getElementById('temp').textContent = 'N/A';
                }}

                // Network
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

                // Top processes
                const procDiv = document.getElementById('processes');
                procDiv.innerHTML = '<div class="stat-line"><span class="label">TOP PROCESSES:</span></div>';
                data.processes.slice(0, 5).forEach(p => {{
                    const line = document.createElement('div');
                    line.className = 'stat-line';
                    line.textContent = '  ' + p.name.padEnd(30) + p.cpu.toFixed(1).padStart(6) + '% CPU  ' +
                                     p.ram.toFixed(1).padStart(6) + '% RAM';
                    procDiv.appendChild(line);
                }});

                // Timestamp
                document.getElementById('timestamp').textContent =
                    new Date().toLocaleTimeString();

            }} catch (error) {{
                console.error('Error fetching stats:', error);
            }}
        }}

        // Update every 2 seconds
        updateStats();
        setInterval(updateStats, 2000);
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
                temp = psutil.sensors_temperatures().get('coretemp', [{}])[0].current
            except:
                pass

            # Network stats
            net = psutil.net_io_counters()

            # Top processes by CPU
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append({
                        'name': proc.info['name'][:25],
                        'cpu': proc.info['cpu_percent'] or 0,
                        'ram': proc.info['memory_percent'] or 0,
                    })
                except psutil.NoSuchProcess:
                    pass

            processes.sort(key=lambda x: x['cpu'], reverse=True)

            return {
                'hostname': __import__('socket').gethostname(),
                'tailscale_ip': get_tailscale_ip(),
                'cpu': cpu,
                'ram': ram,
                'disk': disk,
                'temp': temp,
                'net_rx': net.bytes_recv,
                'net_tx': net.bytes_sent,
                'processes': processes[:10],
            }
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {'error': str(e)}

    return router
