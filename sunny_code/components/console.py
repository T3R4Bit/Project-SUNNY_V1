"""The console — Sunny's one web surface, rebuilt as a tabbed page: Chat,
Stats, Logs, and OAuth Links. Replaces the old console_stats.py (chat + a
system-stats/OAuth-status sidebar bolted together) and chatbot_ui.py (the
message API and old /chatbot, / redirects) with one file.

Logs tab reads sunny_code.components.trace, which every handle_message()
call (web chat, Discord, Pi companion) feeds -- see trace.py for the log
format and the SSE mechanism. OAuth Links tab is a thin, generic wrapper
around the existing /auth/google/* and /auth/spotify/* routers (unchanged)."""

import asyncio
import json
import logging
import socket
import subprocess

import psutil
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from sunny_code.components import trace
from sunny_code.components.assistant import handle_message
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.calendar_engine import CalendarEngine
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.project_engine import ProjectEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.spotify_engine import SpotifyEngine
from sunny_code.components.tasks_engine import TaskEngine

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


def create_console_router(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    project_engine: ProjectEngine,
    spotify_engine: SpotifyEngine,
    calendar_engine: CalendarEngine,
) -> APIRouter:
    """Create every route for the web console: the page itself, the chat
    message API, live system stats, the trace log feed, and redirects for
    old bookmarks. Takes the same shared engine instances as the Discord bot
    and REST API so a change from any interface shows up everywhere."""
    router = APIRouter()

    @router.get("/")
    async def root():
        """Redirect root to the console."""
        return RedirectResponse(url="/console")

    @router.get("/chatbot")
    async def chatbot_redirect():
        """Old standalone chat page — now part of /console."""
        return RedirectResponse(url="/console")

    @router.post("/api/assistant/message")
    async def assistant_message(
        text: str = Query(..., description="Free-text message from the chatbot"),
        session: str = Query("web-default", description="Per-browser session ID, for follow-up questions"),
    ):
        """Single entry point for the chatbot — routing lives in
        sunny_code.components.assistant so the web chatbot and the Discord
        bot behave identically (and both get traced the same way)."""
        response = await handle_message(
            text, tasks_engine, briefing_engine, list_engine, scheduled_engine,
            project_engine, spotify_engine, calendar_engine, session_id=f"web:{session}"
        )
        return {"response": response}

    @router.get("/api/stats")
    async def get_stats():
        """System statistics for the Stats tab."""
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            temp = None
            try:
                temps = psutil.sensors_temperatures()
                if 'coretemp' in temps:
                    temp = temps['coretemp'][0].current
                elif 'acpitz' in temps:
                    temp = temps['acpitz'][0].current
            except Exception as e:
                logger.debug(f"Temp error: {e}")

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

    @router.get("/api/traces/recent")
    async def traces_recent(limit: int = 200):
        """Backfill for the Logs tab — everything currently on disk, before
        the live stream picks up."""
        return {"traces": trace.recent_traces(limit=limit)}

    @router.get("/api/traces/stream")
    async def traces_stream():
        """Server-Sent Events feed of new traces as they happen. Plain
        stdlib/FastAPI SSE — one-directional (server to browser), so no new
        dependency (websockets) is needed for it."""

        async def event_source():
            queue = trace.subscribe()
            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                trace.unsubscribe(queue)

        return StreamingResponse(event_source(), media_type="text/event-stream")

    @router.get("/console")
    async def console_ui():
        """Serve the tabbed console page."""
        tailscale_ip = get_tailscale_ip()
        tailscale_url = f"http://{tailscale_ip}:5000" if tailscale_ip else "http://127.0.0.1:5000"
        return HTMLResponse(content=_render_page(tailscale_url))

    return router


def _render_page(tailscale_url: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='40' fill='%23ffb703'/%3E%3C/svg%3E">
    <title>SUNNY</title>
    <style>
{_STYLE}
    </style>
</head>
<body>
    <div class="topbar">
        <div class="brand">
            <div class="sun-badge"></div>
            <div class="brand-text">
                <h1>SUNNY</h1>
                <p><span class="status-dot"></span>Online</p>
            </div>
        </div>
        <button class="icon-btn" id="clearBtn" title="Clear chat history" aria-label="Clear chat history"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6M14 11v6"></path><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"></path></svg></button>
    </div>

    <div class="tabbar" id="tabbar">
        <button class="tab active" data-tab="chat">Chat</button>
        <button class="tab" data-tab="stats">Stats</button>
        <button class="tab" data-tab="logs">Logs</button>
        <button class="tab" data-tab="oauth">OAuth Links</button>
    </div>

    <div class="content">
        <section class="panel active" id="panel-chat">
            <div class="chat-card">
                <div class="chips" id="chips">
                    <button class="chip" data-cmd="morning" data-send="1">Morning</button>
                    <button class="chip" data-cmd="evening" data-send="1">Evening</button>
                    <button class="chip" data-cmd="show my tasks" data-send="1">Tasks</button>
                    <button class="chip" data-cmd="add " data-send="0">Add task</button>
                    <button class="chip" data-cmd="setup" data-send="1">Setup</button>
                    <button class="chip" data-cmd="/help" data-send="1">Help</button>
                </div>

                <div class="messages" id="messages"></div>

                <div class="input-bar">
                    <div class="input-shell">
                        <textarea id="input" rows="1" placeholder="Ask me anything..." autocomplete="off"></textarea>
                    </div>
                    <button class="send-btn" id="sendBtn" aria-label="Send message"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg></button>
                </div>
            </div>
        </section>

        <section class="panel" id="panel-stats">
            <div class="stats-grid">
                <div>
                    <div class="section-label">CONNECTION</div>
                    <div class="card">
                        <dl class="kv-grid">
                            <dt>HOSTNAME</dt><dd id="hostname">connecting&hellip;</dd>
                            <dt>TAILSCALE IP</dt><dd id="tailscale-ip">connecting&hellip;</dd>
                            <dt>STATUS</dt><dd id="status">ONLINE</dd>
                            <dt>ACCESS</dt><dd><a href="{tailscale_url}">{tailscale_url}</a></dd>
                        </dl>
                    </div>
                </div>

                <div>
                    <div class="section-label">LOCATION</div>
                    <div class="card">
                        <div class="loc-row">
                            <input class="loc-input" id="location-input" type="text" placeholder="City,State,Country" autocomplete="off">
                            <button class="loc-save" id="location-save">Save</button>
                        </div>
                        <div class="loc-status" id="location-status">Used for weather. Saves instantly, no restart needed.</div>
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
            </div>
            <div class="side-footer">Last updated: <span id="timestamp">-</span> &middot; refreshes every 2s</div>
        </section>

        <section class="panel" id="panel-logs">
            <div class="logs-toolbar">
                <span id="logs-count">0 traces</span>
                <span class="logs-live"><span class="status-dot"></span> live</span>
            </div>
            <div class="logs-table-wrap" id="logs-table-wrap">
                <table class="logs-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Input</th>
                            <th>Routing Decision</th>
                            <th>Path Taken</th>
                            <th>Confidence</th>
                            <th>Result</th>
                            <th>Errors</th>
                        </tr>
                    </thead>
                    <tbody id="logs-body"></tbody>
                </table>
            </div>
        </section>

        <section class="panel" id="panel-oauth">
            <div class="oauth-grid" id="oauth-grid"></div>
        </section>
    </div>

    <script>
{_SCRIPT}
    </script>
</body>
</html>
"""


_STYLE = """
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg: #0b0d12;
            --panel: #0e1015;
            --elevated: #171a21;
            --border: rgba(255, 255, 255, 0.08);
            --border-strong: rgba(255, 255, 255, 0.16);
            --accent: #5b8cff;
            --accent-soft: rgba(91, 140, 255, 0.14);
            --success: #3fb950;
            --warning: #d29922;
            --critical: #f85149;
            --text: #e6e8eb;
            --dim: #8b93a1;
            --dim-2: #5b6472;
            --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
            --font-mono: ui-monospace, "SFMono-Regular", "Cascadia Code", Consolas, "Liberation Mono", monospace;
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: 0.001ms !important;
                animation-iteration-count: 1 !important;
            }
        }

        html, body { height: 100%; }

        body {
            font-family: var(--font-sans);
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 20px;
            background: var(--panel);
            border-bottom: 1px solid var(--border);
            flex-shrink: 0;
        }

        .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }

        .sun-badge {
            flex-shrink: 0;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 15px;
            background: linear-gradient(135deg, #ffb703, #ff7a3d);
        }

        .brand-text h1 {
            font-size: 14px;
            letter-spacing: 0.5px;
            font-weight: 650;
            color: var(--text);
        }

        .brand-text p { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--dim); margin-top: 2px; }

        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--success);
            display: inline-block;
        }

        .icon-btn {
            flex-shrink: 0;
            width: 30px;
            height: 30px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: transparent;
            color: var(--dim);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            transition: background 0.15s, border-color 0.15s, color 0.15s;
        }

        .icon-btn:hover { color: var(--text); border-color: var(--border-strong); background: var(--elevated); }

        .tabbar {
            display: flex;
            gap: 2px;
            padding: 0 20px;
            background: var(--panel);
            border-bottom: 1px solid var(--border);
            flex-shrink: 0;
        }

        .tab {
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            padding: 11px 16px;
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--dim);
            cursor: pointer;
            transition: color 0.15s, border-color 0.15s;
        }

        .tab:hover { color: var(--text); }
        .tab.active { color: var(--text); border-bottom-color: var(--accent); }

        .content { flex: 1; min-height: 0; overflow: hidden; display: flex; background: var(--bg); }

        .panel { display: none; flex: 1; min-width: 0; min-height: 0; padding: 20px; overflow-y: auto; }
        .panel.active { display: flex; flex-direction: column; }

        /* ---- Chat ---- */

        .chat-card {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
            min-height: 0;
            max-width: 820px;
            width: 100%;
            margin: 0 auto;
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
        }

        .chips { display: flex; gap: 8px; flex-wrap: wrap; padding: 14px 18px 0; }

        .chip {
            font-family: inherit;
            font-size: 12px;
            font-weight: 500;
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--elevated);
            color: var(--dim);
            cursor: pointer;
            transition: background 0.15s, color 0.15s, border-color 0.15s;
            white-space: nowrap;
        }

        .chip:hover { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            scroll-behavior: smooth;
            min-height: 0;
        }

        .message { display: flex; gap: 10px; max-width: 88%; }

        .message.user { align-self: flex-end; flex-direction: row-reverse; }
        .message.bot { align-self: flex-start; }

        .avatar {
            flex-shrink: 0;
            width: 26px;
            height: 26px;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 600;
        }

        .message.bot .avatar { background: var(--accent-soft); color: var(--accent); }
        .message.user .avatar { background: var(--elevated); color: var(--text); border: 1px solid var(--border); }

        .bubble-wrap { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
        .message.user .bubble-wrap { align-items: flex-end; }

        .bubble {
            padding: 10px 14px;
            font-size: 13.5px;
            line-height: 1.55;
            white-space: pre-wrap;
            word-break: break-word;
            border-radius: 10px;
        }

        .message.bot .bubble { background: var(--elevated); color: var(--text); border: 1px solid var(--border); }
        .message.user .bubble { background: var(--accent); color: #fff; }

        .meta { font-size: 10.5px; color: var(--dim-2); padding: 0 4px; }

        .input-bar { padding: 14px 16px; background: var(--panel); border-top: 1px solid var(--border); display: flex; align-items: flex-end; gap: 10px; }

        .input-shell {
            flex: 1;
            display: flex;
            align-items: flex-end;
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 6px 6px 6px 14px;
            transition: border-color 0.15s;
        }

        .input-shell:focus-within { border-color: var(--accent); }

        #input {
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            resize: none;
            color: var(--text);
            font-family: inherit;
            font-size: 13.5px;
            line-height: 1.4;
            max-height: 100px;
            padding: 8px 0;
        }

        #input::placeholder { color: var(--dim-2); }

        .send-btn {
            flex-shrink: 0;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            border: none;
            background: var(--accent);
            color: #fff;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            transition: background 0.15s, opacity 0.15s;
        }

        .send-btn:hover:not(:disabled) { background: #4a7aef; }
        .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .typing-dots { display: inline-flex; gap: 4px; padding: 4px 2px; }
        .typing-dots span { width: 5px; height: 5px; border-radius: 50%; background: var(--dim); animation: typing 1.4s infinite; }
        .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
        .typing-dots span:nth-child(3) { animation-delay: 0.4s; }

        @keyframes typing { 0%, 60%, 100% { transform: translateY(0); opacity: 0.5; } 30% { transform: translateY(-5px); opacity: 1; } }

        .messages::-webkit-scrollbar, .panel::-webkit-scrollbar, .logs-table-wrap::-webkit-scrollbar { width: 8px; }
        .messages::-webkit-scrollbar-track, .panel::-webkit-scrollbar-track, .logs-table-wrap::-webkit-scrollbar-track { background: transparent; }
        .messages::-webkit-scrollbar-thumb, .panel::-webkit-scrollbar-thumb, .logs-table-wrap::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
        .messages::-webkit-scrollbar-thumb:hover, .panel::-webkit-scrollbar-thumb:hover, .logs-table-wrap::-webkit-scrollbar-thumb:hover { background: var(--dim-2); }

        /* ---- Stats ---- */

        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; max-width: 1000px; width: 100%; margin: 0 auto; }

        .section-label { font-size: 11px; font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase; color: var(--dim); margin-bottom: 8px; }

        .card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px 16px;
            transition: border-color 0.15s;
        }

        .card:hover { border-color: var(--border-strong); }

        .kv-grid { display: grid; grid-template-columns: auto 1fr; row-gap: 10px; column-gap: 16px; font-size: 13px; }
        .kv-grid dt { color: var(--dim); font-size: 11.5px; align-self: center; }
        .kv-grid dd { color: var(--text); font-weight: 500; overflow-wrap: anywhere; }
        .kv-grid a { color: var(--accent); text-decoration: none; }
        .kv-grid a:hover { text-decoration: underline; }

        .loc-row { display: flex; gap: 6px; }

        .loc-input {
            flex: 1;
            min-width: 0;
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 7px 10px;
            color: var(--text);
            font-family: inherit;
            font-size: 12.5px;
            outline: none;
            transition: border-color 0.15s;
        }

        .loc-input:focus { border-color: var(--accent); }

        .loc-save {
            flex-shrink: 0;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--accent-soft);
            color: var(--accent);
            font-family: inherit;
            font-weight: 500;
            font-size: 12px;
            padding: 7px 12px;
            cursor: pointer;
            transition: background 0.15s;
        }

        .loc-save:hover { background: rgba(91, 140, 255, 0.24); }
        .loc-status { font-size: 11px; color: var(--dim); margin-top: 8px; }

        .metrics { display: flex; flex-direction: column; gap: 14px; }
        .metric-row { display: flex; align-items: center; gap: 12px; }
        .metric-label { width: 40px; flex-shrink: 0; font-size: 11.5px; color: var(--dim); }

        .metric-bar { flex: 1; height: 8px; border-radius: 4px; background: var(--elevated); overflow: hidden; }

        .metric-fill { height: 100%; border-radius: 4px; background: var(--accent); width: 0%; transition: width 0.4s ease; }
        .metric-fill.warning { background: var(--warning); }
        .metric-fill.critical { background: var(--critical); }

        .metric-value { width: 48px; flex-shrink: 0; text-align: right; font-size: 12.5px; font-weight: 600; color: var(--text); }

        .stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }

        .stat-tile { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; text-align: center; }
        .stat-tile .label { font-size: 10.5px; color: var(--dim); margin-bottom: 4px; }
        .stat-tile .value { font-size: 15px; font-weight: 600; color: var(--text); }

        .side-footer { font-size: 11px; color: var(--dim-2); text-align: center; padding: 12px 0 4px; max-width: 1000px; margin: 0 auto; width: 100%; }

        /* ---- Logs ---- */

        .logs-toolbar { display: flex; align-items: center; justify-content: space-between; padding-bottom: 10px; font-size: 12px; color: var(--dim); flex-shrink: 0; }
        .logs-live { display: flex; align-items: center; gap: 6px; color: var(--success); }

        .logs-table-wrap {
            flex: 1;
            min-height: 0;
            overflow: auto;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--panel);
        }

        .logs-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: var(--font-mono); }
        .logs-table thead th {
            position: sticky;
            top: 0;
            background: var(--panel);
            text-align: left;
            padding: 9px 12px;
            font-size: 10.5px;
            font-family: var(--font-sans);
            font-weight: 600;
            letter-spacing: 0.3px;
            text-transform: uppercase;
            color: var(--dim);
            border-bottom: 1px solid var(--border);
            z-index: 1;
        }

        .logs-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .logs-table tr.trace-row { cursor: pointer; border-left: 2px solid transparent; transition: background 0.15s; }
        .logs-table tr.trace-row:hover { background: var(--elevated); }
        .logs-table tr.trace-row.ok { border-left-color: var(--success); }
        .logs-table tr.trace-row.err { border-left-color: var(--critical); }
        .logs-table tr.trace-row.ok td.result { color: var(--success); }
        .logs-table tr.trace-row.err td.result, .logs-table tr.trace-row.err td.err { color: var(--critical); }

        .logs-table tr.trace-detail td { white-space: pre-wrap; word-break: break-word; background: var(--bg); font-size: 11.5px; color: var(--dim); }
        .logs-table tr.trace-detail.hidden { display: none; }
        .logs-table tr.trace-detail dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; }
        .logs-table tr.trace-detail dt { color: var(--accent); font-family: var(--font-sans); }
        .logs-table tr.trace-detail dd { color: var(--text); }
        .confidence-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 10.5px; font-family: var(--font-sans); font-weight: 500; border: 1px solid currentColor; }
        .confidence-badge.conf-exact { color: var(--success); }
        .confidence-badge.conf-heuristic { color: var(--accent); }
        .confidence-badge.conf-fallback { color: var(--warning); }
        .confidence-badge.conf-none { color: var(--dim); }

        /* ---- OAuth Links ---- */

        .oauth-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; max-width: 1000px; width: 100%; margin: 0 auto; }

        @media (max-width: 900px) {
            .stat-grid { grid-template-columns: 1fr 1fr; }
            .tabbar { overflow-x: auto; }
        }
"""


_SCRIPT = """
        // ---------- Tabs ----------
        const TAB_KEY = 'sunny-console-tab';
        const tabbar = document.getElementById('tabbar');
        const panels = document.querySelectorAll('.panel');
        const tabs = document.querySelectorAll('.tab');

        function activateTab(name) {
            tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));
            panels.forEach(p => p.classList.toggle('active', p.id === 'panel-' + name));
            try { localStorage.setItem(TAB_KEY, name); } catch (e) { /* no persistence */ }
        }

        tabbar.addEventListener('click', (e) => {
            const btn = e.target.closest('.tab');
            if (!btn) return;
            activateTab(btn.dataset.tab);
        });

        (function restoreTab() {
            let saved = null;
            try { saved = localStorage.getItem(TAB_KEY); } catch (e) { /* ignore */ }
            if (saved && document.getElementById('panel-' + saved)) activateTab(saved);
        })();

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text == null ? '' : String(text);
            return div.innerHTML;
        }

        // ---------- Chat ----------
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const chips = document.getElementById('chips');
        const clearBtn = document.getElementById('clearBtn');

        const STORAGE_KEY = 'sunny-chat-history';
        const SESSION_KEY = 'sunny-chat-session';
        const MAX_HISTORY = 200;

        function getSessionId() {
            let id = localStorage.getItem(SESSION_KEY);
            if (!id) {
                id = 'sess-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
                try { localStorage.setItem(SESSION_KEY, id); } catch (e) { /* no persistence */ }
            }
            return id;
        }

        const sessionId = getSessionId();

        function loadHistory() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                return raw ? JSON.parse(raw) : [];
            } catch (e) { return []; }
        }

        function saveHistory() {
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-MAX_HISTORY))); }
            catch (e) { /* storage full/unavailable — chat still works this session */ }
        }

        let history = loadHistory();

        function autoGrow() {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 100) + 'px';
        }
        input.addEventListener('input', autoGrow);

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        sendBtn.addEventListener('click', sendMessage);

        chips.addEventListener('click', (e) => {
            const chip = e.target.closest('.chip');
            if (!chip) return;
            const cmd = chip.dataset.cmd;
            if (chip.dataset.send === '1') {
                input.value = cmd;
                sendMessage();
            } else {
                input.value = cmd;
                autoGrow();
                input.focus();
            }
        });

        function timestamp() {
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        async function sendMessage() {
            const text = input.value.trim();
            if (!text) return;

            input.value = '';
            autoGrow();
            addMessage(text, 'user');

            input.disabled = true;
            sendBtn.disabled = true;

            const typingMsg = document.createElement('div');
            typingMsg.className = 'message bot';
            typingMsg.innerHTML = '<div class="avatar">S</div><div class="bubble-wrap"><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div></div>';
            messagesDiv.appendChild(typingMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            try {
                const url = new URL('/api/assistant/message', window.location.origin);
                url.searchParams.append('text', text);
                url.searchParams.append('session', sessionId);

                const response = await fetch(url, { method: 'POST' });
                const data = await response.json();

                messagesDiv.removeChild(typingMsg);

                const botText = data.response || JSON.stringify(data, null, 2);
                addMessage(botText, 'bot');
            } catch (error) {
                messagesDiv.removeChild(typingMsg);
                addMessage('ERROR: ' + error.message, 'bot');
            } finally {
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }
        }

        function renderMessage(text, sender, time) {
            const msg = document.createElement('div');
            msg.className = 'message ' + sender;
            const avatar = sender === 'user' ? 'U' : 'S';
            msg.innerHTML =
                '<div class="avatar">' + avatar + '</div>' +
                '<div class="bubble-wrap">' +
                    '<div class="bubble">' + escapeHtml(text) + '</div>' +
                    '<div class="meta">' + time + '</div>' +
                '</div>';
            messagesDiv.appendChild(msg);
        }

        function addMessage(text, sender) {
            const time = timestamp();
            renderMessage(text, sender, time);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            history.push({ text, sender, time });
            saveHistory();
        }

        clearBtn.addEventListener('click', () => {
            if (!confirm('Clear chat history? This only clears it on this device.')) return;
            history = [];
            saveHistory();
            messagesDiv.innerHTML = '';
            addMessage('Chat cleared. Try a shortcut below or ask me anything.', 'bot');
        });

        window.addEventListener('load', () => {
            if (history.length > 0) {
                history.forEach((m) => renderMessage(m.text, m.sender, m.time));
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            } else {
                addMessage('Welcome to Project SUNNY. Try a shortcut below or ask me anything.', 'bot');
            }
            input.focus();
        });

        // ---------- Stats ----------
        let lastNetStats = null;

        function setBarState(barEl, valueEl, value, suffix) {
            valueEl.textContent = value.toFixed(1) + suffix;
            barEl.style.width = Math.min(value, 100) + '%';
            barEl.className = 'metric-fill' + (value > 90 ? ' critical' : value > 70 ? ' warning' : '');
        }

        async function updateStats() {
            try {
                const response = await fetch('/api/stats');
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const data = await response.json();
                if (data.error) { console.error('API error:', data.error); return; }

                if (data.hostname) document.getElementById('hostname').textContent = data.hostname;
                document.getElementById('tailscale-ip').textContent = data.tailscale_ip || 'N/A';

                if (typeof data.cpu === 'number') setBarState(document.getElementById('cpu-bar'), document.getElementById('cpu'), data.cpu, '%');
                if (typeof data.ram === 'number') setBarState(document.getElementById('ram-bar'), document.getElementById('ram'), data.ram, '%');
                if (typeof data.disk === 'number') setBarState(document.getElementById('disk-bar'), document.getElementById('disk'), data.disk, '%');

                document.getElementById('temp').textContent = data.temp ? data.temp.toFixed(1) + ' C' : 'N/A';

                if (typeof data.net_rx === 'number' && typeof data.net_tx === 'number') {
                    if (lastNetStats) {
                        const rxSpeed = ((data.net_rx - lastNetStats.rx) / 1024 / 1024).toFixed(2);
                        const txSpeed = ((data.net_tx - lastNetStats.tx) / 1024 / 1024).toFixed(2);
                        document.getElementById('net-rx').textContent = rxSpeed + ' MB/s';
                        document.getElementById('net-tx').textContent = txSpeed + ' MB/s';
                    } else {
                        document.getElementById('net-rx').textContent = 'measuring…';
                        document.getElementById('net-tx').textContent = 'measuring…';
                    }
                    lastNetStats = { rx: data.net_rx, tx: data.net_tx };
                }

                document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();
            } catch (error) {
                console.error('Stats error:', error);
            }
        }

        // ---------- Location (weather) ----------
        async function loadLocation() {
            try {
                const response = await fetch('/api/weather/location');
                const data = await response.json();
                document.getElementById('location-input').value = data.location || '';
            } catch (error) {
                console.error('Location load error:', error);
            }
        }

        async function saveLocation() {
            const input = document.getElementById('location-input');
            const statusEl = document.getElementById('location-status');
            const value = input.value.trim();
            if (!value) {
                statusEl.textContent = 'Enter a location first, e.g. "Detroit,MI,US".';
                return;
            }
            try {
                const response = await fetch('/api/weather/location', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ location: value }),
                });
                const data = await response.json();
                statusEl.textContent = data.status === 'saved'
                    ? 'Saved — weather updates immediately, no restart needed.'
                    : (data.message || 'Error saving location.');
            } catch (error) {
                statusEl.textContent = 'Error saving location — check the console log.';
                console.error('Location save error:', error);
            }
        }

        document.getElementById('location-save').addEventListener('click', saveLocation);
        document.getElementById('location-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); saveLocation(); }
        });

        window.addEventListener('load', () => {
            updateStats();
            setInterval(updateStats, 2000);
            loadLocation();
        });

        // ---------- Logs ----------
        const logsBody = document.getElementById('logs-body');
        const logsWrap = document.getElementById('logs-table-wrap');
        const logsCount = document.getElementById('logs-count');
        const MAX_ROWS = 200;
        let traceSeq = 0;

        function fmtTime(iso) {
            try { return new Date(iso).toLocaleTimeString(); } catch (e) { return iso; }
        }

        function truncate(text, n) {
            if (text == null) return '';
            const s = String(text);
            return s.length > n ? s.slice(0, n - 1) + '…' : s;
        }

        function addTraceRow(ev) {
            const id = 'trace-' + (traceSeq++);
            const ok = !ev.error;
            const nearBottom = logsWrap.scrollHeight - logsWrap.scrollTop - logsWrap.clientHeight < 40;

            const row = document.createElement('tr');
            row.className = 'trace-row ' + (ok ? 'ok' : 'err');
            row.dataset.detail = id;
            row.innerHTML =
                '<td>' + escapeHtml(fmtTime(ev.timestamp)) + '</td>' +
                '<td>' + escapeHtml(truncate(ev.input, 60)) + '</td>' +
                '<td>' + escapeHtml(ev.route || 'unclassified') + '</td>' +
                '<td>' + escapeHtml(ev.path || '\\u2014') + '</td>' +
                '<td><span class="confidence-badge conf-' + escapeHtml(ev.confidence || 'none') + '">' +
                    escapeHtml(ev.confidence || '\\u2014') + '</span></td>' +
                '<td class="result">' + escapeHtml(truncate(ev.result, 60)) + '</td>' +
                '<td class="err">' + escapeHtml(truncate(ev.error, 60)) + '</td>';

            const detail = document.createElement('tr');
            detail.className = 'trace-detail hidden';
            detail.id = id;
            const detailCell = document.createElement('td');
            detailCell.colSpan = 7;
            detailCell.innerHTML =
                '<dl>' +
                '<dt>source</dt><dd>' + escapeHtml(ev.source) + '</dd>' +
                '<dt>session</dt><dd>' + escapeHtml(ev.session_id) + '</dd>' +
                '<dt>function called</dt><dd>' + escapeHtml(ev.function || '\\u2014') + '</dd>' +
                '<dt>confidence</dt><dd>' + escapeHtml(ev.confidence || '\\u2014') + '</dd>' +
                '<dt>duration</dt><dd>' + escapeHtml(ev.duration_ms) + ' ms</dd>' +
                '<dt>input</dt><dd>' + escapeHtml(ev.input) + '</dd>' +
                '<dt>result</dt><dd>' + escapeHtml(ev.result || '\\u2014') + '</dd>' +
                '<dt>error</dt><dd>' + escapeHtml(ev.error || '\\u2014') + '</dd>' +
                ((ev.notes && ev.notes.length)
                    ? '<dt>guard notes</dt><dd>' + ev.notes.map(escapeHtml).join('<br>') + '</dd>'
                    : '') +
                '</dl>';
            detail.appendChild(detailCell);

            row.addEventListener('click', () => detail.classList.toggle('hidden'));

            logsBody.appendChild(row);
            logsBody.appendChild(detail);

            while (logsBody.children.length > MAX_ROWS * 2) {
                logsBody.removeChild(logsBody.firstChild);
                logsBody.removeChild(logsBody.firstChild);
            }

            logsCount.textContent = logsBody.children.length / 2 + ' traces';
            if (nearBottom) logsWrap.scrollTop = logsWrap.scrollHeight;
        }

        async function loadRecentTraces() {
            try {
                const response = await fetch('/api/traces/recent?limit=' + MAX_ROWS);
                const data = await response.json();
                (data.traces || []).forEach(addTraceRow);
                logsWrap.scrollTop = logsWrap.scrollHeight;
            } catch (error) {
                console.error('Trace backfill error:', error);
            }
        }

        function connectTraceStream() {
            const source = new EventSource('/api/traces/stream');
            source.onmessage = (e) => {
                try { addTraceRow(JSON.parse(e.data)); } catch (err) { console.error('Bad trace event:', err); }
            };
            source.onerror = () => {
                // EventSource auto-reconnects; nothing to do here.
            };
        }

        window.addEventListener('load', () => {
            loadRecentTraces().then(connectTraceStream);
        });

        // ---------- OAuth Links ----------
        const OAUTH_PROVIDERS = [
            { name: 'Google', prefix: '/auth/google', note: 'Calendar + Gmail (read-only)' },
            { name: 'Spotify', prefix: '/auth/spotify', note: 'Playback control' },
        ];

        function renderOauthCard(provider) {
            const card = document.createElement('div');
            card.className = 'card';
            card.innerHTML =
                '<div class="section-label">' + escapeHtml(provider.name.toUpperCase()) + '</div>' +
                '<dl class="kv-grid">' +
                '<dt>STATUS</dt><dd class="oauth-status">checking&hellip;</dd>' +
                '<dt>ACCOUNT</dt><dd class="oauth-account">&mdash;</dd>' +
                '<dt>ACTION</dt><dd class="oauth-action">&mdash;</dd>' +
                '</dl>' +
                '<div class="loc-status">' + escapeHtml(provider.note) + '</div>';
            return card;
        }

        async function refreshOauthCard(provider, card) {
            const statusEl = card.querySelector('.oauth-status');
            const accountEl = card.querySelector('.oauth-account');
            const actionEl = card.querySelector('.oauth-action');
            try {
                const response = await fetch(provider.prefix + '/status');
                const data = await response.json();

                if (!data.client_configured) {
                    statusEl.textContent = 'NOT SET UP';
                    accountEl.textContent = '\\u2014';
                    actionEl.textContent = 'add credentials to .env';
                } else if (data.connected) {
                    statusEl.textContent = 'CONNECTED';
                    accountEl.textContent = data.email || data.username || 'unknown';
                    const link = document.createElement('a');
                    link.href = '#';
                    link.textContent = 'Disconnect';
                    link.addEventListener('click', async (e) => {
                        e.preventDefault();
                        await fetch(provider.prefix + '/disconnect', { method: 'POST' });
                        refreshOauthCard(provider, card);
                    });
                    actionEl.innerHTML = '';
                    actionEl.appendChild(link);
                } else {
                    statusEl.textContent = 'NOT CONNECTED';
                    accountEl.textContent = '\\u2014';
                    actionEl.innerHTML = '<a href="' + provider.prefix + '/login">Connect ' + escapeHtml(provider.name) + ' Account</a>';
                }
            } catch (error) {
                console.error(provider.name + ' status error:', error);
            }
        }

        function initOauthTab() {
            const grid = document.getElementById('oauth-grid');
            OAUTH_PROVIDERS.forEach((provider) => {
                const card = renderOauthCard(provider);
                grid.appendChild(card);
                refreshOauthCard(provider, card);
                setInterval(() => refreshOauthCard(provider, card), 30000);
            });
        }

        window.addEventListener('load', initOauthTab);
"""
