"""Discord bot — task commands and a live-updating dashboard in a dedicated channel.

Uses the exact same routing as the web chatbot (sunny.components.assistant.handle_message),
so behavior is identical across interfaces. Scoped to one channel (DISCORD_TASKS_CHANNEL_ID) —
messages elsewhere are ignored.

Setup steps: see sunny-vault/docs/architecture/discord-bot.md
"""

import logging

import discord
from discord.ext import tasks

from sunny.components.assistant import handle_message
from sunny.components.briefing import BriefingEngine
from sunny.components.key_status import missing_api_keys, startup_summary
from sunny.components.tasks_engine import TaskEngine
from sunny.components.tasks_parser import TaskCommandParser

logger = logging.getLogger(__name__)

DASHBOARD_MARKER = "​"  # zero-width space appended to the dashboard message so a
# restarted bot can recognize its own pinned message and start editing it again
REFRESH_EMOJI = "🔄"
MAX_MESSAGE_LENGTH = 1900  # Discord's real limit is 2000; leave headroom


def _chunk_message(text: str, limit: int = MAX_MESSAGE_LENGTH):
    """Split text into Discord-safe chunks, preferring newline boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def create_discord_bot(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    tasks_channel_id: int,
) -> discord.Client:
    """Build (but don't start) the Discord client."""
    intents = discord.Intents.default()
    intents.message_content = True  # required to read command text, not just embeds/mentions

    client = discord.Client(intents=intents)
    state = {"dashboard_message_id": None, "posted_key_status": False}

    async def refresh_dashboard():
        """Post or edit the pinned dashboard message in the tasks channel."""
        try:
            channel = await client.fetch_channel(tasks_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord tasks channel {tasks_channel_id}: {e}")
            return

        dashboard_text = tasks_engine.format_dashboard() + DASHBOARD_MARKER

        message = None
        if state["dashboard_message_id"]:
            try:
                message = await channel.fetch_message(state["dashboard_message_id"])
            except discord.NotFound:
                message = None

        if message is None:
            # Bot restarted — look for a dashboard message pinned by a previous run
            async for pin in channel.pins(limit=50):
                if pin.author.id == client.user.id and pin.content.endswith(DASHBOARD_MARKER):
                    message = pin
                    break

        if message is not None:
            state["dashboard_message_id"] = message.id
            try:
                await message.edit(content=dashboard_text)
                return
            except discord.NotFound:
                state["dashboard_message_id"] = None

        # Nothing to edit — post a fresh one and pin it
        new_message = await channel.send(dashboard_text)
        try:
            await new_message.pin()
        except discord.Forbidden:
            logger.warning("Missing permission to pin the dashboard message — sent unpinned")
        state["dashboard_message_id"] = new_message.id

    @tasks.loop(minutes=5)
    async def refresh_loop():
        await refresh_dashboard()

    @client.event
    async def on_ready():
        logger.info(f"Discord bot connected as {client.user} (tasks channel: {tasks_channel_id})")
        if not refresh_loop.is_running():
            refresh_loop.start()  # runs immediately, then every 5 minutes

        # Post what's still missing an API key once per run, so it's visible right
        # in the channel — but skip it entirely if everything's configured (no noise).
        if not state["posted_key_status"]:
            state["posted_key_status"] = True
            missing = missing_api_keys()
            if missing:
                try:
                    channel = await client.fetch_channel(tasks_channel_id)
                    await channel.send(startup_summary())
                except (discord.NotFound, discord.Forbidden) as e:
                    logger.warning(f"Could not post startup key-status summary: {e}")

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != tasks_channel_id:
            return

        response = await handle_message(message.content, tasks_engine, briefing_engine)
        for chunk in _chunk_message(response):
            await message.channel.send(chunk)

        # Only refresh the dashboard for commands that actually changed something
        cmd_type, _, _ = TaskCommandParser.parse_command(message.content.strip())
        if cmd_type in ("add", "update", "delete"):
            await refresh_dashboard()

    @client.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        if payload.user_id == client.user.id:
            return
        if str(payload.emoji) != REFRESH_EMOJI:
            return
        if payload.message_id != state["dashboard_message_id"]:
            return

        await refresh_dashboard()

        # Clear the reaction so it's ready to use again
        try:
            channel = await client.fetch_channel(payload.channel_id)
            reacted_message = await channel.fetch_message(payload.message_id)
            user = await client.fetch_user(payload.user_id)
            await reacted_message.remove_reaction(payload.emoji, user)
        except (discord.NotFound, discord.Forbidden):
            pass

    return client
