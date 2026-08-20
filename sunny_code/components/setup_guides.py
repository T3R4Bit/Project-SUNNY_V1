"""Chat-facing setup guides: "setup weather", "setup calendar", "setup discord",
or bare "setup" for an overview. Same content as the architecture docs
(google-integration.md, discord-bot.md) condensed for a chat bubble, with a
live status line pulled from actual config/connection state — not just static
text — so the answer is never stale.
"""

from typing import Optional

from sunny_code.components import google_auth, location_store, tts
from sunny_code.components.data_sources import is_configured
from sunny_code.config import get_settings, looks_configured

_ALIASES = {
    "claude": "claude",
    "llm": "claude",
    "anthropic": "claude",
    "ai": "claude",
    "weather": "weather",
    "openweathermap": "weather",
    "openweather": "weather",
    "gps": "gps",
    "owntracks": "gps",
    "location": "gps",
    "calendar": "google",
    "google calendar": "google",
    "email": "google",
    "gmail": "google",
    "google": "google",
    "sign in": "google",
    "sign-in": "google",
    "google sign in": "google",
    "google sign-in": "google",
    "discord": "discord",
    "discord bot": "discord",
    "piper": "piper",
    "speak": "piper",
    "tts": "piper",
    "text to speech": "piper",
    "text-to-speech": "piper",
    "commute": "commute",
    "traffic": "commute",
    "maps": "commute",
    "google maps": "commute",
    "health": "health",
    "wellness": "health",
    "news": "news",
    "motorsports": "motorsports",
    "racing": "motorsports",
    "tasks": "tasks",
    "task": "tasks",
}


def _claude_guide() -> str:
    settings = get_settings()
    status = "Connected" if looks_configured(settings.claude_api_key) else "Not connected"
    return f"""CLAUDE (LLM) SETUP
Status: {status}

No feature calls this yet — it's the safety-rail infrastructure only (spend
caps, usage logging) that has to exist before any LLM feature is turned on.
See sunny-vault/docs/architecture/llm-readiness.md for what's built and
what's still gated on this.

1. Go to console.anthropic.com and create an account/API key.
2. Add to .env: CLAUDE_API_KEY=<your key> — then restart Sunny.
3. Optional — adjust spend caps in .env (defaults: $20/day, $100/month):
   DAILY_SPEND_CAP=20.0
   MONTHLY_SPEND_CAP=100.0

Spend so far today/this month: GET /api/dashboard/spend/today and
/api/dashboard/spend/month once a key is set."""


def _weather_guide() -> str:
    status = "Connected" if is_configured("weather") else "Not connected"
    location = location_store.get_location()
    gps = location_store.get_coordinates()
    location_line = f"{location} (also have a live GPS fix)" if location and gps else \
        (f"GPS fix, {gps[0]:.3f},{gps[1]:.3f}" if gps else (location or "not set"))
    return f"""WEATHER SETUP (OpenWeatherMap)
Status: {status}
Location: {location_line}

Needs two things — a key alone can't tell OpenWeatherMap where you are:

1. Go to openweathermap.org/api and create a free account.
2. Under "My API keys", copy your default key (or generate a new one).
3. Add to .env: OPENWEATHERMAP_API_KEY=<your key> — then restart Sunny.
4. Set your location on /console (LOCATION card) — saves instantly, no
   restart needed, and can be changed anytime. Format: City,State,Country
   (e.g. Detroit,MI,US). See sunny-vault/docs/architecture/location.md.

Or skip the static location entirely and connect live GPS instead — see
"setup gps"."""


def _google_guide() -> str:
    if not google_auth.is_client_configured():
        status = "Not set up (no OAuth client yet)"
    elif not google_auth.is_connected():
        status = "Client configured, but not signed in yet"
    else:
        status = f"Connected as {google_auth.connected_email()}"

    return f"""GOOGLE SIGN-IN SETUP (Calendar + Gmail)
Status: {status}

1. console.cloud.google.com → create/select a project.
2. APIs & Services → Library → enable "Google Calendar API" and "Gmail API".
3. APIs & Services → OAuth consent screen → External, add yourself as a test
   user, add scopes calendar.readonly + gmail.readonly, set Publishing
   status to "In production" (Testing mode expires refresh tokens every 7 days).
4. APIs & Services → Credentials → Create OAuth client ID → Web application
   → redirect URI: http://<your-tailscale-ip>:5000/auth/google/callback
5. Copy Client ID/Secret into .env:
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_OAUTH_REDIRECT_URI=http://<your-tailscale-ip>:5000/auth/google/callback
6. Restart Sunny, open /console, click "Connect Google Account" in the GOOGLE card.

Covers Calendar + Gmail (read-only) only — not Drive, Contacts, sending mail,
or Maps/traffic. Full details: sunny-vault/docs/architecture/google-integration.md"""


def _discord_guide() -> str:
    settings = get_settings()
    if looks_configured(settings.discord_bot_token) and settings.discord_chat_channel_id:
        status = "Connected"
    else:
        status = "Not connected"

    return f"""DISCORD BOT SETUP
Status: {status}

1. discord.com/developers/applications → New Application.
2. Bot tab → Reset Token → copy it. Enable the "MESSAGE CONTENT INTENT" toggle
   (under Privileged Gateway Intents) or commands won't parse.
3. OAuth2 → URL Generator → check "bot" scope → permissions: View Channel,
   Send Messages, Read Message History, Manage Messages, Add Reactions, and
   (for the create/delete channel & role commands) Manage Channels + Manage
   Roles. Open the generated URL, pick your server, authorize.
4. In Discord, enable Developer Mode (User Settings → Advanced), right-click
   the channel you want commands read from → Copy Channel ID.
5. Add to .env:
   DISCORD_BOT_TOKEN=<your token>
   DISCORD_CHAT_CHANNEL_ID=<channel id, no quotes>
6. Restart Sunny.

Optional — DISCORD_TASKS_CHANNEL_ID gives the pinned task dashboard its own
read-only channel instead of sharing the chat channel (nothing is ever read
from it). DISCORD_BRIEFINGS_CHANNEL_ID, DISCORD_WARNINGS_CHANNEL_ID,
DISCORD_TASK_UPDATES_CHANNEL_ID are separate output-only channels for
specific things. Leave any blank to keep that output going to the chat
channel.

Full details: sunny-vault/docs/architecture/discord-bot.md"""


def _not_built_guide(label: str) -> str:
    return f"""{label.upper()} SETUP
Status: Not built yet — no integration exists to connect

There's no API wired up for this yet, so there's nothing to configure. Every
time you ask about it, it gets logged to sunny-vault/log/requests.md — real
usage is what decides what gets built next."""


def _tasks_guide() -> str:
    return """TASKS
Status: Always connected — stored directly in the vault (sunny-vault/state/tasks/), no API or setup needed."""


def _gps_guide() -> str:
    settings = get_settings()
    fix = location_store.get_coordinates()
    status = f"Connected — last fix {fix[0]:.4f}, {fix[1]:.4f}" if fix else "Not connected"
    auth_line = (
        "A shared secret is set — use it as the Basic Auth password (any username)."
        if looks_configured(settings.owntracks_shared_secret)
        else "No shared secret set — the endpoint accepts reports with no auth at all "
        "(fine for personal use over Tailscale; set OWNTRACKS_SHARED_SECRET in .env for a bit more safety)."
    )
    return f"""GPS LOCATION (OwnTracks)
Status: {status}

Free, self-hosted, no cloud — OwnTracks pushes your phone's location
straight to Sunny on its own schedule (~30 min by default in the app,
configurable). A fix older than 30 minutes is treated as if there isn't
one, and weather falls back to your static location (see "setup weather").

1. Install OwnTracks (iOS or Android) — owntracks.org
2. In the app's connection settings, choose HTTP mode.
3. Endpoint URL: https://<your-tailscale-hostname>:5443/api/location/owntracks
4. {auth_line}
5. Set the report mode to "Significant" or a custom interval — your call.

Full details: sunny-vault/docs/architecture/location.md"""


def _piper_guide() -> str:
    settings = get_settings()
    status = "Connected — voice model downloaded" if tts.is_voice_downloaded() else \
        "Not downloaded yet — happens automatically the first time /speak is used"
    return f"""PIPER TTS SETUP
Status: {status}
Voice: {settings.piper_voice}

Free, fully local text-to-speech — no API key, no cost, nothing to sign up
for. Type /speak <text> as a real Discord slash command (not a plain chat
message) in the chat channel — Sunny posts back a playable audio attachment.

1. Nothing to configure — the voice model (~60MB) downloads automatically
   the first time /speak is used.
2. If /speak doesn't show up in Discord's slash-command picker, the bot's
   invite is probably missing the "applications.commands" scope — re-run
   the invite URL with that box checked too (see "setup discord"), Discord
   updates the bot in place, no need to kick/re-invite.
3. Keep it under 1000 characters per call.

Full details: sunny-vault/docs/architecture/tts-piper.md"""


_GUIDES = {
    "claude": _claude_guide,
    "weather": _weather_guide,
    "gps": _gps_guide,
    "piper": _piper_guide,
    "google": _google_guide,
    "discord": _discord_guide,
    "commute": lambda: _not_built_guide("commute/traffic"),
    "health": lambda: _not_built_guide("health/wellness"),
    "news": lambda: _not_built_guide("news"),
    "motorsports": lambda: _not_built_guide("motorsports"),
    "tasks": _tasks_guide,
}

_OVERVIEW_ORDER = ["tasks", "weather", "gps", "google", "discord", "piper", "claude", "commute", "health", "news", "motorsports"]
_OVERVIEW_LABELS = {
    "tasks": "Tasks",
    "claude": "Claude (LLM, infra-only)",
    "weather": "Weather",
    "gps": "GPS location (OwnTracks)",
    "google": "Calendar + Email (Google)",
    "discord": "Discord bot",
    "piper": "Voice (Piper TTS, /speak)",
    "commute": "Commute/Traffic",
    "health": "Health",
    "news": "News",
    "motorsports": "Motorsports",
}


def _overview_status(key: str) -> str:
    if key == "google":
        if not google_auth.is_client_configured():
            return "not set up"
        return "connected" if google_auth.is_connected() else "needs sign-in"
    if key == "discord":
        settings = get_settings()
        return "connected" if (looks_configured(settings.discord_bot_token) and settings.discord_chat_channel_id) else "not connected"
    if key in ("commute", "health", "news", "motorsports"):
        return "not built yet"
    if key == "claude":
        settings = get_settings()
        return "connected" if looks_configured(settings.claude_api_key) else "not connected"
    if key == "gps":
        return "connected" if location_store.get_coordinates() is not None else "not connected"
    if key == "piper":
        return "connected" if tts.is_voice_downloaded() else "not downloaded yet"
    source = "weather" if key == "weather" else key
    return "connected" if is_configured(source) else "not connected"


def overview() -> str:
    lines = ["SETUP STATUS — type \"setup <name>\" for step-by-step instructions\n"]
    for key in _OVERVIEW_ORDER:
        lines.append(f"  {_OVERVIEW_LABELS[key]:<28} {_overview_status(key)}")
    lines.append('\nExample: "setup weather" or "setup calendar"')
    return "\n".join(lines)


def guide_for(query: str) -> Optional[str]:
    key = _ALIASES.get(query.strip().lower())
    if key is None:
        return None
    return _GUIDES[key]()


def respond(query: str) -> str:
    """query="" means the bare "setup" overview; otherwise a source name/alias."""
    if not query:
        return overview()
    guide = guide_for(query)
    if guide is None:
        return (
            f'Not sure what "{query}" is. Try: setup weather, setup calendar, '
            f'setup email, setup discord — or just "setup" to see everything.'
        )
    return guide
