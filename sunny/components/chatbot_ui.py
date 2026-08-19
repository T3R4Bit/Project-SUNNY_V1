"""Web-based chatbot UI served over Tailscale."""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
import logging
import asyncio

from sunny.components.briefing import BriefingEngine
from sunny.components.tasks_engine import TaskEngine
from sunny.components.tasks_db import TaskDB
from sunny.components.assistant import handle_message
from sunny.config import get_settings

logger = logging.getLogger(__name__)


def create_chatbot_router() -> APIRouter:
    """Create chatbot UI routes."""
    router = APIRouter(prefix="")

    # Initialize engines
    settings = get_settings()
    tasks_db = TaskDB(settings.project_root / "tasks.db")
    tasks_engine = TaskEngine(tasks_db)
    briefing_engine = BriefingEngine()

    @router.get("/")
    async def root():
        """Redirect root to the chatbot UI."""
        return RedirectResponse(url="/chatbot")

    @router.post("/api/assistant/message")
    async def assistant_message(text: str = Query(..., description="Free-text message from the chatbot")):
        """Single entry point for the chatbot — routing lives in sunny.components.assistant
        so the web chatbot and the Discord bot behave identically."""
        response = await handle_message(text, tasks_engine, briefing_engine)
        return {"response": response}

    @router.get("/chatbot")
    async def chatbot_ui():
        """Serve the chatbot web interface with modern theme."""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="dark">
    <title>SUNNY Chat</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%98%80%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg: #0a0e27;
            --panel: #0d1330;
            --elevated: #121a38;
            --cyan: #00d4ff;
            --green: #00ff88;
            --pink: #ff4d7e;
            --text: #e8f6ff;
            --dim: #6b83a8;
            --border: rgba(0, 212, 255, 0.28);
        }

        html, body { height: 100%; }

        body {
            font-family: ui-monospace, 'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace;
            background:
                radial-gradient(circle at 50% -10%, #16204a 0%, var(--bg) 45%, #05070f 100%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px 16px;
        }

        .app {
            width: 100%;
            max-width: 720px;
            height: min(86vh, 820px);
            background: linear-gradient(180deg, var(--panel) 0%, var(--bg) 100%);
            border: 1px solid var(--border);
            border-radius: 20px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow:
                0 24px 60px -24px rgba(0, 0, 0, 0.7),
                0 0 50px -18px rgba(0, 212, 255, 0.25);
        }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 16px 20px;
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.14), rgba(0, 255, 136, 0.06));
            border-bottom: 1px solid var(--border);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }

        .sun-badge {
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
        }

        .brand-text h1 {
            font-size: 16px;
            letter-spacing: 3px;
            font-weight: 800;
            background: linear-gradient(90deg, var(--cyan), var(--green));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }

        .brand-text p {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--dim);
            margin-top: 2px;
        }

        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 6px var(--green);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        .nav-link {
            flex-shrink: 0;
            font-size: 10.5px;
            letter-spacing: 1.5px;
            color: var(--cyan);
            text-decoration: none;
            border: 1px solid var(--border);
            padding: 7px 12px;
            border-radius: 20px;
            transition: all 0.2s;
        }

        .nav-link:hover {
            background: rgba(0, 212, 255, 0.12);
            box-shadow: 0 0 12px rgba(0, 212, 255, 0.3);
        }

        .chips {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            padding: 12px 20px 0;
        }

        .chip {
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
        }

        .chip:hover {
            background: rgba(0, 212, 255, 0.16);
            transform: translateY(-1px);
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            scroll-behavior: smooth;
        }

        .message {
            display: flex;
            gap: 10px;
            max-width: 88%;
            animation: rise 0.3s ease-out;
        }

        @keyframes rise {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.user {
            align-self: flex-end;
            flex-direction: row-reverse;
        }

        .message.bot {
            align-self: flex-start;
        }

        .avatar {
            flex-shrink: 0;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
        }

        .message.bot .avatar {
            background: linear-gradient(135deg, var(--cyan), var(--green));
            color: #04101f;
        }

        .message.user .avatar {
            background: linear-gradient(135deg, var(--pink), #ff8a5c);
            color: #240a12;
        }

        .bubble-wrap {
            display: flex;
            flex-direction: column;
            gap: 4px;
            min-width: 0;
        }

        .message.user .bubble-wrap {
            align-items: flex-end;
        }

        .bubble {
            padding: 11px 15px;
            font-size: 13.5px;
            line-height: 1.55;
            white-space: pre-wrap;
            word-break: break-word;
            box-shadow: 0 4px 14px -6px rgba(0, 0, 0, 0.5);
        }

        .message.bot .bubble {
            background: var(--elevated);
            color: #d7f4ff;
            border: 1px solid rgba(0, 212, 255, 0.18);
            border-radius: 4px 14px 14px 14px;
        }

        .message.user .bubble {
            background: linear-gradient(135deg, var(--pink), #ff7a5c);
            color: #fff;
            border-radius: 14px 4px 14px 14px;
        }

        .meta {
            font-size: 10px;
            color: var(--dim);
            padding: 0 4px;
        }

        .input-bar {
            padding: 14px 16px;
            background: #080b1c;
            border-top: 1px solid var(--border);
            display: flex;
            align-items: flex-end;
            gap: 10px;
        }

        .input-shell {
            flex: 1;
            display: flex;
            align-items: flex-end;
            background: var(--elevated);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 6px 6px 6px 16px;
            transition: all 0.2s;
        }

        .input-shell:focus-within {
            border-color: var(--green);
            box-shadow: 0 0 0 3px rgba(0, 255, 136, 0.12);
        }

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

        #input::placeholder {
            color: var(--dim);
        }

        .send-btn {
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
        }

        .send-btn:hover:not(:disabled) {
            transform: scale(1.06);
            box-shadow: 0 0 16px rgba(0, 255, 136, 0.5);
        }

        .send-btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }

        .typing-dots {
            display: inline-flex;
            gap: 4px;
            padding: 4px 2px;
        }

        .typing-dots span {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
            animation: typing 1.4s infinite;
        }

        .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
        .typing-dots span:nth-child(3) { animation-delay: 0.4s; }

        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
            30% { transform: translateY(-6px); opacity: 1; }
        }

        .messages::-webkit-scrollbar { width: 7px; }
        .messages::-webkit-scrollbar-track { background: transparent; }
        .messages::-webkit-scrollbar-thumb {
            background: rgba(0, 212, 255, 0.35);
            border-radius: 4px;
        }
        .messages::-webkit-scrollbar-thumb:hover { background: var(--cyan); }

        @media (max-width: 640px) {
            body { padding: 0; }
            .app { height: 100vh; max-width: 100%; border-radius: 0; border: none; }
        }
    </style>
</head>
<body>
    <div class="app">
        <div class="header">
            <div class="brand">
                <div class="sun-badge">&#9728;&#65039;</div>
                <div class="brand-text">
                    <h1>SUNNY</h1>
                    <p><span class="status-dot"></span>Online</p>
                </div>
            </div>
            <a class="nav-link" href="/console">CONSOLE</a>
        </div>

        <div class="chips" id="chips">
            <button class="chip" data-cmd="morning" data-send="1">&#9728;&#65039; Morning</button>
            <button class="chip" data-cmd="evening" data-send="1">&#127769; Evening</button>
            <button class="chip" data-cmd="show my tasks" data-send="1">&#10003; Tasks</button>
            <button class="chip" data-cmd="add " data-send="0">&#65291; Add task</button>
        </div>

        <div class="messages" id="messages"></div>

        <div class="input-bar">
            <div class="input-shell">
                <textarea
                    id="input"
                    rows="1"
                    placeholder="Ask me anything..."
                    autocomplete="off"
                ></textarea>
            </div>
            <button class="send-btn" id="sendBtn" aria-label="Send message">&#10148;</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const chips = document.getElementById('chips');

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
            typingMsg.innerHTML = '<div class="avatar">&#9728;&#65039;</div><div class="bubble-wrap"><div class="bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div></div>';
            messagesDiv.appendChild(typingMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            try {
                const url = new URL('/api/assistant/message', window.location.origin);
                url.searchParams.append('text', text);

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

        function addMessage(text, sender) {
            const msg = document.createElement('div');
            msg.className = 'message ' + sender;
            const avatar = sender === 'user' ? '&#128100;' : '&#9728;&#65039;';
            msg.innerHTML =
                '<div class="avatar">' + avatar + '</div>' +
                '<div class="bubble-wrap">' +
                    '<div class="bubble">' + escapeHtml(text) + '</div>' +
                    '<div class="meta">' + timestamp() + '</div>' +
                '</div>';
            messagesDiv.appendChild(msg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        window.addEventListener('load', () => {
            addMessage('Welcome to Project SUNNY. Try a shortcut below or ask me anything.', 'bot');
            input.focus();
        });
    </script>
</body>
</html>
        """
        return HTMLResponse(content=html)

    return router
