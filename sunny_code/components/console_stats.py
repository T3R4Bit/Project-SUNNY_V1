"""The console — Sunny's one web surface: chat on one side, live system/Google
status on the other. Replaces the old split between /chatbot and /console."""

import psutil
import logging
import subprocess
import socket
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

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
    """Create console routes: the combined UI plus its stats API."""
    router = APIRouter(prefix="/console")

    @router.get("/")
    async def console_ui():
        """Serve the combined chat + system status page."""
        tailscale_ip = get_tailscale_ip()
        tailscale_url = f"http://{tailscale_ip}:5000" if tailscale_ip else "http://127.0.0.1:5000"

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='40' fill='%23ffb703'/%3E%3C/svg%3E">
    <title>SUNNY</title>
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
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}

        .topbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 20px;
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.14), rgba(0, 255, 136, 0.06));
            border-bottom: 1px solid var(--border);
            flex-shrink: 0;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }}

        .sun-badge {{
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 17px;
            background: radial-gradient(circle at 35% 30%, #fff6d8, var(--green) 55%, var(--cyan) 100%);
            box-shadow: 0 0 18px rgba(0, 255, 136, 0.45);
        }}

        .brand-text h1 {{
            font-size: 15px;
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
            font-size: 10.5px;
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

        .icon-btn {{
            flex-shrink: 0;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            border: 1px solid var(--border);
            background: transparent;
            color: var(--dim);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            transition: all 0.2s;
        }}

        .icon-btn:hover {{
            color: var(--pink);
            border-color: var(--pink);
            background: rgba(255, 77, 126, 0.1);
        }}

        .layout {{
            flex: 1;
            display: flex;
            gap: 16px;
            padding: 16px;
            min-height: 0;
            overflow: hidden;
        }}

        /* ---- Chat column ---- */

        .chat-col {{
            flex: 1.5;
            min-width: 0;
            display: flex;
        }}

        .chat-card {{
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
            background: linear-gradient(180deg, var(--panel) 0%, var(--bg) 100%);
            border: 1px solid var(--border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 24px 60px -24px rgba(0, 0, 0, 0.7), 0 0 50px -18px rgba(0, 212, 255, 0.2);
        }}

        .chips {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            padding: 14px 18px 0;
        }}

        .chip {{
            font-family: inherit;
            font-size: 11.5px;
            padding: 7px 12px;
            border-radius: 20px;
            border: 1px solid var(--border);
            background: rgba(0, 212, 255, 0.06);
            color: var(--cyan);
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
        }}

        .chip:hover {{
            background: rgba(0, 212, 255, 0.16);
            transform: translateY(-1px);
        }}

        .messages {{
            flex: 1;
            overflow-y: auto;
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            scroll-behavior: smooth;
            min-height: 0;
        }}

        .message {{
            display: flex;
            gap: 10px;
            max-width: 88%;
            animation: rise 0.3s ease-out;
        }}

        @keyframes rise {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .message.user {{ align-self: flex-end; flex-direction: row-reverse; }}
        .message.bot {{ align-self: flex-start; }}

        .avatar {{
            flex-shrink: 0;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
        }}

        .message.bot .avatar {{
            background: linear-gradient(135deg, var(--cyan), var(--green));
            color: #04101f;
        }}

        .message.user .avatar {{
            background: linear-gradient(135deg, var(--pink), #ff8a5c);
            color: #240a12;
        }}

        .bubble-wrap {{ display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
        .message.user .bubble-wrap {{ align-items: flex-end; }}

        .bubble {{
            padding: 11px 15px;
            font-size: 13.5px;
            line-height: 1.55;
            white-space: pre-wrap;
            word-break: break-word;
            box-shadow: 0 4px 14px -6px rgba(0, 0, 0, 0.5);
        }}

        .message.bot .bubble {{
            background: var(--elevated);
            color: #d7f4ff;
            border: 1px solid rgba(0, 212, 255, 0.18);
            border-radius: 4px 14px 14px 14px;
        }}

        .message.user .bubble {{
            background: linear-gradient(135deg, var(--pink), #ff7a5c);
            color: #fff;
            border-radius: 14px 4px 14px 14px;
        }}

        .meta {{ font-size: 10px; color: var(--dim); padding: 0 4px; }}

        .input-bar {{
            padding: 14px 16px;
            background: #080b1c;
            border-top: 1px solid var(--border);
            display: flex;
            align-items: flex-end;
            gap: 10px;
        }}

        .input-shell {{
            flex: 1;
            display: flex;
            align-items: flex-end;
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 6px 6px 6px 16px;
            transition: all 0.2s;
        }}

        .input-shell:focus-within {{
            border-color: var(--green);
            box-shadow: 0 0 0 3px rgba(0, 255, 136, 0.12);
        }}

        #input {{
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
        }}

        #input::placeholder {{ color: var(--dim); }}

        .send-btn {{
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, var(--cyan), var(--green));
            color: #04101f;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 15px;
            transition: all 0.2s;
        }}

        .send-btn:hover:not(:disabled) {{
            transform: scale(1.06);
            box-shadow: 0 0 16px rgba(0, 255, 136, 0.5);
        }}

        .send-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}

        .typing-dots {{ display: inline-flex; gap: 4px; padding: 4px 2px; }}
        .typing-dots span {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
            animation: typing 1.4s infinite;
        }}
        .typing-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
        .typing-dots span:nth-child(3) {{ animation-delay: 0.4s; }}

        @keyframes typing {{
            0%, 60%, 100% {{ transform: translateY(0); opacity: 0.5; }}
            30% {{ transform: translateY(-6px); opacity: 1; }}
        }}

        .messages::-webkit-scrollbar, .side-col::-webkit-scrollbar {{ width: 7px; }}
        .messages::-webkit-scrollbar-track, .side-col::-webkit-scrollbar-track {{ background: transparent; }}
        .messages::-webkit-scrollbar-thumb, .side-col::-webkit-scrollbar-thumb {{
            background: rgba(0, 212, 255, 0.35);
            border-radius: 4px;
        }}
        .messages::-webkit-scrollbar-thumb:hover, .side-col::-webkit-scrollbar-thumb:hover {{ background: var(--cyan); }}

        /* ---- Side column ---- */

        .side-col {{
            width: 300px;
            flex-shrink: 0;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
            padding-right: 2px;
        }}

        .section-label {{
            font-size: 10.5px;
            letter-spacing: 2px;
            color: var(--dim);
            margin-bottom: 8px;
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

        .kv-grid dt {{ color: var(--dim); font-size: 11px; letter-spacing: 0.5px; align-self: center; }}
        .kv-grid dd {{ color: var(--text); font-weight: 600; overflow-wrap: anywhere; }}
        .kv-grid a {{ color: var(--cyan); text-decoration: none; }}
        .kv-grid a:hover {{ text-decoration: underline; }}

        .loc-row {{ display: flex; gap: 6px; }}

        .loc-input {{
            flex: 1;
            min-width: 0;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 10px;
            color: var(--text);
            font-family: inherit;
            font-size: 12.5px;
            outline: none;
        }}

        .loc-input:focus {{ border-color: var(--green); }}

        .loc-save {{
            flex-shrink: 0;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: rgba(0, 255, 136, 0.08);
            color: var(--green);
            font-family: inherit;
            font-size: 11.5px;
            padding: 6px 10px;
            cursor: pointer;
            transition: all 0.15s;
        }}

        .loc-save:hover {{ background: rgba(0, 255, 136, 0.18); }}

        .loc-status {{ font-size: 10.5px; color: var(--dim); margin-top: 8px; }}

        .metrics {{ display: flex; flex-direction: column; gap: 14px; }}
        .metric-row {{ display: flex; align-items: center; gap: 12px; }}
        .metric-label {{ width: 46px; flex-shrink: 0; font-size: 11px; letter-spacing: 0.5px; color: var(--dim); }}

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

        .stat-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}

        .stat-tile {{
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px;
            text-align: center;
        }}

        .stat-tile .label {{ font-size: 10px; letter-spacing: 0.5px; color: var(--dim); margin-bottom: 4px; }}
        .stat-tile .value {{ font-size: 15px; font-weight: 700; color: var(--green); }}

        .side-footer {{ font-size: 10px; color: var(--dim); text-align: center; padding: 4px 0 8px; }}

        @media (max-width: 900px) {{
            body {{ height: auto; overflow: auto; }}
            .layout {{ flex-direction: column; overflow: visible; padding: 12px; }}
            .chat-col {{ height: 72vh; }}
            .side-col {{ width: 100%; overflow: visible; }}
            .stat-grid {{ grid-template-columns: 1fr 1fr; }}
        }}
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

    <div class="layout">
        <div class="chat-col">
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
        </div>

        <aside class="side-col">
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

            <div class="side-footer">Last updated: <span id="timestamp">-</span> &middot; refreshes every 2s</div>
        </aside>
    </div>

    <script>
        // ---------- Chat ----------
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const chips = document.getElementById('chips');
        const clearBtn = document.getElementById('clearBtn');

        const STORAGE_KEY = 'sunny-chat-history';
        const SESSION_KEY = 'sunny-chat-session';
        const MAX_HISTORY = 200;

        function getSessionId() {{
            let id = localStorage.getItem(SESSION_KEY);
            if (!id) {{
                id = 'sess-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
                try {{ localStorage.setItem(SESSION_KEY, id); }} catch (e) {{ /* no persistence */ }}
            }}
            return id;
        }}

        const sessionId = getSessionId();

        function loadHistory() {{
            try {{
                const raw = localStorage.getItem(STORAGE_KEY);
                return raw ? JSON.parse(raw) : [];
            }} catch (e) {{ return []; }}
        }}

        function saveHistory() {{
            try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-MAX_HISTORY))); }}
            catch (e) {{ /* storage full/unavailable — chat still works this session */ }}
        }}

        let history = loadHistory();

        function autoGrow() {{
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 100) + 'px';
        }}
        input.addEventListener('input', autoGrow);

        input.addEventListener('keydown', (e) => {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }});

        sendBtn.addEventListener('click', sendMessage);

        chips.addEventListener('click', (e) => {{
            const chip = e.target.closest('.chip');
            if (!chip) return;
            const cmd = chip.dataset.cmd;
            if (chip.dataset.send === '1') {{
                input.value = cmd;
                sendMessage();
            }} else {{
                input.value = cmd;
                autoGrow();
                input.focus();
            }}
        }});

        function timestamp() {{
            return new Date().toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
        }}

        async function sendMessage() {{
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

            try {{
                const url = new URL('/api/assistant/message', window.location.origin);
                url.searchParams.append('text', text);
                url.searchParams.append('session', sessionId);

                const response = await fetch(url, {{ method: 'POST' }});
                const data = await response.json();

                messagesDiv.removeChild(typingMsg);

                const botText = data.response || JSON.stringify(data, null, 2);
                addMessage(botText, 'bot');
            }} catch (error) {{
                messagesDiv.removeChild(typingMsg);
                addMessage('ERROR: ' + error.message, 'bot');
            }} finally {{
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }}
        }}

        function renderMessage(text, sender, time) {{
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
        }}

        function addMessage(text, sender) {{
            const time = timestamp();
            renderMessage(text, sender, time);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            history.push({{ text, sender, time }});
            saveHistory();
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        clearBtn.addEventListener('click', () => {{
            if (!confirm('Clear chat history? This only clears it on this device.')) return;
            history = [];
            saveHistory();
            messagesDiv.innerHTML = '';
            addMessage('Chat cleared. Try a shortcut below or ask me anything.', 'bot');
        }});

        window.addEventListener('load', () => {{
            if (history.length > 0) {{
                history.forEach((m) => renderMessage(m.text, m.sender, m.time));
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }} else {{
                addMessage('Welcome to Project SUNNY. Try a shortcut below or ask me anything.', 'bot');
            }}
            input.focus();
        }});

        // ---------- System stats ----------
        let lastNetStats = null;

        function setBarState(barEl, valueEl, value, suffix) {{
            valueEl.textContent = value.toFixed(1) + suffix;
            barEl.style.width = Math.min(value, 100) + '%';
            barEl.className = 'metric-fill' + (value > 90 ? ' critical' : value > 70 ? ' warning' : '');
        }}

        async function updateStats() {{
            try {{
                const response = await fetch('/console/api/stats');
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const data = await response.json();
                if (data.error) {{ console.error('API error:', data.error); return; }}

                if (data.hostname) document.getElementById('hostname').textContent = data.hostname;
                document.getElementById('tailscale-ip').textContent = data.tailscale_ip || 'N/A';

                if (typeof data.cpu === 'number') setBarState(document.getElementById('cpu-bar'), document.getElementById('cpu'), data.cpu, '%');
                if (typeof data.ram === 'number') setBarState(document.getElementById('ram-bar'), document.getElementById('ram'), data.ram, '%');
                if (typeof data.disk === 'number') setBarState(document.getElementById('disk-bar'), document.getElementById('disk'), data.disk, '%');

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

        // ---------- Google status ----------
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

        // ---------- Location (weather) ----------
        async function loadLocation() {{
            try {{
                const response = await fetch('/api/weather/location');
                const data = await response.json();
                document.getElementById('location-input').value = data.location || '';
            }} catch (error) {{
                console.error('Location load error:', error);
            }}
        }}

        async function saveLocation() {{
            const input = document.getElementById('location-input');
            const statusEl = document.getElementById('location-status');
            const value = input.value.trim();
            if (!value) {{
                statusEl.textContent = 'Enter a location first, e.g. "Detroit,MI,US".';
                return;
            }}
            try {{
                const response = await fetch('/api/weather/location', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ location: value }}),
                }});
                const data = await response.json();
                statusEl.textContent = data.status === 'saved'
                    ? 'Saved — weather updates immediately, no restart needed.'
                    : (data.message || 'Error saving location.');
            }} catch (error) {{
                statusEl.textContent = 'Error saving location — check the console log.';
                console.error('Location save error:', error);
            }}
        }}

        document.getElementById('location-save').addEventListener('click', saveLocation);
        document.getElementById('location-input').addEventListener('keydown', (e) => {{
            if (e.key === 'Enter') {{ e.preventDefault(); saveLocation(); }}
        }});

        window.addEventListener('load', () => {{
            updateStats();
            setInterval(updateStats, 2000);
            updateGoogleStatus();
            setInterval(updateGoogleStatus, 30000);
            loadLocation();
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
