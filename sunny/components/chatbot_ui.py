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
        """Serve the chatbot web interface."""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project SUNNY — Chatbot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            width: 100%;
            max-width: 600px;
            height: 80vh;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .header h1 {
            font-size: 24px;
            margin-bottom: 5px;
        }

        .header p {
            font-size: 12px;
            opacity: 0.9;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f7f7f7;
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
            background: #667eea;
            color: white;
            border-radius: 18px 18px 0 18px;
        }

        .message.bot .bubble {
            background: #e0e0e0;
            color: #333;
            border-radius: 18px 18px 18px 0;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .bubble {
            display: inline-block;
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 14px;
            line-height: 1.4;
        }

        .input-area {
            padding: 15px;
            background: white;
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 10px;
        }

        input {
            flex: 1;
            padding: 12px 15px;
            border: 1px solid #ddd;
            border-radius: 24px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.3s;
        }

        input:focus {
            border-color: #667eea;
        }

        button {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 24px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }

        button:hover {
            background: #764ba2;
        }

        button:active {
            transform: scale(0.95);
        }

        .typing {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #999;
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

        .commands {
            font-size: 12px;
            color: #999;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e0e0e0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌞 Project SUNNY</h1>
            <p>Chatbot — Try asking questions or commands</p>
        </div>

        <div class="messages" id="messages"></div>

        <div class="input-area">
            <input
                type="text"
                id="input"
                placeholder="Ask me anything... (e.g., 'morning briefing', '!tasks', 'weather')"
                autocomplete="off"
            />
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('input');

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        async function sendMessage() {
            const text = input.value.trim();
            if (!text) return;

            input.value = '';

            // Add user message
            addMessage(text, 'user');

            // Show typing indicator
            const typingMsg = document.createElement('div');
            typingMsg.className = 'message bot';
            typingMsg.innerHTML = '<div class="bubble"><span class="typing"></span><span class="typing"></span><span class="typing"></span></div>';
            messagesDiv.appendChild(typingMsg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            try {
                // Try to determine if it's a task command or briefing/question
                let endpoint, params;

                if (text.startsWith('!')) {
                    // Task command
                    endpoint = '/api/tasks/command';
                    params = { cmd: text };
                } else if (text.toLowerCase() === 'morning' || text.toLowerCase() === 'morning briefing') {
                    // Morning briefing
                    endpoint = '/api/briefing/morning';
                    params = {};
                } else if (text.toLowerCase() === 'evening' || text.toLowerCase() === 'evening briefing') {
                    // Evening briefing
                    endpoint = '/api/briefing/evening';
                    params = {};
                } else {
                    // Question
                    endpoint = '/api/briefing/ask';
                    params = { q: text };
                }

                // Build URL
                const url = new URL(endpoint, window.location.origin);
                Object.entries(params).forEach(([k, v]) => url.searchParams.append(k, v));

                const response = await fetch(url);
                const data = await response.json();

                // Remove typing indicator
                messagesDiv.removeChild(typingMsg);

                // Add bot response
                let botText = '';
                if (data.message) {
                    botText = data.message;
                } else if (data.response) {
                    botText = data.response;
                } else if (data.content) {
                    botText = data.content;
                } else if (data.dashboard) {
                    botText = data.dashboard;
                } else {
                    botText = JSON.stringify(data, null, 2);
                }

                addMessage(botText, 'bot');
            } catch (error) {
                messagesDiv.removeChild(typingMsg);
                addMessage(`❌ Error: ${error.message}`, 'bot');
            }
        }

        function addMessage(text, sender) {
            const msg = document.createElement('div');
            msg.className = `message ${sender}`;
            msg.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
            messagesDiv.appendChild(msg);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Welcome message
        window.addEventListener('load', () => {
            addMessage('👋 Welcome to Project SUNNY!\\n\\nTry asking:\\n• "morning" for morning briefing\\n• "!tasks" for your task list\\n• "what\\'s the weather?" for weather\\n• "!task add \\"Title\\" --tag School" to create a task', 'bot');
        });
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
