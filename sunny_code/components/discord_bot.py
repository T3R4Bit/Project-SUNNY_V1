"""Discord bot — task/list/alarm/reminder commands, server administration
(channels/roles), and a live-updating task dashboard, in one dedicated channel.

Task/list/alarm/briefing commands use the exact same routing as the web
console and terminal chat (sunny_code.components.assistant.handle_message),
so behavior is identical across interfaces. Server-admin commands
(create/delete channels and roles) are Discord-only and checked separately
(see sunny_code.components.server_admin_parser) — they need a live
discord.Guild, which only exists here, so they can't route through that
shared, interface-agnostic handler. Scoped to one channel
(DISCORD_TASKS_CHANNEL_ID) — messages elsewhere are ignored, including for
server-admin commands.

Also the only real delivery mechanism for alarms/reminders today: there's no
clock/speaker hardware yet, so "sounding" an alarm means posting a message in
this channel when it's due (see the scheduled-items loop below).

Setup steps: see sunny-vault/docs/architecture/discord-bot.md
"""

import logging
from datetime import datetime

import discord
from discord.ext import tasks

from sunny_code.components.assistant import handle_message, is_briefing_trigger
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.key_status import missing_api_keys, startup_summary
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.server_admin_parser import ServerAdminParser
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.components.time_parse import next_occurrence

logger = logging.getLogger(__name__)

DASHBOARD_MARKER = "​"  # zero-width space appended to the dashboard message so a
# restarted bot can recognize its own pinned message and start editing it again
REFRESH_EMOJI = "🔄"
MAX_MESSAGE_LENGTH = 1900  # Discord's real limit is 2000; leave headroom
SCHEDULED_CHECK_INTERVAL_SECONDS = 30


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


def _find_channel(guild: discord.Guild, name: str):
    name = name.lower().lstrip("#")
    return discord.utils.find(lambda c: c.name.lower() == name, guild.channels)


def _find_role(guild: discord.Guild, name: str):
    name = name.lower()
    return discord.utils.find(lambda r: r.name.lower() == name, guild.roles)


async def _execute_server_admin(action: str, data: dict, guild: discord.Guild, tasks_channel_id: int) -> str:
    """Run one server-admin command against a live guild. Never raises —
    Discord API errors (missing permission, role-hierarchy limits, etc.)
    become a plain-text reply, same fail-quietly contract as the rest of
    the app. Deletions execute immediately, no confirmation step — same
    trust model as task/list deletion elsewhere in this app."""
    try:
        if action == "list_channels":
            names = ", ".join(f"#{c.name}" for c in guild.text_channels) or "(none)"
            return f"📺 CHANNELS\n{names}"

        if action == "create_channel":
            channel = await guild.create_text_channel(data["name"])
            return f"✅ Created channel #{channel.name}"

        if action == "delete_channel":
            channel = _find_channel(guild, data["name"])
            if channel is None:
                return f"❌ No channel named \"{data['name']}\" found"
            if channel.id == tasks_channel_id:
                return "⚠️  Can't delete the channel I'm listening in — that would strand me with no way to talk to you here."
            await channel.delete()
            return f"✅ Deleted channel #{channel.name}"

        if action == "list_roles":
            names = ", ".join(r.name for r in guild.roles if not r.is_default()) or "(none)"
            return f"🎭 ROLES\n{names}"

        if action == "create_role":
            role = await guild.create_role(name=data["name"])
            return f"✅ Created role \"{role.name}\""

        if action == "delete_role":
            role = _find_role(guild, data["name"])
            if role is None:
                return f"❌ No role named \"{data['name']}\" found"
            if role.is_default():
                return "⚠️  Can't delete @everyone — Discord doesn't allow it."
            await role.delete()
            return f"✅ Deleted role \"{role.name}\""

        if action in ("assign_role", "remove_role"):
            role = _find_role(guild, data["role_name"])
            if role is None:
                return f"❌ No role named \"{data['role_name']}\" found"
            member = guild.get_member(data["user_id"]) or await guild.fetch_member(data["user_id"])
            if action == "assign_role":
                await member.add_roles(role)
                return f"✅ Gave {member.display_name} the \"{role.name}\" role"
            await member.remove_roles(role)
            return f"✅ Removed the \"{role.name}\" role from {member.display_name}"

    except discord.Forbidden:
        return "❌ I don't have permission to do that — check my role has Manage Channels/Manage Roles, and (for roles) sits above the role being changed."
    except discord.NotFound:
        return "❌ That no longer exists — someone may have already removed it."
    except discord.HTTPException as e:
        return f"❌ Discord rejected that: {e}"

    return f"❌ Unrecognized server-admin action: {action}"


def create_discord_bot(
    tasks_engine: TaskEngine,
    briefing_engine: BriefingEngine,
    list_engine: ListEngine,
    scheduled_engine: ScheduledEngine,
    tasks_channel_id: int,
    briefings_channel_id: int = 0,
    warnings_channel_id: int = 0,
    task_updates_channel_id: int = 0,
) -> discord.Client:
    """Build (but don't start) the Discord client. tasks_channel_id is the only
    channel commands are read from; the three optional *_channel_id args are
    output-only destinations — see sunny-vault/docs/architecture/discord-bot.md."""
    intents = discord.Intents.default()
    intents.message_content = True  # required to read command text, not just embeds/mentions

    client = discord.Client(intents=intents)
    state = {"dashboard_message_id": None, "posted_key_status": False}

    async def _post_to(channel_id: int, text: str, fallback_channel_id: int = None):
        """Send `text` to `channel_id` if set, else to `fallback_channel_id` (typically
        the tasks channel) if that's set — used so an unconfigured output channel just
        means "goes where it always went" instead of silently vanishing."""
        target_id = channel_id or fallback_channel_id
        if not target_id:
            return
        try:
            channel = await client.fetch_channel(target_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord channel {target_id}: {e}")
            return
        for chunk in _chunk_message(text):
            await channel.send(chunk)

    async def refresh_dashboard(_change_message: str = None):
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

    async def on_task_change(change_message: str = None):
        """Runs on every successful add/update/delete, from any interface (web
        console, terminal chat, or this bot) — wiring it here covers all of
        them, not just Discord-originated changes."""
        await refresh_dashboard()
        if change_message and task_updates_channel_id:
            await _post_to(task_updates_channel_id, change_message)

    tasks_engine.on_change = on_task_change

    @tasks.loop(minutes=5)
    async def refresh_loop():
        await refresh_dashboard()

    @tasks.loop(seconds=SCHEDULED_CHECK_INTERVAL_SECONDS)
    async def scheduled_check_loop():
        """Post a ping for any due alarm/reminder — the only real 'sounding'
        mechanism until there's a clock/speaker device."""
        due = scheduled_engine.db.get_due_items(datetime.now())
        if not due:
            return

        try:
            channel = await client.fetch_channel(tasks_channel_id)
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Cannot access Discord tasks channel {tasks_channel_id}: {e}")
            return

        for item in due:
            icon = "⏰" if item["kind"] == "alarm" else "🔔"
            noun = "Alarm" if item["kind"] == "alarm" else "Reminder"
            try:
                await channel.send(f'{icon} {noun}: {item["label"]}')
            except discord.Forbidden:
                logger.warning("Missing permission to send scheduled-item ping")

            if item["recurrence"]:
                trigger_at = datetime.fromisoformat(item["trigger_at"])
                scheduled_engine.db.reschedule(item["id"], next_occurrence(trigger_at, item["recurrence"]))
            else:
                scheduled_engine.db.deactivate(item["id"])

    @client.event
    async def on_ready():
        logger.info(f"Discord bot connected as {client.user} (tasks channel: {tasks_channel_id})")
        if not refresh_loop.is_running():
            refresh_loop.start()  # runs immediately, then every 5 minutes
        if not scheduled_check_loop.is_running():
            scheduled_check_loop.start()  # runs immediately, then every 30s

        # Post what's still missing an API key once per run, so it's visible —
        # in #warnings if configured, else the tasks channel like before that
        # existed. Skipped entirely if everything's configured (no noise).
        if not state["posted_key_status"]:
            state["posted_key_status"] = True
            missing = missing_api_keys()
            if missing:
                await _post_to(warnings_channel_id, startup_summary(), fallback_channel_id=tasks_channel_id)

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != tasks_channel_id:
            return

        # Checked before the shared assistant router, same reason lists/alarms
        # are checked before tasks there: a generic "delete <title>" pattern
        # would otherwise swallow "delete channel #general" as a task-delete
        # attempt. Guild-scoped, so this only ever matches here, never on the
        # console or terminal chat.
        admin_command = ServerAdminParser.parse(message.content)
        if admin_command is not None:
            action, data = admin_command
            response = await _execute_server_admin(action, data, message.guild, tasks_channel_id)
            for chunk in _chunk_message(response):
                await message.channel.send(chunk)
            return

        session_id = f"discord:{message.channel.id}:{message.author.id}"
        response = await handle_message(
            message.content, tasks_engine, briefing_engine, list_engine, scheduled_engine, session_id=session_id
        )
        for chunk in _chunk_message(response):
            await message.channel.send(chunk)
        # Dashboard refresh (if this was a mutating command) happens automatically
        # via tasks_engine.on_change — no need to check/trigger it here too.

        if briefings_channel_id and is_briefing_trigger(message.content):
            await _post_to(briefings_channel_id, response)

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
