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
    router = APIRouter(prefix="")

    # Initialize engines
    settings = get_settings()
    briefing_engine = BriefingEngine()
    tasks_db = TaskDB(settings.project_root / "tasks.db")
    tasks_engine = TaskEngine(tasks_db)

    @router.get("/")
    async def chatbot_ui():
        """Serve the chatbot web interface with modern theme."""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SUNNY Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #0a0e27 0%, #1a1a3e 100%);
            color: #00d4ff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            width: 100%;
            max-width: 700px;
            height: 80vh;
            background: #0a0e27;
            border: 2px solid #00d4ff;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 0 30px rgba(0, 212, 255, 0.2);
        }

        .header {
            background: linear-gradient(90deg, #00d4ff 0%, #00ff88 100%);
            color: #0a0e27;
            padding: 20px;
            text-align: center;
            border-bottom: 2px solid #00d4ff;
        }

        .header h1 {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .header p {
            font-size: 12px;
            opacity: 0.8;
        }

        .header .nav-link {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 11px;
            color: #0a0e27;
            text-decoration: none;
            border: 1px solid #0a0e27;
            padding: 4px 10px;
            font-weight: bold;
            opacity: 0.85;
            transition: opacity 0.2s;
        }

        .header .nav-link:hover {
            opacity: 1;
        }

        .header {
            position: relative;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #0a0e27;
        }

        .message {
            margin-bottom: 15px;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .message.user {
            text-align: right;
        }

        .message.user .bubble {
            background: linear-gradient(90deg, #ff006e 0%, #ff4757 100%);
            color: white;
            border-radius: 12px 12px 0 12px;
        }

        .message.bot .bubble {
            background: #1a2540;
            color: #00ff88;
            border-radius: 12px 12px 12px 0;
            border-left: 3px solid #00d4ff;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .bubble {
            display: inline-block;
            max-width: 80%;
            padding: 12px 16px;
            font-size: 14px;
            line-height: 1.4;
        }

        .input-area {
            padding: 15px;
            background: #0a0e27;
            border-top: 2px solid #00d4ff;
            display: flex;
            gap: 10px;
        }

        input {
            flex: 1;
            padding: 12px 15px;
            background: #1a2540;
            border: 1px solid #00d4ff;
            color: #00d4ff;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            outline: none;
            transition: all 0.3s;
        }

        input:focus {
            border-color: #00ff88;
            box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);
        }

        input::placeholder {
            color: #00d4ff;
            opacity: 0.5;
        }

        button {
            padding: 12px 20px;
            background: linear-gradient(90deg, #00d4ff 0%, #00ff88 100%);
            color: #0a0e27;
            border: none;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s;
        }

        button:hover {
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.5);
            transform: translateY(-2px);
        }

        button:active {
            transform: translateY(0);
        }

        .typing {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #00ff88;
            border-radius: 50%;
            animation: typing 1.4s infinite;
            margin: 0 2px;
        }

        @keyframes typing {
            0%, 60%, 100% {
                transform: translateY(0);
            }
            30% {
                transform: translateY(-10px);
            }
        }

        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: #0a0e27;
        }

        ::-webkit-scrollbar-thumb {
            background: #00d4ff;
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #00ff88;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a class="nav-link" href="/console">STATUS</a>
            <h1>SUNNY</h1>
            <p>Chat with your AI assistant</p>
        </div>

        <div class="messages" id="messages"></div>

        <div class="input-area">
            <input
                type="text"
                id="input"
                placeholder="Ask me anything..."
                autocomplete="off"
            />
            <button onclick="sendMessage()">SEND</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('input');

        input.addEventListener('keypress', (e) => {{
            if (e.key === 'Enter') sendMessage();
        }});

        async function sendMessage() {{
            const text = input.value.trim();
            if (!text) return;

            input.value = '';
            addMessage(text, 'user');

            const typingMsg = document.createElement('div');
            typingMsg.className = 'message bot';
            typingMsg.innerHTML = '<div class="bubble"><span class="typing"></span><span class="typing"></span><span class="typing"></span></div>';
            messagesDiv.appendChild(typingMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

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

                messagesDiv.removeChild(typingMsg);

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
                messagesDiv.removeChild(typingMsg);
                addMessage('ERROR: ' + error.message, 'bot');
            }}
        }}

        function addMessage(text, sender) {{
            const msg = document.createElement('div');
            msg.className = 'message ' + sender;
            msg.innerHTML = '<div class="bubble">' + escapeHtml(text) + '</div>';
            messagesDiv.appendChild(msg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        window.addEventListener('load', () => {{
            addMessage('Welcome to Project SUNNY', 'bot');
            addMessage('Try: "morning" for briefing, "!tasks" for your tasks, or ask a question', 'bot');
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
