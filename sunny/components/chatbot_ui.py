"""Web-based chatbot UI served over Tailscale."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import logging
import asyncio

from sunny.components.briefing import BriefingEngine
from sunny.components.tasks_engine import TaskEngine
from sunny.components.tasks_db import TaskDB
from sunny.config import get_settings

logger = logging.getLogger(__name__)


def create_chatbot_router() -> APIRouter:
    """Create chatbot UI routes."""
    router = APIRouter(prefix="/chatbot")

    # Initialize engines
    settings = get_settings()
    briefing_engine = BriefingEngine()
    tasks_db = TaskDB(settings.project_root / "tasks.db")
    tasks_engine = TaskEngine(tasks_db)

    @router.get("/")
    async def chatbot_ui():
        """Serve the chatbot web interface (console-style)."""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PROJECT SUNNY</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', monospace;
            background: #000;
            color: #0f0;
            padding: 0;
            min-height: 100vh;
            display: flex;
        }

        .sidebar {
            width: 280px;
            background: #000;
            border-right: 2px solid #0f0;
            padding: 15px;
            font-size: 12px;
            line-height: 1.6;
            overflow-y: auto;
            border-bottom: 1px solid #0f0;
        }

        .stat-group {
            margin-bottom: 20px;
            border-bottom: 1px solid #0f0;
            padding-bottom: 15px;
        }

        .stat-group:last-child {
            border-bottom: none;
        }

        .stat-label {
            color: #0f0;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .stat-value {
            color: #0f0;
            margin-left: 10px;
            font-size: 11px;
        }

        .bar {
            display: inline-block;
            width: 80px;
            height: 8px;
            background: #111;
            border: 1px solid #0f0;
            margin-left: 5px;
            vertical-align: middle;
        }

        .bar-fill {
            height: 100%;
            background: #0f0;
        }

        .bar-fill.warning { background: #ff0; }
        .bar-fill.critical { background: #f00; }

        .nav {
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #0f0;
        }

        .nav a {
            display: block;
            color: #0f0;
            text-decoration: none;
            margin: 5px 0;
            font-size: 11px;
        }

        .nav a:hover {
            text-decoration: underline;
        }

        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #000;
            border-left: 2px solid #0f0;
        }

        .header {
            background: #000;
            border-bottom: 2px solid #0f0;
            padding: 15px;
            text-align: left;
        }

        .header h1 {
            color: #0f0;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 3px;
        }

        .header .status {
            font-size: 11px;
            color: #0f0;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            background: #000;
        }

        .message {
            margin-bottom: 10px;
            font-size: 12px;
            line-height: 1.4;
        }

        .message.user {
            color: #0f0;
        }

        .message.user::before {
            content: '> ';
            font-weight: bold;
        }

        .message.bot {
            color: #0f0;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .message.bot::before {
            content: '[ ] ';
            color: #0f0;
        }

        .input-area {
            padding: 15px;
            background: #000;
            border-top: 2px solid #0f0;
            display: flex;
            gap: 5px;
        }

        input {
            flex: 1;
            background: #000;
            color: #0f0;
            border: 1px solid #0f0;
            padding: 8px 10px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            outline: none;
        }

        input:focus {
            outline: 1px solid #0f0;
        }

        input::placeholder {
            color: #0a0;
            opacity: 0.5;
        }

        button {
            padding: 8px 15px;
            background: #000;
            color: #0f0;
            border: 1px solid #0f0;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.1s;
        }

        button:hover {
            background: #0f0;
            color: #000;
        }

        button:active {
            background: #000;
            color: #0f0;
        }

        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: #000;
        }

        ::-webkit-scrollbar-thumb {
            background: #0f0;
            border: 1px solid #0f0;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #0a0;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="nav">
            <a href="/console">STATS</a>
            <a href="/chatbot">CHAT</a>
            <a href="/">HOME</a>
        </div>

        <div class="stat-group">
            <div class="stat-label">SYSTEM</div>
            <div class="stat-value">Hostname: <span id="hostname">-</span></div>
            <div class="stat-value">Tailscale IP: <span id="tailscale-ip">-</span></div>
            <div class="stat-value">Status: <span id="status">ONLINE</span></div>
        </div>

        <div class="stat-group">
            <div class="stat-label">CPU</div>
            <div class="stat-value"><span id="cpu">-</span>%
                <span class="bar"><span class="bar-fill" id="cpu-bar" style="width: 0%"></span></span>
            </div>
        </div>

        <div class="stat-group">
            <div class="stat-label">RAM</div>
            <div class="stat-value"><span id="ram">-</span>%
                <span class="bar"><span class="bar-fill" id="ram-bar" style="width: 0%"></span></span>
            </div>
        </div>

        <div class="stat-group">
            <div class="stat-label">DISK</div>
            <div class="stat-value"><span id="disk">-</span>%
                <span class="bar"><span class="bar-fill" id="disk-bar" style="width: 0%"></span></span>
            </div>
        </div>

        <div class="stat-group">
            <div class="stat-label">NETWORK</div>
            <div class="stat-value">RX: <span id="net-rx">-</span> MB/s</div>
            <div class="stat-value">TX: <span id="net-tx">-</span> MB/s</div>
            <div class="stat-value">TEMP: <span id="temp">-</span></div>
        </div>
    </div>

    <div class="main">
        <div class="header">
            <h1>[PROJECT SUNNY CHAT]</h1>
            <div class="status">Commands: morning | evening | !tasks | !task add "title" | questions</div>
        </div>

        <div class="messages" id="messages"></div>

        <div class="input-area">
            <input
                type="text"
                id="input"
                placeholder="enter command or ask question"
                autocomplete="off"
            />
            <button onclick="sendMessage()">SEND</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('input');
        let lastNetStats = null;

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        async function updateStats() {{
            try {{
                const response = await fetch('/console/api/stats');
                const data = await response.json();

                document.getElementById('hostname').textContent = data.hostname;
                document.getElementById('tailscale-ip').textContent = data.tailscale_ip || 'N/A';

                const cpuPercent = data.cpu;
                document.getElementById('cpu').textContent = cpuPercent.toFixed(1);
                const cpuBar = document.getElementById('cpu-bar');
                cpuBar.style.width = cpuPercent + '%';
                cpuBar.className = 'bar-fill ' + (cpuPercent > 90 ? 'critical' : cpuPercent > 70 ? 'warning' : '');

                const ramPercent = data.ram;
                document.getElementById('ram').textContent = ramPercent.toFixed(1);
                const ramBar = document.getElementById('ram-bar');
                ramBar.style.width = ramPercent + '%';
                ramBar.className = 'bar-fill ' + (ramPercent > 90 ? 'critical' : ramPercent > 70 ? 'warning' : '');

                const diskPercent = data.disk;
                document.getElementById('disk').textContent = diskPercent.toFixed(1);
                const diskBar = document.getElementById('disk-bar');
                diskBar.style.width = diskPercent + '%';
                diskBar.className = 'bar-fill ' + (diskPercent > 90 ? 'critical' : diskPercent > 70 ? 'warning' : '');

                if (data.temp) {{
                    document.getElementById('temp').textContent = data.temp.toFixed(1) + 'C';
                }} else {{
                    document.getElementById('temp').textContent = 'N/A';
                }}

                if (lastNetStats) {{
                    const rxSpeed = ((data.net_rx - lastNetStats.rx) / 1024 / 1024).toFixed(2);
                    const txSpeed = ((data.net_tx - lastNetStats.tx) / 1024 / 1024).toFixed(2);
                    document.getElementById('net-rx').textContent = rxSpeed;
                    document.getElementById('net-tx').textContent = txSpeed;
                }}
                lastNetStats = {{ rx: data.net_rx, tx: data.net_tx }};
            }} catch (e) {{
                console.error('Stats update error:', e);
            }}
        }}

        async function sendMessage() {{
            const text = input.value.trim();
            if (!text) return;

            input.value = '';
            addMessage(text, 'user');

            addMessage('[processing...]', 'bot');

            try {{
                let endpoint, params;

                if (text.startsWith('!')) {{
                    endpoint = '/api/tasks/command';
                    params = {{ cmd: text }};
                }} else if (text.toLowerCase() === 'morning' || text.toLowerCase() === 'morning briefing') {{
                    endpoint = '/api/briefing/morning';
                    params = {{}};
                }} else if (text.toLowerCase() === 'evening' || text.toLowerCase() === 'evening briefing') {{
                    endpoint = '/api/briefing/evening';
                    params = {{}};
                }} else {{
                    endpoint = '/api/briefing/ask';
                    params = {{ q: text }};
                }}

                const url = new URL(endpoint, window.location.origin);
                Object.entries(params).forEach(([k, v]) => url.searchParams.append(k, v));

                const response = await fetch(url);
                const data = await response.json();

                // Remove processing message
                const messages = messagesDiv.querySelectorAll('.message');
                if (messages.length > 0) {{
                    messages[messages.length - 1].remove();
                }}

                let botText = '';
                if (data.message) {{
                    botText = data.message;
                }} else if (data.response) {{
                    botText = data.response;
                }} else if (data.content) {{
                    botText = data.content;
                }} else if (data.dashboard) {{
                    botText = data.dashboard;
                }} else {{
                    botText = JSON.stringify(data, null, 2);
                }}

                addMessage(botText, 'bot');
            }} catch (error) {{
                const messages = messagesDiv.querySelectorAll('.message');
                if (messages.length > 0) {{
                    messages[messages.length - 1].remove();
                }}
                addMessage('ERROR: ' + error.message, 'bot');
            }}
        }}

        function addMessage(text, sender) {{
            const msg = document.createElement('div');
            msg.className = 'message ' + sender;
            msg.textContent = text;
            messagesDiv.appendChild(msg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }}

        window.addEventListener('load', () => {{
            addMessage('Welcome to Project SUNNY', 'bot');
            addMessage('Type "morning" for briefing, "!tasks" to see tasks, or ask a question', 'bot');
            updateStats();
            setInterval(updateStats, 2000);
        }});
    </script>
</body>
</html>
        """
        return HTMLResponse(content=html)

    @router.get("/api/ask")
    async def ask(q: str):
        """Ask a question (for non-WebSocket requests)."""
        response = await briefing_engine.answer_question(q)
        return {"response": response}

    @router.get("/api/morning")
    async def morning():
        """Get morning briefing."""
        briefing = await briefing_engine.generate_morning_briefing()
        return {"content": briefing}

    @router.get("/api/evening")
    async def evening():
        """Get evening briefing."""
        briefing = await briefing_engine.generate_evening_briefing()
        return {"content": briefing}

    return router
