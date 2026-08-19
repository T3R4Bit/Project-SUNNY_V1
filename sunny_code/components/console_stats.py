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
        """Serve the system status dashboard."""
        tailscale_ip = get_tailscale_ip()
        tailscale_url = f"http://{tailscale_ip}:5000" if tailscale_ip else "http://127.0.0.1:5000"

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%98%80%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <title>SUNNY Console</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        :root {{
            --bg: #0a0e27;
            --panel: #0d1330;
            --elevated: #121a38;
            --cyan: #00d4ff;
            --green: #00ff88;
            --pink: #ff4d7e;
            --warning: #ffb81c;
            --critical: #ff4757;
            --text: #e8f6ff;
            --dim: #6b83a8;
            --border: rgba(0, 212, 255, 0.28);
        }}

        html, body {{ height: 100%; }}

        body {{
            font-family: ui-monospace, 'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace;
            background: radial-gradient(circle at 50% -10%, #16204a 0%, var(--bg) 45%, #05070f 100%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px 16px;
        }}

        .app {{
            width: 100%;
            max-width: 760px;
            background: linear-gradient(180deg, var(--panel) 0%, var(--bg) 100%);
            border: 1px solid var(--border);
            border-radius: 20px;
            overflow: hidden;
            box-shadow:
                0 24px 60px -24px rgba(0, 0, 0, 0.7),
                0 0 50px -18px rgba(0, 212, 255, 0.25);
        }}

        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 16px 20px;
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.14), rgba(0, 255, 136, 0.06));
            border-bottom: 1px solid var(--border);
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }}

        .sun-badge {{
            flex-shrink: 0;
            width: 38px;
            height: 38px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            background: radial-gradient(circle at 35% 30%, #fff6d8, var(--green) 55%, var(--cyan) 100%);
            box-shadow: 0 0 18px rgba(0, 255, 136, 0.45);
        }}

        .brand-text h1 {{
            font-size: 16px;
            letter-spacing: 3px;
            font-weight: 800;
            background: linear-gradient(90deg, var(--cyan), var(--green));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }}

        .brand-text p {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--dim);
            margin-top: 2px;
        }}

        .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 6px var(--green);
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}

        .nav-link {{
            flex-shrink: 0;
            font-size: 10.5px;
            letter-spacing: 1.5px;
            color: var(--cyan);
            text-decoration: none;
            border: 1px solid var(--border);
            padding: 7px 12px;
            border-radius: 20px;
            transition: all 0.2s;
        }}

        .nav-link:hover {{
            background: rgba(0, 212, 255, 0.12);
            box-shadow: 0 0 12px rgba(0, 212, 255, 0.3);
        }}

        .content {{
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 18px;
        }}

        .section-label {{
            font-size: 10.5px;
            letter-spacing: 2px;
            color: var(--dim);
            margin-bottom: 10px;
        }}

        .card {{
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 14px 16px;
        }}

        .kv-grid {{
            display: grid;
            grid-template-columns: auto 1fr;
            row-gap: 10px;
            column-gap: 16px;
            font-size: 13px;
        }}

        .kv-grid dt {{
            color: var(--dim);
            font-size: 11px;
            letter-spacing: 0.5px;
            align-self: center;
        }}

        .kv-grid dd {{
            color: var(--text);
            font-weight: 600;
            overflow-wrap: anywhere;
        }}

        .kv-grid a {{
            color: var(--cyan);
            text-decoration: none;
        }}

        .kv-grid a:hover {{
            text-decoration: underline;
        }}

        .metrics {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}

        .metric-row {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .metric-label {{
            width: 60px;
            flex-shrink: 0;
            font-size: 11px;
            letter-spacing: 0.5px;
            color: var(--dim);
        }}

        .metric-bar {{
            flex: 1;
            height: 10px;
            border-radius: 6px;
            background: #0a0e27;
            border: 1px solid var(--border);
            overflow: hidden;
        }}

        .metric-fill {{
            height: 100%;
            border-radius: 6px;
            background: linear-gradient(90deg, var(--cyan), var(--green));
            width: 0%;
            transition: width 0.4s ease;
        }}

        .metric-fill.warning {{ background: linear-gradient(90deg, var(--warning), #ff8a3d); }}
        .metric-fill.critical {{ background: linear-gradient(90deg, var(--critical), #ff2d55); }}

        .metric-value {{
            width: 52px;
            flex-shrink: 0;
            text-align: right;
            font-size: 12.5px;
            font-weight: 700;
            color: var(--text);
        }}

        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }}

        .stat-tile {{
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
            text-align: center;
        }}

        .stat-tile .label {{
            font-size: 10px;
            letter-spacing: 0.5px;
            color: var(--dim);
            margin-bottom: 4px;
        }}

        .stat-tile .value {{
            font-size: 15px;
            font-weight: 700;
            color: var(--green);
        }}

        .footer {{
            font-size: 10.5px;
            color: var(--dim);
            text-align: center;
            padding-top: 4px;
        }}

        @media (max-width: 640px) {{
            body {{ padding: 0; }}
            .app {{ max-width: 100%; border-radius: 0; border: none; }}
            .stat-grid {{ grid-template-columns: 1fr 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="app">
        <div class="header">
            <div class="brand">
                <div class="sun-badge">&#9728;&#65039;</div>
                <div class="brand-text">
                    <h1>SUNNY</h1>
                    <p><span class="status-dot"></span>Console</p>
                </div>
            </div>
            <a class="nav-link" href="{tailscale_url}/chatbot">CHAT</a>
        </div>

        <div class="content">
            <div>
                <div class="section-label">CONNECTION</div>
                <div class="card">
                    <dl class="kv-grid">
                        <dt>HOSTNAME</dt><dd id="hostname">connecting&hellip;</dd>
                        <dt>TAILSCALE IP</dt><dd id="tailscale-ip">connecting&hellip;</dd>
                        <dt>STATUS</dt><dd id="status">ONLINE</dd>
                        <dt>CHATBOT</dt><dd><a href="{tailscale_url}/chatbot">{tailscale_url}/chatbot</a></dd>
                    </dl>
                </div>
            </div>

            <div>
                <div class="section-label">GOOGLE</div>
                <div class="card">
                    <dl class="kv-grid">
                        <dt>STATUS</dt><dd id="google-status">checking&hellip;</dd>
                        <dt>ACCOUNT</dt><dd id="google-account">&mdash;</dd>
                        <dt>ACTION</dt><dd id="google-action">&mdash;</dd>
                    </dl>
                </div>
            </div>

            <div>
                <div class="section-label">RESOURCES</div>
                <div class="card">
                    <div class="metrics">
                        <div class="metric-row">
                            <div class="metric-label">CPU</div>
                            <div class="metric-bar"><div class="metric-fill" id="cpu-bar"></div></div>
                            <div class="metric-value" id="cpu">-</div>
                        </div>
                        <div class="metric-row">
                            <div class="metric-label">RAM</div>
                            <div class="metric-bar"><div class="metric-fill" id="ram-bar"></div></div>
                            <div class="metric-value" id="ram">-</div>
                        </div>
                        <div class="metric-row">
                            <div class="metric-label">DISK</div>
                            <div class="metric-bar"><div class="metric-fill" id="disk-bar"></div></div>
                            <div class="metric-value" id="disk">-</div>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <div class="section-label">SYSTEM</div>
                <div class="stat-grid">
                    <div class="stat-tile">
                        <div class="label">TEMP</div>
                        <div class="value" id="temp">-</div>
                    </div>
                    <div class="stat-tile">
                        <div class="label">NET RX</div>
                        <div class="value" id="net-rx">-</div>
                    </div>
                    <div class="stat-tile">
                        <div class="label">NET TX</div>
                        <div class="value" id="net-tx">-</div>
                    </div>
                </div>
            </div>

            <div class="footer">Last updated: <span id="timestamp">-</span> &middot; refreshes every 2s</div>
        </div>
    </div>

    <script>
        let lastNetStats = null;

        function setBarState(barEl, valueEl, value, suffix) {{
            valueEl.textContent = value.toFixed(1) + suffix;
            barEl.style.width = Math.min(value, 100) + '%';
            barEl.className = 'metric-fill' + (value > 90 ? ' critical' : value > 70 ? ' warning' : '');
        }}

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

                if (data.hostname) {{
                    document.getElementById('hostname').textContent = data.hostname;
                }}

                document.getElementById('tailscale-ip').textContent = data.tailscale_ip || 'N/A';

                if (typeof data.cpu === 'number') {{
                    setBarState(document.getElementById('cpu-bar'), document.getElementById('cpu'), data.cpu, '%');
                }}
                if (typeof data.ram === 'number') {{
                    setBarState(document.getElementById('ram-bar'), document.getElementById('ram'), data.ram, '%');
                }}
                if (typeof data.disk === 'number') {{
                    setBarState(document.getElementById('disk-bar'), document.getElementById('disk'), data.disk, '%');
                }}

                document.getElementById('temp').textContent = data.temp ? data.temp.toFixed(1) + ' C' : 'N/A';

                if (typeof data.net_rx === 'number' && typeof data.net_tx === 'number') {{
                    if (lastNetStats) {{
                        const rxSpeed = ((data.net_rx - lastNetStats.rx) / 1024 / 1024).toFixed(2);
                        const txSpeed = ((data.net_tx - lastNetStats.tx) / 1024 / 1024).toFixed(2);
                        document.getElementById('net-rx').textContent = rxSpeed + ' MB/s';
                        document.getElementById('net-tx').textContent = txSpeed + ' MB/s';
                    }} else {{
                        document.getElementById('net-rx').textContent = 'measuring…';
                        document.getElementById('net-tx').textContent = 'measuring…';
                    }}
                    lastNetStats = {{ rx: data.net_rx, tx: data.net_tx }};
                }}

                document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();

            }} catch (error) {{
                console.error('Stats error:', error);
            }}
        }}

        async function disconnectGoogle() {{
            await fetch('/auth/google/disconnect', {{ method: 'POST' }});
            updateGoogleStatus();
        }}

        async function updateGoogleStatus() {{
            try {{
                const response = await fetch('/auth/google/status');
                const data = await response.json();

                const statusEl = document.getElementById('google-status');
                const accountEl = document.getElementById('google-account');
                const actionEl = document.getElementById('google-action');

                if (!data.client_configured) {{
                    statusEl.textContent = 'NOT SET UP';
                    accountEl.textContent = '—';
                    actionEl.innerHTML = 'add GOOGLE_CLIENT_ID/SECRET to .env';
                }} else if (data.connected) {{
                    statusEl.textContent = 'CONNECTED';
                    accountEl.textContent = data.email || 'unknown';
                    actionEl.innerHTML = '<a href="#" onclick="disconnectGoogle(); return false;">Disconnect</a>';
                }} else {{
                    statusEl.textContent = 'NOT CONNECTED';
                    accountEl.textContent = '—';
                    actionEl.innerHTML = '<a href="/auth/google/login">Connect Google Account</a>';
                }}
            }} catch (error) {{
                console.error('Google status error:', error);
            }}
        }}

        window.addEventListener('load', () => {{
            updateStats();
            setInterval(updateStats, 2000);
            updateGoogleStatus();
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
